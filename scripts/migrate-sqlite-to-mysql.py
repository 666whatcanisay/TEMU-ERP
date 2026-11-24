"""Freeze the app first. Copy all five tables without changing IDs or timestamps."""
import argparse
from contextlib import closing
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.backend import config
from app.backend.adapters.storage_mysql import MySQLStore
from app.backend.adapters import storage_state

def read_sqlite(path):
    with closing(sqlite3.connect(f'{path.resolve().as_uri()}?mode=ro',uri=True)) as source:
        source.row_factory = sqlite3.Row
        if source.execute('PRAGMA quick_check').fetchone()[0]!='ok':
            raise ValueError('SQLite integrity check failed')
        source.execute('BEGIN')
        tables = {table:[dict(row) for row in source.execute(f'SELECT * FROM {table}').fetchall()]
                  for table in storage_state.TABLES}
    return storage_state.envelope(tables)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=config.DB_PATH)
    parser.add_argument('--app-stopped',action='store_true',help='Confirm the app is stopped to prevent writes during migration')
    args = parser.parse_args()
    if not args.app_stopped: raise SystemExit('Stop the workbench, then rerun with --app-stopped.')
    with socket.socket() as probe:
        if probe.connect_ex((config.HOST,config.PORT))==0:
            raise SystemExit('Workbench port is still active; stop the app before migration.')
    if not args.source.is_file(): raise SystemExit('SQLite source does not exist.')
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    folder = config.DATA_DIR / 'backups'
    folder.mkdir(parents=True,exist_ok=True)
    backup = folder / f'before-mysql-{stamp}.db'
    with closing(sqlite3.connect(f'{args.source.resolve().as_uri()}?mode=ro',uri=True)) as source, closing(sqlite3.connect(backup)) as saved:
        source.backup(saved)
    state = read_sqlite(backup)
    target = MySQLStore(**config.mysql_settings())
    try:
        current = target.export_state()
        if current['sha256'] == state['sha256']:
            status = 'already_identical'
        else:
            target.replace_state(state,require_empty=True)
            status = 'migrated'
        actual = target.export_state()
        assert actual['sha256']==state['sha256']
        report = {'status':status,'source_backup':str(backup),'target':target.location,
                  'tables':{t:len(rows) for t,rows in state['tables'].items()},
                  'source_sha256':state['sha256'],'target_sha256':actual['sha256'],
                  'ids_timestamps_and_payloads':'identical'}
        out = ROOT / 'reports/mysql-migration'
        out.mkdir(parents=True,exist_ok=True)
        (out/f'migration-{stamp}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False))
    finally:
        target.close()

if __name__=='__main__':
    main()
