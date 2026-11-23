import json
import tempfile
import unittest
from pathlib import Path

from app.backend.adapters.storage_sqlite import SQLiteStore
from app.backend.application.services import WorkbenchService
from app.backend.domain.ports import AdapterResult
from app.backend import config

FIX = config.FIXTURES_DIR


class _FakeCollector:
    def __init__(self, snapshot_file: str):
        self.snapshot_file = snapshot_file

    def collect(self, request):
        return AdapterResult("succeeded", payload={
            "title": "Test Title", "snapshot_ref": self.snapshot_file,
            "sha256": "abc123", "file_path": self.snapshot_file,
        })


class _FakeExtractor:
    def extract(self, request):
        return AdapterResult("succeeded", payload={"fields": {
            "title": {"value": "Test Title", "locator": "<title>",
                      "extraction_method": "rule", "confirmation": "extracted_candidate"},
            "display_price": {"value": "5.00", "locator": "first price token",
                              "extraction_method": "rule", "confirmation": "extracted_candidate"},
        }})


def load(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.store = SQLiteStore(Path(self.tmp.name) / "svc.db")
        self.service = WorkbenchService(store=self.store)
        self.service.seed_if_empty({
            "source": load("public-source-ikea.json"),
            "candidate": load("synthetic-candidate.json"),
            "policy": load("company-policy.example.json"),
            "feedback": load("buyer-feedback-synthetic.json"),
        })

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_candidate_view_keeps_unconfirmed_policy_scenario(self):
        detail = self.service.get_candidate("DEMO-ORG-001")
        self.assertIsNotNone(detail)
        self.assertIn(detail["skus"][0]["evaluation"]["status"],
                      ("NEEDS_POLICY", "NEEDS_POLICY_CONFIRMATION"))

    def test_ikea_source_not_comparable(self):
        detail = self.service.get_candidate("DEMO-ORG-001")
        comp = detail["evidence"][0]["comparability"]
        self.assertFalse(comp["comparable"])
        self.assertTrue(comp["reasons"])

    def test_sales_kept_null(self):
        detail = self.service.get_candidate("DEMO-ORG-001")
        self.assertIsNone(detail["evidence"][0]["sales"]["sales"])

    def test_pause_and_restore_decision(self):
        errors = self.service.set_decision("DEMO-ORG-001", "paused", "低于门槛，暂缓", "tester")
        self.assertEqual(errors, [])
        cand = self.store.get_record("candidate", "DEMO-ORG-001")
        self.assertEqual(cand["internal_decision"], "paused")
        self.assertEqual(cand["decision_history"][-1]["reason"], "低于门槛，暂缓")
        errors = self.service.restore_decision("DEMO-ORG-001", "tester")
        self.assertEqual(errors, [])
        cand = self.store.get_record("candidate", "DEMO-ORG-001")
        self.assertEqual(cand["internal_decision"], "research")

    def test_confirmed_feedback_without_evidence_downgrades_to_draft(self):
        result = self.service.add_feedback({
            "candidate_id": "DEMO-ORG-001", "platform_stage": "pricing",
            "feedback_text": "假设建议价 24 元", "verification": "human_confirmed",
        })
        self.assertEqual(result["status"], "succeeded")
        fb = self.store.get_record("feedback", result["id"])
        self.assertEqual(fb["verification"], "draft")

    def test_submission_package_is_internal_only(self):
        result = self.service.build_submission("DEMO-ORG-001")
        self.assertEqual(result["status"], "succeeded")
        package = result["package"]
        self.assertIn("非 Temu 导入模板", package["banner"])
        self.assertTrue(package["unverified_items"])

    def test_confirmed_policy_and_confirmed_costs_evaluate(self):
        policy = {
            "record_type": "policy", "metric": "contribution_margin", "threshold_percent": "15",
            "confirmed": True, "confirmed_by": "owner", "confirmed_at": "2026-11-23",
            "source_ref": "fixture:policy", "version": "demo-v1",
        }
        self.service.save_policy(policy)
        cand = load("synthetic-candidate.json")
        for sku in cand["skus"]:
            sku["supply_income"]["confirmed"] = True
            sku["supply_income"]["source_ref"] = "fixture:quote"
            for cost in sku["costs"]:
                cost["money"]["confirmed"] = True
                cost["money"]["source_ref"] = "fixture:cost"
        self.service.save_candidate(cand)
        detail = self.service.get_candidate("DEMO-ORG-001")
        self.assertEqual(detail["skus"][0]["evaluation"]["status"], "MEETS_THRESHOLD")

    def test_buyer_price_affects_only_buyer_evaluation(self):
        """FIN-08: buyer suggested price recomputes a separate evaluation;
        original supply income and costs are never adjusted to fit a threshold."""
        detail = self.service.get_candidate("DEMO-ORG-001")
        view = detail["skus"][0]
        self.assertEqual(view["sku"]["supply_income"]["amount"], "28.00")
        self.assertEqual(view["buyer_supply_income"]["amount"], "24.00")
        self.assertIn("buyer_evaluation", view)
        original_costs = [c["money"]["amount"] for c in view["sku"]["costs"]]
        self.assertEqual(original_costs, ["18.00", "1.00", "2.00", "1.00", "1.50"])

    def test_multi_sku_with_specs_and_composition_roundtrips(self):
        cand = load("synthetic-candidate.json")
        base = cand["skus"][0]
        base["specs"] = {
            "dimensions": {"length_cm": "28.0", "width_cm": "9.0", "height_cm": "5.0", "unit": "cm"},
            "weight": {"net_weight_g": "120", "gross_weight_g": "135", "unit": "g"},
        }
        second = json.loads(json.dumps(base))
        second["merchant_sku"] = "ORG-CLR-007"
        second['pieces'] = 2
        second["pack_composition"] = [
            {"name": "混合收纳盒", "count": 2, "product_dimensions_cm": ["20", "9", "5"], "classification": None},
        ]
        cand["skus"].append(second)
        errors = self.service.save_candidate(cand)
        self.assertEqual(errors, [])
        loaded = self.store.get_record("candidate", "DEMO-ORG-001")
        self.assertEqual(len(loaded["skus"]), 2)
        self.assertEqual(loaded["skus"][0]["specs"]["weight"]["net_weight_g"], "120")
        self.assertEqual(loaded["skus"][1]["pack_composition"][0]["name"], "混合收纳盒")

    def test_invalid_specs_and_composition_are_rejected_with_paths(self):
        cand = load("synthetic-candidate.json")
        cand["skus"][0]["specs"] = {
            "dimensions": {"length_cm": "-2", "width_cm": "9", "height_cm": "5", "unit": "inch"},
            "weight": {"net_weight_g": "abc", "gross_weight_g": None, "unit": "g"},
        }
        cand["skus"][0]["pack_composition"] = [{"name": "", "count": 0, "product_dimensions_cm": ["x"]}]
        errors = self.service.save_candidate(cand)
        self.assertTrue(any("specs.dimensions.length_cm" in e for e in errors))
        self.assertTrue(any("specs.dimensions.unit" in e for e in errors))
        self.assertTrue(any("specs.weight.net_weight_g" in e for e in errors))
        self.assertTrue(any("pack_composition[0].name" in e for e in errors))
        self.assertTrue(any("pack_composition[0].count" in e for e in errors))

    def test_spec_bindings_roundtrip_and_reject_invalid(self):
        cand = load("synthetic-candidate.json")
        cand["skus"][0]["sale_spec_bindings"] = [
            {"name": "颜色", "value": "透明", "parent_spec_id": None, "spec_id": None, "source_ref": None},
        ]
        errors = self.service.save_candidate(cand)
        self.assertEqual(errors, [])
        loaded = self.store.get_record("candidate", "DEMO-ORG-001")
        self.assertEqual(loaded["skus"][0]["sale_spec_bindings"][0]["value"], "透明")

        bad = load("synthetic-candidate.json")
        bad["skus"][0]["sale_spec_bindings"] = [
            {"name": "", "value": "x", "spec_id": 12345},
        ]
        errors = self.service.save_candidate(bad)
        self.assertTrue(any("sale_spec_bindings[0].name" in e for e in errors))
        self.assertTrue(any("sale_spec_bindings[0].spec_id" in e for e in errors))

    def test_collected_extracted_candidates_kept_separate_and_visible(self):
        """SRC-03: rule/LLM candidates are stored on the source, marked pending,
        exposed in the linked evidence view, and never overwrite confirmed fields."""
        snap = Path(self.tmp.name) / "snap.html"
        snap.write_text("<title>x</title>", encoding="utf-8")
        self.service.collector = _FakeCollector(str(snap))
        self.service.rule_extractor = _FakeExtractor()
        result = self.service.collect_page("test-001", "https://example.com/item",
                                           ("example.com",))
        self.assertEqual(result.status, "succeeded")
        src = self.store.get_record("source", "WEB-test-001")
        cands = src["facts"]["extracted_candidates"]
        self.assertEqual(cands["display_price"]["confirmation"], "extracted_candidate")

        cand = self.store.get_record("candidate", "DEMO-ORG-001")
        cand["evidence_refs"].append("WEB-test-001")
        self.service.save_candidate(cand)
        detail = self.service.get_candidate("DEMO-ORG-001")
        linked = [e for e in detail["evidence"] if e["source"]["id"] == "WEB-test-001"]
        self.assertTrue(linked)
        self.assertEqual(linked[0]["source"]["facts"]["extracted_candidates"]["title"]["value"],
                         "Test Title")
        # Extracted candidate must not overwrite the confirmed candidate record.
        self.assertEqual(detail["candidate"]["skus"][0]["merchant_sku"], "ORG-CLR-006")

    def test_fillplan_is_readonly_and_key_based(self):
        result = self.service.build_fill_plan("DEMO-ORG-001")
        self.assertEqual(result["status"], "succeeded")
        plan = result["plan"]
        self.assertEqual(plan["status"], "dry_run_only")
        self.assertTrue(plan["steps"])
        coordinate_keys = {"x", "y", "coordinate", "screen_x", "screen_y"}
        for step in plan["steps"]:
            self.assertTrue(step["field_key"])
            self.assertIn("locator", step)
            self.assertNotIn(step["locator"].get("type"), ("coordinate",))
            self.assertFalse(coordinate_keys & set(step.keys()))
        id_steps = [s for s in plan["steps"] if "platform_" in s["field_key"]]
        self.assertTrue(id_steps)
        for s in id_steps:
            self.assertIsNone(s["value"])
            self.assertTrue(s["needs_confirm"])
        income = [s for s in plan["steps"] if s["field_key"].endswith("supply_income.amount")]
        self.assertTrue(income[0]["needs_confirm"])
        sub = self.service.build_submission("DEMO-ORG-001")
        self.assertIn("rpa_dry_run_plan", sub["package"])
        self.assertEqual(sub["package"]["rpa_dry_run_plan"]["status"], "dry_run_only")

    def test_long_platform_id_roundtrip(self):
        cand = load("synthetic-candidate.json")
        cand["platform_product_id"] = "9876543210987654321"
        cand["skus"][0]["platform_sku_id"] = "1234567890123456789"
        errors = self.service.save_candidate(cand)
        self.assertEqual(errors, [])
        loaded = self.store.get_record("candidate", "DEMO-ORG-001")
        self.assertEqual(loaded["platform_product_id"], "9876543210987654321")
        self.assertEqual(loaded["skus"][0]["platform_sku_id"], "1234567890123456789")


if __name__ == "__main__":
    unittest.main()
