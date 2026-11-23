import json
import tempfile
import unittest
from pathlib import Path

from app.backend.adapters.storage_sqlite import SQLiteStore
from app.backend.domain import models


def candidate_record(cid="TEST-001", platform_id=None):
    return {
        "record_type": "candidate", "id": cid, "mode_assumption": "fully_managed",
        "mode_confirmed": False, "research_market": "DE", "platform_product_id": platform_id,
        "category_path_ids": [], "template_binding": {"status": "unverified"},
        "evidence_refs": [], "internal_decision": "research", "decision_history": [],
        "skus": [{
            "merchant_sku": "TEST-SKU-1", "merchant_group_code": "TEST",
            "platform_sku_id": None, "platform_skc_id": None, "sales_unit": "set", "pieces": 6,
            "sale_spec_bindings": [], "pack_composition": [],
            "supply_income": models.empty_money(),
            "costs": [{"key": k, "money": models.empty_money()} for k in models.COST_KEYS],
        }],
    }


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.store = SQLiteStore(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_upsert_and_read_back(self):
        errors = self.store.upsert_record(candidate_record())
        self.assertEqual(errors, [])
        loaded = self.store.get_record("candidate", "TEST-001")
        self.assertEqual(loaded["id"], "TEST-001")
        self.assertEqual(len(loaded["skus"]), 1)

    def test_long_opaque_id_preserved_as_string(self):
        long_id = "1234567890123456789"
        self.store.upsert_record(candidate_record(platform_id=long_id))
        loaded = self.store.get_record("candidate", "TEST-001")
        self.assertEqual(loaded["platform_product_id"], long_id)
        self.assertIsInstance(loaded["platform_product_id"], str)

    def test_revision_history(self):
        self.store.add_revision("TEST-001", "TEST-SKU-1", "supply_income", None, "28.00", "tester", "manual")
        history = self.store.revision_history("TEST-001")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["field_key"], "supply_income")

    def test_backup_and_restore(self):
        self.store.upsert_record(candidate_record())
        backup = Path(self.tmp.name) / "backup.db"
        self.store.backup(backup)
        self.assertTrue(backup.is_file())
        errors = self.store.restore(str(backup))
        self.assertEqual(errors, [])
        self.assertIsNotNone(self.store.get_record("candidate", "TEST-001"))

    def test_validation_rejects_bad_record(self):
        bad = candidate_record()
        bad["skus"][0]["platform_sku_id"] = 12345
        errors = self.store.upsert_record(bad)
        self.assertTrue(any("platform_sku_id" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
