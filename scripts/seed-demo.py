"""Load the published, offline five-product case without touching existing records."""
from __future__ import annotations
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.backend import config
from app.backend.adapters.storage_relational import RelationalStore
from app.backend.adapters.store_factory import create_store
from app.backend.application.services import WorkbenchService


def seed(store: RelationalStore) -> dict:
    bundle = json.loads((ROOT / 'fixtures' / 'demo-catalog.json').read_text(encoding='utf-8'))
    service = WorkbenchService(store)
    added, skipped = [], []
    # All records are authored cases. Never copy the working user's database.
    for record in bundle['records']:
        kind, rid = record['record_type'], record['id']
        if store.get_record(kind, rid) or (kind == 'policy' and service.get_policy()):
            skipped.append(rid)
            continue
        errors = store.upsert_record(record)
        if errors:
            raise ValueError(f'{rid}: {errors}')
        added.append(rid)
    return {'added': added, 'preserved': skipped, 'database': store.location}


if __name__ == '__main__':
    store = create_store()
    try:
        result = seed(store)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        store.close()
