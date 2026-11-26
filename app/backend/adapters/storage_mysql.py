"""MySQL entity store, versioned migrations and transactional full backups."""
from contextlib import contextmanager, nullcontext
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import threading

from .storage_relational import RelationalStore
from .mysql_entities import EntityRepositories, ROOTS
from . import mysql_schema as schema
from . import relational_codec as codec
from . import storage_state

BACKUP_FORMAT='temu-workbench-relational/v2'


class Rows:
    def __init__(self, rows):self.rows=list(rows)
    def fetchone(self):return self.rows[0] if self.rows else None
    def fetchall(self):return self.rows


def portable(value):
    if isinstance(value,Decimal):return format(value,'f')
    if isinstance(value,datetime):return value.isoformat(sep=' ',timespec='microseconds')
    if isinstance(value,date):return value.isoformat()
    if isinstance(value,dict):return {k:portable(v) for k,v in value.items()}
    if isinstance(value,list):return [portable(v) for v in value]
    return value


def relational_digest(tables):
    value={table:sorted(portable(rows),key=lambda r:tuple(str(r[k]) for k in schema.PRIMARY[table])) for table,rows in tables.items()}
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


class MySQLStore(EntityRepositories,RelationalStore):
    engine='mysql'
    backup_suffix='.mysql.json'
    schema_version=schema.VERSION

    def __init__(self,*,host,port,user,password,database,allow_legacy=False):
        self._settings=dict(host=host,port=int(port),user=user,password=password,database=database)
        self._lock=threading.RLock();self._in_transaction=False;self._conn=None
        self._connect()
        try:self._init_schema(allow_legacy)
        except BaseException:
            self.close();raise

    @property
    def location(self):return f'mysql://{self._settings["host"]}:{self._settings["port"]}/{self._settings["database"]}'

    def _connect(self):
        import pymysql
        try:
            self._conn=pymysql.connect(**self._settings,charset='utf8mb4',cursorclass=pymysql.cursors.DictCursor,
                autocommit=True,connect_timeout=5,read_timeout=30,write_timeout=30)
            with self._conn.cursor() as cursor:cursor.execute("SET time_zone='+00:00'")
        except pymysql.Error:
            raise RuntimeError('MySQL连接失败；请检查数据库服务及本机连接配置，不会自动退回SQLite。') from None

    def _ensure_connection(self):
        if self._in_transaction:return
        try:self._conn.ping(reconnect=False)
        except Exception:
            try:self._conn.close()
            except Exception:pass
            self._connect()

    def _execute(self,sql,params=()):
        with self._lock:
            self._ensure_connection()
            with self._conn.cursor() as cursor:
                cursor.execute(sql.replace('?','%s'),params)
                return Rows(cursor.fetchall() if cursor.description else [])

    def _commit(self):pass

    def _upsert(self,table,columns,values,keys,updates):
        names=','.join(f'`{c}`' for c in columns);marks=','.join('?' for _ in columns)
        changes=','.join(f'`{c}`=?' for c in updates);lookup=dict(zip(columns,values))
        self._execute(f'INSERT INTO `{table}` ({names}) VALUES ({marks}) ON DUPLICATE KEY UPDATE {changes}',list(values)+[lookup[c] for c in updates])

    def _table_exists(self,name):
        return bool(self._execute('SELECT 1 FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=?',(name,)).fetchone())

    def _init_schema(self,allow_legacy):
        ready=self._table_exists('schema_migrations') and self._execute('SELECT * FROM schema_migrations WHERE version=?',(schema.VERSION,)).fetchone()
        self.has_legacy=self._table_exists('records') or self._table_exists('legacy_v1_records')
        self._schema_ready=bool(ready)
        if ready:
            if ready['checksum']!=schema.checksum():raise RuntimeError('Applied migration file was modified; create a new migration instead.')
            self.validate_parameter_definitions()
            return
        if self.has_legacy and not allow_legacy:
            raise RuntimeError('检测到v1数据库，请停止应用后执行 python scripts/upgrade-database-v2.py --app-stopped；不会自动覆盖旧数据。')
        for statement in schema.statements():self._execute(statement)
        if not self.has_legacy:
            with self.transaction():
                self.ensure_parameter_definitions();self._mark_ready('Fresh relational database')
            self._schema_ready=True

    def _mark_ready(self,note):
        self._put('schema_migrations',dict(version=schema.VERSION,checksum=schema.checksum(),applied_at=codec.utc(),note=note),['version'])

    @contextmanager
    def transaction(self,consistent=False):
        with self._lock:
            if self._in_transaction:raise RuntimeError('Nested database transaction is not supported')
            self._ensure_connection()
            self._execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            self._execute('START TRANSACTION WITH CONSISTENT SNAPSHOT' if consistent else 'START TRANSACTION')
            self._in_transaction=True
            try:
                yield
                self._conn.commit()
            except BaseException:
                self._conn.rollback();raise
            finally:self._in_transaction=False

    def read_legacy_state(self):
        prefix='' if self._table_exists('records') else 'legacy_v1_'
        tables={t:self._execute(f'SELECT * FROM `{prefix+t}`').fetchall() for t in storage_state.TABLES}
        return storage_state.envelope(tables)

    def upgrade_legacy(self,archive=True):
        if self._schema_ready:
            if archive:self.archive_legacy_tables()
            return {'status':'already_current'}
        state=self.read_legacy_state()
        with self.transaction():
            self._import_legacy(state,require_empty=True)
            self._mark_ready('Lossless v1 DTO import verified before archive')
        self._schema_ready=True
        if archive:self.archive_legacy_tables()
        return {'status':'migrated','legacy_sha256':state['sha256'],'entity_sha256':self.export_state()['sha256']}

    def archive_legacy_tables(self):
        if not self._schema_ready:raise RuntimeError('Entity import is not verified')
        if self._table_exists('records'):
            # One atomic RENAME statement, after the verified DML commit.
            names=','.join(f'`{table}` TO `legacy_v1_{table}`' for table in storage_state.TABLES)
            self._execute('RENAME TABLE '+names)

    def _compat_state(self):
        tables={t:[] for t in storage_state.TABLES}
        for kind in ROOTS:
            for record in self.list_records(kind):
                meta=self.record_metadata(kind,record['id'])
                tables['records'].append(dict(record_type=kind,id=record['id'],payload=codec.dumps(record),
                    decision=record.get('internal_decision') if kind=='candidate' else None,
                    market=record.get('research_market') if kind=='candidate' else None,
                    candidate_id=record.get('candidate_id') if kind=='feedback' else None,
                    synthetic=int(bool(record.get('synthetic'))),created_at=meta['created_at'],updated_at=meta['updated_at']))
        for r in self._execute('SELECT * FROM field_revisions').fetchall():
            tables['revisions'].append(dict(id=r['revision_id'],candidate_id=r['product_id'],sku_ref=r['sku_ref'],
                field_key=r['field_key'],payload=r['payload_json'],created_at=r['original_at']))
        for r in self._execute('SELECT * FROM internal_submissions').fetchall():
            tables['submissions'].append(dict(id=r['submission_id'],candidate_id=r['product_id'],payload=r['snapshot_json'],created_at=r['original_at']))
        for r in self._execute('SELECT * FROM source_snapshots').fetchall():
            payload=json.loads(r['payload_json'])
            if payload.get('migration_origin')=='source_record_backfill':continue
            tables['snapshots'].append(dict(source_id=r['source_ref'],snapshot_ref=r['snapshot_ref'],sha256=r['sha256'],
                file_path=r['file_path'],status=r['status'],captured_at=r['original_at'],payload=r['payload_json']))
        for r in self._execute('SELECT * FROM integration_status').fetchall():
            tables['adapter_status'].append(dict(port_key=r['port_key'],status=r['status'],detail=r['detail_json'],updated_at=r['original_at']))
        return storage_state.envelope(tables)

    def export_state(self):
        """v1 DTO interchange for SQLite migration. Full backups use all entities."""
        with self._atomic():return self._compat_state() if self._schema_ready else self.read_legacy_state()

    def _clear_entities(self):
        for table in reversed(schema.TABLES):self._execute(f'DELETE FROM `{table}`')

    def _import_legacy(self,state,require_empty=False):
        storage_state.validate(state)
        if require_empty and any(self._execute(f'SELECT 1 FROM `{t}` LIMIT 1').fetchone() for t in ('products','buyer_feedback','business_policies','sources','internal_submissions','field_revisions')):
            raise ValueError('目标MySQL库非空，拒绝覆盖已有数据')
        self._clear_entities();self.ensure_parameter_definitions()
        priority={'source':0,'candidate':1,'policy':2,'feedback':3}
        for row in sorted(state['tables']['records'],key=lambda r:priority[r['record_type']]):
            self._save_record(json.loads(row['payload']),dict(created_at=row['created_at'],updated_at=row['updated_at']))
        for row in state['tables']['revisions']:self._save_revision(row)
        for row in state['tables']['submissions']:
            self.save_submission(json.loads(row['payload']))
            self._execute('UPDATE internal_submissions SET snapshot_json=? WHERE submission_id=?',(row['payload'],row['id']))
        for row in state['tables']['snapshots']:self._save_snapshot(row)
        for row in state['tables']['adapter_status']:
            self._put('integration_status',dict(port_key=row['port_key'],status=row['status'],detail_json=row['detail'],
                updated_at=codec.utc(row['updated_at']),original_at=row['updated_at']),['port_key'])
        actual=self._compat_state()
        if actual['sha256']!=state['sha256']:
            raise ValueError('迁移或恢复对账不一致，事务已回滚')

    def export_relational_state(self):
        with self._atomic():
            tables={t:portable(self._execute(f'SELECT * FROM `{t}`').fetchall()) for t in schema.TABLES}
        return dict(format=BACKUP_FORMAT,schema_version=schema.VERSION,ddl_checksum=schema.checksum(),
                    tables=tables,sha256=relational_digest(tables))

    def replace_state(self,state,require_empty=False):
        if state.get('format')==storage_state.FORMAT:
            with self._atomic():self._import_legacy(state,require_empty)
            return
        self._validate_relational(state)
        with self._atomic():
            if require_empty and any(self._execute(f'SELECT 1 FROM `{t}` LIMIT 1').fetchone() for t in ('products','sources','buyer_feedback')):
                raise ValueError('目标MySQL库非空，拒绝覆盖已有数据')
            self._clear_entities()
            for table in schema.TABLES:
                for row in state['tables'][table]:
                    names=','.join(f'`{c}`' for c in row);marks=','.join('?' for _ in row)
                    self._execute(f'INSERT INTO `{table}` ({names}) VALUES ({marks})',list(row.values()))
            try:self.validate_parameter_definitions()
            except RuntimeError as exc:raise ValueError(str(exc)) from None
            if self.export_relational_state()['sha256']!=state['sha256']:
                raise ValueError('Relational restore checksum mismatch')

    def _validate_relational(self,state):
        if state.get('format')!=BACKUP_FORMAT or state.get('schema_version')!=schema.VERSION or state.get('ddl_checksum')!=schema.checksum():
            raise ValueError('Unsupported relational backup version')
        tables=state.get('tables')
        if not isinstance(tables,dict) or set(tables)!=set(schema.TABLES):raise ValueError('Backup table set mismatch')
        for table,rows in tables.items():
            columns={c['Field'] for c in self._execute(f'SHOW COLUMNS FROM `{table}`').fetchall()}
            seen=set()
            if not isinstance(rows,list):raise ValueError('Invalid backup rows')
            for row in rows:
                if not isinstance(row,dict) or set(row)!=columns:raise ValueError('Invalid backup columns')
                key=tuple(row[k] for k in schema.PRIMARY[table])
                if key in seen:raise ValueError('Duplicate backup key')
                seen.add(key)
        if state.get('sha256')!=relational_digest(tables):raise ValueError('Backup checksum mismatch')

    def backup(self,target_path):
        target=Path(target_path);target.parent.mkdir(parents=True,exist_ok=True)
        pending=target.with_name(target.name+'.tmp')
        pending.write_text(json.dumps(self.export_relational_state(),ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
        pending.replace(target);return target

    def restore(self,source_path):
        import pymysql
        path=Path(source_path)
        if not path.is_file():return ['backup file not found']
        try:
            if path.stat().st_size>100*1024*1024:return ['backup file exceeds 100MB']
            self.replace_state(json.loads(path.read_text(encoding='utf-8')))
        except (ValueError,TypeError,KeyError,UnicodeError,pymysql.MySQLError):
            return ['invalid or corrupted MySQL full backup; current data preserved']
        return []

    def close(self):
        if self._conn is not None:self._conn.close()
