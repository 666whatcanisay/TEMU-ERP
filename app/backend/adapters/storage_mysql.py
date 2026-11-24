"""MySQL 8 storage: shared record semantics, InnoDB transactions and full backups."""
from contextlib import contextmanager
import json
from pathlib import Path
import threading

from .storage_relational import RelationalStore
from . import storage_state


class Rows:
    def __init__(self, rows): self.rows = list(rows)
    def fetchone(self): return self.rows[0] if self.rows else None
    def fetchall(self): return self.rows


class MySQLStore(RelationalStore):
    engine = 'mysql'
    backup_suffix = '.mysql.json'

    def __init__(self, *, host, port, user, password, database):
        self._settings = dict(host=host,port=int(port),user=user,password=password,database=database)
        self._lock = threading.RLock()
        self._in_transaction = False
        self._conn = None
        self._connect()
        self._init_schema()

    @property
    def location(self):
        return f'mysql://{self._settings["host"]}:{self._settings["port"]}/{self._settings["database"]}'

    def _connect(self):
        import pymysql
        try:
            self._conn = pymysql.connect(**self._settings,charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor,autocommit=True,
                connect_timeout=5,read_timeout=30,write_timeout=30)
        except pymysql.Error:
            raise RuntimeError('MySQL连接失败；请检查数据库服务及本机连接配置，不会自动退回SQLite。') from None

    def _ensure_connection(self):
        if self._in_transaction: return
        try:
            self._conn.ping(reconnect=False)
        except Exception:
            try: self._conn.close()
            except Exception: pass
            self._connect()

    def _execute(self, sql, params=()):
        with self._lock:
            self._ensure_connection()
            with self._conn.cursor() as cursor:
                # Only static internal queries use this DB-API placeholder adaptation.
                # Values always remain separately bound parameters.
                cursor.execute(sql.replace('?', '%s'), params)
                return Rows(cursor.fetchall() if cursor.description else [])

    def _commit(self):
        # Individual mutations are single autocommit statements. Explicit bulk
        # transactions below commit once; never replay a possibly committed write.
        pass

    def _upsert(self, table, columns, values, keys, updates):
        names = ','.join(f'`{c}`' for c in columns)
        marks = ','.join('?' for _ in columns)
        change = ','.join(f'`{c}`=?' for c in updates)
        lookup = dict(zip(columns, values))
        self._execute(f'INSERT INTO `{table}` ({names}) VALUES ({marks}) ON DUPLICATE KEY UPDATE {change}',
                      list(values)+[lookup[c] for c in updates])

    def _init_schema(self):
        definitions = {
            'records': '''record_type VARCHAR(32) NOT NULL,id VARCHAR(191) NOT NULL,payload LONGTEXT NOT NULL,
                decision VARCHAR(64),market VARCHAR(32),candidate_id VARCHAR(191),synthetic TINYINT NOT NULL DEFAULT 0,
                created_at VARCHAR(40) NOT NULL,updated_at VARCHAR(40) NOT NULL,
                PRIMARY KEY(record_type,id),KEY record_lookup(record_type,candidate_id,updated_at),CHECK(JSON_VALID(payload))''',
            'revisions': '''id VARCHAR(191) PRIMARY KEY,candidate_id VARCHAR(191) NOT NULL,sku_ref VARCHAR(191),
                field_key VARCHAR(191) NOT NULL,payload LONGTEXT NOT NULL,created_at VARCHAR(40) NOT NULL,
                KEY revision_lookup(candidate_id,created_at),CHECK(JSON_VALID(payload))''',
            'adapter_status': '''port_key VARCHAR(191) PRIMARY KEY,status VARCHAR(64) NOT NULL,
                detail LONGTEXT NOT NULL,updated_at VARCHAR(40) NOT NULL,CHECK(JSON_VALID(detail))''',
            'submissions': '''id VARCHAR(191) PRIMARY KEY,candidate_id VARCHAR(191) NOT NULL,payload LONGTEXT NOT NULL,
                created_at VARCHAR(40) NOT NULL,KEY submission_lookup(candidate_id,created_at),CHECK(JSON_VALID(payload))''',
            'snapshots': '''source_id VARCHAR(191) PRIMARY KEY,snapshot_ref TEXT,sha256 VARCHAR(64),file_path TEXT,
                status VARCHAR(64) NOT NULL,captured_at VARCHAR(40) NOT NULL,payload LONGTEXT NOT NULL,CHECK(JSON_VALID(payload))''',
        }
        for table,definition in definitions.items():
            self._execute(f'CREATE TABLE IF NOT EXISTS `{table}` ({definition}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin')

    @contextmanager
    def transaction(self, consistent=False):
        with self._lock:
            if self._in_transaction: raise RuntimeError('Nested database transaction is not supported')
            self._ensure_connection()
            self._execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            self._execute('START TRANSACTION WITH CONSISTENT SNAPSHOT' if consistent else 'START TRANSACTION')
            self._in_transaction = True
            try:
                yield
                self._conn.commit()
            except BaseException:
                self._conn.rollback()
                raise
            finally:
                self._in_transaction = False

    def export_state(self):
        with self.transaction(consistent=True):
            tables = {table:self._execute(f'SELECT * FROM `{table}`').fetchall() for table in storage_state.TABLES}
        return storage_state.envelope(tables)

    def replace_state(self, state, require_empty=False):
        storage_state.validate(state)
        with self.transaction():
            if require_empty and any(self._execute(f'SELECT 1 FROM `{t}` LIMIT 1').fetchone() for t in storage_state.TABLES):
                raise ValueError('目标MySQL库非空，拒绝覆盖已有数据')
            for table,columns in storage_state.TABLES.items():
                self._execute(f'DELETE FROM `{table}`')
                names = ','.join(f'`{c}`' for c in columns)
                marks = ','.join('?' for _ in columns)
                for row in state['tables'][table]:
                    self._execute(f'INSERT INTO `{table}` ({names}) VALUES ({marks})', [row[c] for c in columns])
            actual = {t:self._execute(f'SELECT * FROM `{t}`').fetchall() for t in storage_state.TABLES}
            if storage_state.digest(actual) != state['sha256']:
                raise ValueError('迁移或恢复对账不一致，事务已回滚')

    def backup(self, target_path):
        target = Path(target_path)
        target.parent.mkdir(parents=True,exist_ok=True)
        state = self.export_state()
        pending = target.with_name(target.name+'.tmp')
        pending.write_text(json.dumps(state,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
        pending.replace(target)
        return target

    def restore(self, source_path):
        import pymysql
        source = Path(source_path)
        if not source.is_file(): return ['backup file not found']
        try:
            if source.stat().st_size > 100*1024*1024: return ['backup file exceeds 100MB']
            state = json.loads(source.read_text(encoding='utf-8'))
            self.replace_state(state)
        except (ValueError, TypeError, KeyError, UnicodeError, pymysql.MySQLError):
            return ['invalid or corrupted MySQL full backup; current data preserved']
        return []

    def close(self):
        if self._conn is not None: self._conn.close()
