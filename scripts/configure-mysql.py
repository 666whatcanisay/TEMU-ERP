"""Provision a schema-scoped app account; save its secret only in ignored data/."""
import argparse
import getpass
import json
import os
from pathlib import Path
import re
import secrets
import pymysql

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',default=3306,type=int)
    parser.add_argument('--database',default='temu_workbench')
    parser.add_argument('--with-test-database',action='store_true')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,57}',args.database):
        raise SystemExit('Use a short SQL identifier for the database name.')
    path = ROOT / 'data/mysql.local.json'
    saved = None
    if path.is_file():
        saved = json.loads(path.read_text(encoding='utf-8'))
        if saved.get('host')==args.host and saved.get('port')==args.port and saved.get('database')==args.database:
            connection = pymysql.connect(**{k:saved[k] for k in ('host','port','user','password','database')})
            connection.close()
            if not args.with_test_database:
                print('Existing working app credentials preserved.')
                return
        else:
            raise SystemExit('A different local configuration exists; preserved without overwrite.')
    password = os.environ.get('WORKBENCH_MYSQL_BOOTSTRAP_PASSWORD') or getpass.getpass('Existing MySQL root password: ')
    root = pymysql.connect(host=args.host,port=args.port,user='root',password=password,
                           autocommit=True,charset='utf8mb4',connect_timeout=5)
    try:
        user = saved['user'] if saved else 'temu_workbench_app'
        app_password = saved['password'] if saved else secrets.token_urlsafe(32)
        with root.cursor() as cursor:
            if not saved:
                cursor.execute('SELECT 1 FROM mysql.user WHERE User=%s AND Host=%s',(user,'localhost'))
                if cursor.fetchone(): user = 'temu_workbench_'+secrets.token_hex(4)
            cursor.execute(f'CREATE DATABASE IF NOT EXISTS `{args.database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin')
            if not saved:
                cursor.execute('CREATE USER %s@%s IDENTIFIED BY %s',(user,'localhost',app_password))
            databases = [args.database]
            if args.with_test_database:
                test_name = args.database+'_test'
                cursor.execute(f'CREATE DATABASE IF NOT EXISTS `{test_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin')
                databases.append(test_name)
            for database in databases:
                cursor.execute(f'GRANT SELECT,INSERT,UPDATE,DELETE,CREATE,INDEX,ALTER,CREATE VIEW,SHOW VIEW ON `{database}`.* TO %s@%s',(user,'localhost'))
        settings = dict(driver='mysql',host=args.host,port=args.port,user=user,password=app_password,database=args.database)
        check = pymysql.connect(**{k:settings[k] for k in ('host','port','user','password','database')})
        check.close()
        path.parent.mkdir(parents=True,exist_ok=True)
        pending = path.with_suffix('.json.tmp')
        pending.write_text(json.dumps(settings,ensure_ascii=False,indent=2),encoding='utf-8')
        pending.replace(path)
        print(json.dumps({'configured':True,'database':args.database,'host':args.host,'port':args.port,
                          'account':'schema-scoped app user','local_config':'data/mysql.local.json'},ensure_ascii=False))
    finally:
        root.close()

if __name__ == '__main__':
    main()
