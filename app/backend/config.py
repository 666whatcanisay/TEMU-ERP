"""Runtime configuration: all paths stay on the E: workbench directory by default."""
from __future__ import annotations

import os
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

HOST = os.environ.get("WORKBENCH_HOST", "127.0.0.1")
PORT = int(os.environ.get("WORKBENCH_PORT", "8765"))
MODE = os.environ.get("WORKBENCH_MODE", "fully_managed")
LIVE_WRITE_ENABLED = os.environ.get("WORKBENCH_LIVE_PLATFORM_WRITE", "false").lower() == "true"
COLLECT_ALLOWED_HOSTS=tuple(h.strip() for h in os.environ.get('COLLECT_ALLOWED_HOSTS','relaxdays.de,www.ikea.com,help.dianxiaomi.com,erp.91miaoshou.com').split(',') if h.strip())

for directory in (DATA_DIR, CACHE_DIR, REPORTS_DIR, SAMPLES_DIR):
    directory.mkdir(parents=True, exist_ok=True)
