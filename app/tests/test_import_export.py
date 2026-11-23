import json
import tempfile
import unittest
from pathlib import Path

from app.backend.adapters.storage_sqlite import SQLiteStore
from app.backend.application.services import WorkbenchService
from app.backend import config

FIX = config.FIXTURES_DIR


def load(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def make_service(tmp: str, name: str) -> WorkbenchService:
    store = SQLiteStore(Path(tmp) / name)
    return WorkbenchService(store=store)


class ImportExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.src = make_service(self.tmp.name, "src.db")
        self.src.seed_if_empty({
            "source": load("public-source-ikea.json"),
            "candidate": load("synthetic-candidate.json"),
            "policy": load("company-policy.example.json"),
            "feedback": load("buyer-feedback-synthetic.json"),
        })

    def tearDown(self):
        self.src.store.close()
        self.tmp.cleanup()

    def test_json_roundtrip_preserves_records_and_long_id(self):
        cand = load("synthetic-candidate.json")
        cand["platform_product_id"] = "5555555555555555555"
        self.src.save_candidate(cand)
        bundle = self.src.export_bundle("json")
        self.assertEqual(bundle["format"], "json")

        dst = make_service(self.tmp.name, "dst1.db")
        report = dst.import_bundle("json", json.dumps(bundle["content"], ensure_ascii=False))
        self.assertFalse(report["errors"], report["errors"])
        ids = [r["id"] for r in report["imported"] if r["record_type"] == "candidate"]
        self.assertIn("DEMO-ORG-001", ids)
        loaded = dst.store.get_record("candidate", "DEMO-ORG-001")
        self.assertEqual(loaded["platform_product_id"], "5555555555555555555")

    def test_json_roundtrip_preserves_specs_and_composition(self):
        cand = load("synthetic-candidate.json")
        cand["skus"][0]["specs"] = {
            "dimensions": {"length_cm": "28", "width_cm": "9", "height_cm": "5", "unit": "cm"},
            "weight": {"net_weight_g": "120", "gross_weight_g": "135", "unit": "g"},
        }
        cand["skus"][0]["pack_composition"] = [
            {"name": "相同尺寸收纳盒", "count": 6, "product_dimensions_cm": ["28", "9", "5"], "classification": None},
        ]
        self.src.save_candidate(cand)
        bundle = self.src.export_bundle("json")
        dst = make_service(self.tmp.name, "dst5.db")
        report = dst.import_bundle("json", json.dumps(bundle["content"], ensure_ascii=False))
        self.assertFalse(report["errors"], report["errors"])
        loaded = dst.store.get_record("candidate", "DEMO-ORG-001")
        self.assertEqual(loaded["skus"][0]["specs"]["dimensions"]["length_cm"], "28")
        self.assertEqual(loaded["skus"][0]["pack_composition"][0]["count"], 6)
        again = dst.import_bundle("json", json.dumps(bundle["content"], ensure_ascii=False))
        self.assertTrue(again["duplicates"])
        dst.store.close()

    def test_csv_export_and_import_roundtrip(self):
        csv_text = self.src.export_bundle("csv")["content"]
        self.assertIn("非 Temu 导入模板", csv_text)
        dst = make_service(self.tmp.name, "dst2.db")
        report = dst.import_bundle("csv", csv_text)
        self.assertFalse(report["errors"], report["errors"])
        candidates = [r for r in report["imported"] if r["record_type"] == "candidate"]
        self.assertEqual(len(candidates), 1)
        loaded = dst.store.get_record("candidate", "DEMO-ORG-001")
        self.assertEqual(loaded["skus"][0]["merchant_sku"], "ORG-CLR-006")
        dst.store.close()

    def test_csv_reports_bad_rows(self):
        dst = make_service(self.tmp.name, "dst3.db")
        report = dst.import_bundle("csv", "col1,col2\na,b\n")
        self.assertTrue(report["errors"])
        dst.store.close()

    def test_json_rejects_foreign_bundle(self):
        dst = make_service(self.tmp.name, "dst4.db")
        report = dst.import_bundle("json", json.dumps({"records": {}}))
        self.assertTrue(report["errors"])
        dst.store.close()


if __name__ == "__main__":
    unittest.main()
