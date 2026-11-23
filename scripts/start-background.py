"""Start this local workbench with hidden console and persistent E: logs."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
ROOT=Path(__file__).resolve().parents[1]
port=int(os.environ.get('WORKBENCH_PORT','8765'))
with socket.socket() as probe:
    if probe.connect_ex(('127.0.0.1',port))==0:
        raise SystemExit(f'Port {port} is already in use; existing process preserved.')
env=os.environ.copy()
env.update(PYTHONPATH=str(ROOT),WORKBENCH_HOST='127.0.0.1',WORKBENCH_PORT=str(port),
    WORKBENCH_DATA_DIR=str(ROOT/'data'),PYTHONPYCACHEPREFIX=str(ROOT/'.cache/python'))
logs=ROOT/'reports/runtime'; logs.mkdir(parents=True,exist_ok=True)
with (logs/'server.log').open('a',encoding='utf-8') as output:
    child=subprocess.Popen([sys.executable,'-u','-X','utf8','-m','app.backend.api.server'],cwd=ROOT,env=env,
        stdout=output,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
(logs/'server.pid').write_text(str(child.pid),encoding='ascii')
for _ in range(30):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health',timeout=1) as response:
            print(f'Workbench running: http://127.0.0.1:{port} PID={child.pid}')
            break
    except OSError:
        if child.poll() is not None:
            raise SystemExit('Server failed; see reports/runtime/server.log')
        time.sleep(.2)
else:
    raise SystemExit('Server did not become ready; see reports/runtime/server.log')
