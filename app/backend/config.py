"""Runtime configuration: all paths stay on the E: workbench directory by default."""
from __future__ import annotations

import os
import json
from pathlib import Path

ROOT = Path(os.environ.get("WORKBENCH_ROOT", Path(__file__).resolve().parents[2]))
DATA_DIR = Path(os.environ.get("WORKBENCH_DATA_DIR", ROOT / "data"))
CACHE_DIR = Path(os.environ.get("WORKBENCH_CACHE_DIR", ROOT / ".cache" / "workbench"))
REPORTS_DIR = ROOT / "reports"
FIXTURES_DIR = ROOT / "fixtures"
CONTRACTS_DIR = ROOT / "contracts"
RESEARCH_DIR = ROOT / "research"
DB_PATH = DATA_DIR / "workbench.db"
SAMPLES_DIR = DATA_DIR / "samples"

# This file is local-only under ignored data/. Environment variables take priority.
_local_path = DATA_DIR / 'mysql.local.json'
_local = json.loads(_local_path.read_text(encoding='utf-8')) if _local_path.is_file() else {}
DB_DRIVER = os.environ.get('WORKBENCH_DB_DRIVER', _local.get('driver','mysql')).lower()
if DB_DRIVER not in ('mysql','sqlite'):
    raise ValueError('WORKBENCH_DB_DRIVER must be mysql or sqlite')
MYSQL_HOST = os.environ.get('WORKBENCH_MYSQL_HOST', _local.get('host','127.0.0.1'))
MYSQL_PORT = int(os.environ.get('WORKBENCH_MYSQL_PORT', _local.get('port',3306)))
MYSQL_USER = os.environ.get('WORKBENCH_MYSQL_USER', _local.get('user','temu_workbench_app'))
MYSQL_PASSWORD = os.environ.get('WORKBENCH_MYSQL_PASSWORD', _local.get('password',''))
MYSQL_DATABASE = os.environ.get('WORKBENCH_MYSQL_DATABASE', _local.get('database','temu_workbench'))

def mysql_settings():
    if not MYSQL_PASSWORD:
        raise RuntimeError('请通过环境变量或本机data/mysql.local.json配置MySQL凭据；不会自动退回SQLite。')
    return dict(host=MYSQL_HOST,port=MYSQL_PORT,user=MYSQL_USER,password=MYSQL_PASSWORD,database=MYSQL_DATABASE)

def database_info():
    return {'engine':DB_DRIVER,'database':MYSQL_DATABASE if DB_DRIVER=='mysql' else DB_PATH.name}

HOST = os.environ.get("WORKBENCH_HOST", "127.0.0.1")
PORT = int(os.environ.get("WORKBENCH_PORT", "8765"))
MODE = os.environ.get("WORKBENCH_MODE", "fully_managed")
LIVE_WRITE_ENABLED = os.environ.get("WORKBENCH_LIVE_PLATFORM_WRITE", "false").lower() == "true"
COLLECT_ALLOWED_HOSTS=tuple(h.strip() for h in os.environ.get('COLLECT_ALLOWED_HOSTS','relaxdays.de,www.ikea.com,help.dianxiaomi.com,erp.91miaoshou.com').split(',') if h.strip())

for directory in (DATA_DIR, CACHE_DIR, REPORTS_DIR, SAMPLES_DIR):
    directory.mkdir(parents=True, exist_ok=True)
