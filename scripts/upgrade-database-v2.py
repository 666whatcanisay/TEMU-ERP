"""Back up v1, migrate and reconcile DTOs, index evidence, archive old tables.

Run with the app stopped. DDL and DML are separate phases because MySQL DDL
implicitly commits. Admin credentials are read only from getpass/process env.
"""
import argparse
from datetime import datetime
import getpass
import hashlib
import json
import os
from pathlib import Path
import socket
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.backend import config
from app.backend.adapters import storage_state, mysql_schema
from app.backend.adapters.storage_mysql import MySQLStore
from app.backend.adapters import relational_codec as codec


def index_existing_snapshots(store):
    rows=[]
    with store._atomic():
        for source in store.list_records('source'):
            ref=source.get('snapshot_ref')
            if not ref or store.get_snapshot(source['id']):continue
            path=Path(ref);exists=path.is_file()
            actual=hashlib.sha256(path.read_bytes()).hexdigest() if exists else None
            matches=(actual==source['sha256']) if actual and source.get('sha256') else None
            status='indexed_verified' if exists and matches else 'hash_mismatch' if exists and matches is False else 'indexed_unverified' if exists else 'missing_file'
            observed=source.get('retrieved_at') or source.get('observed_at') or codec.utc().isoformat()
            payload={'migration_origin':'source_record_backfill','capture_time_precision':'date_only' if len(observed)==10 else 'timestamp',
                     'file_exists':exists,'hash_verified':matches,'actual_sha256':actual,'verified_at':codec.utc().isoformat()+'Z'}
            store._save_snapshot(dict(source_id=source['id'],snapshot_ref=ref,sha256=source.get('sha256') or actual,
                file_path=ref,status=status,captured_at=observed,payload=codec.dumps(payload)))
            store._execute('UPDATE source_snapshots SET file_exists=?,hash_verified=? WHERE source_ref=?',(exists,matches,source['id']))
            rows.append({'source_id':source['id'],'file_exists':exists,'hash_verified':matches,'status':status})
    return rows


def read_original(settings):
    import pymysql
    connection=pymysql.connect(**settings,charset='utf8mb4',autocommit=False,cursorclass=pymysql.cursors.DictCursor)
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT table_name AS table_name FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name IN ('records','legacy_v1_records')")
            names={r['table_name'] for r in cur.fetchall()}
            prefix='' if 'records' in names else 'legacy_v1_'
            if not names:return None
            cur.execute('START TRANSACTION WITH CONSISTENT SNAPSHOT')
            tables={}
            for table in storage_state.TABLES:
                cur.execute(f'SELECT * FROM `{prefix+table}`');tables[table]=list(cur.fetchall())
            return storage_state.envelope(tables)
    finally:connection.rollback();connection.close()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--app-stopped',action='store_true')
    parser.add_argument('--admin',action='store_true',help='Use root only for the migration, never store its password')
    args=parser.parse_args()
    if not args.app_stopped:raise SystemExit('Stop the app and pass --app-stopped.')
    with socket.socket() as probe:
        if probe.connect_ex((config.HOST,config.PORT))==0:raise SystemExit('Application port is still active; no migration performed.')
    settings=config.mysql_settings()
    if args.admin:
        settings={**settings,'user':'root','password':os.environ.get('WORKBENCH_MIGRATION_ADMIN_PASSWORD') or getpass.getpass('MySQL admin password (not saved): ')}
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
    backup_dir=config.DATA_DIR/'backups';backup_dir.mkdir(parents=True,exist_ok=True)
    original=read_original(settings)
    old_backup=backup_dir/f'before-relational-v2-{stamp}.mysql.json'
    if original:
        old_backup.write_text(json.dumps(original,ensure_ascii=False,indent=2),encoding='utf-8')
    store=MySQLStore(**settings,allow_legacy=True)
    try:
        migration=store.upgrade_legacy(archive=False)
        # Confirm exact old data before adding the reference registry/snapshot indexes.
        if migration['status']=='migrated' and original['sha256']!=store.export_state()['sha256']:
            raise RuntimeError('Old/new business checksums differ; legacy tables kept untouched')
        registry=json.loads((config.RESEARCH_DIR/'sources.json').read_text(encoding='utf-8'))['sources']
        store.ensure_reference_sources(registry)
        snapshots=index_existing_snapshots(store)
        backup=store.backup(backup_dir/f'after-relational-v2-{stamp}.mysql.json')
        store.archive_legacy_tables()
        counts={table:store._execute(f'SELECT COUNT(*) AS n FROM `{table}`').fetchone()['n'] for table in mysql_schema.TABLES}
        foreign_keys=store._execute("SELECT COUNT(*) AS n FROM information_schema.referential_constraints WHERE constraint_schema=DATABASE()").fetchone()['n']
        report={'schema_version':mysql_schema.VERSION,'migration':migration,'old_backup':str(old_backup) if original else None,
            'full_relational_backup':str(backup),'tables':counts,'foreign_keys':foreign_keys,'snapshot_backfill':snapshots,
            'archive':'legacy_v1_* preserved, no longer used by the application',
            'schema_checksum':mysql_schema.checksum()}
        target=ROOT/'reports/database-v2';target.mkdir(parents=True,exist_ok=True)
        (target/f'migration-{stamp}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False,indent=2))
    finally:store.close()


if __name__=='__main__':main()
