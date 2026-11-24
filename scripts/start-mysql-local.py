"""Start an isolated Windows MySQL instance under this project's ignored data/."""
from pathlib import Path
import argparse
import getpass
import os
import shutil
import socket
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--initialize', action='store_true', help='Initialize only a completely empty project data directory')
    parser.add_argument('--port', type=int, default=3307)
    args = parser.parse_args()
    if os.name != 'nt':
        raise SystemExit('Use a normal MySQL service or compose.mysql.yml on this OS.')
    executable = shutil.which('mysqld') or str(Path(os.environ.get('ProgramFiles','C:/Program Files')) / 'MySQL/MySQL Server 8.0/bin/mysqld.exe')
    data = (ROOT / 'data/mysql-server').resolve()
    assert data.parent == (ROOT / 'data').resolve()
    logs = ROOT / 'reports/runtime'
    logs.mkdir(parents=True, exist_ok=True)
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1', args.port)) == 0:
            raise SystemExit(f'Port {args.port} is already occupied; existing instance preserved.')
    base = [executable, '--no-defaults', f'--basedir={Path(executable).parent.parent}', f'--datadir={data}']
    init_file = None
    if args.initialize:
        if data.exists() and any(data.iterdir()):
            raise SystemExit('Initialization refused: project MySQL directory is not empty.')
        password = os.environ.get('WORKBENCH_MYSQL_BOOTSTRAP_PASSWORD') or getpass.getpass('New isolated MySQL root password: ')
        if not password:
            raise SystemExit('A non-empty root password is required.')
        data.mkdir(parents=True, exist_ok=True)
        with (logs / 'mysql-initialize.log').open('wb') as output:
            subprocess.run(base + ['--initialize-insecure'], stdout=output, stderr=subprocess.STDOUT, check=True)
        init_file = ROOT / 'data/mysql-initial-password.sql'
        escaped = password.replace('\\','\\\\').replace("'", "\\'")
        init_file.write_text(f"ALTER USER 'root'@'localhost' IDENTIFIED BY '{escaped}';\n", encoding='utf-8')
    elif not (data / 'auto.cnf').exists():
        raise SystemExit('Project MySQL is not initialized; use --initialize once.')
    command = base + [f'--port={args.port}', '--bind-address=127.0.0.1', '--mysqlx=0', '--console']
    if init_file:
        command.append(f'--init-file={init_file}')
    try:
        with (logs / 'mysql-server.log').open('ab') as output:
            child = subprocess.Popen(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
        (logs / 'mysql-server.pid').write_text(str(child.pid), encoding='ascii')
        for _ in range(120):
            if child.poll() is not None:
                raise SystemExit('MySQL stopped; inspect reports/runtime/mysql-server.log locally.')
            with socket.socket() as probe:
                if probe.connect_ex(('127.0.0.1', args.port)) == 0:
                    print(f'MySQL ready on 127.0.0.1:{args.port}; project data directory; PID={child.pid}')
                    return
            time.sleep(.5)
        raise SystemExit('MySQL startup pending; inspect the local runtime log.')
    finally:
        if init_file and init_file.exists():
            init_file.unlink()

if __name__ == '__main__':
    main()
