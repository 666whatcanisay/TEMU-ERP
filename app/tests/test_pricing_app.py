import unittest
from dataclasses import replace
from decimal import Decimal

from app.backend.domain.pricing import (
    BusinessPolicy, CostItem, MoneyInput, evaluate_offer,
)
from app.backend.domain.ports import ExtractRequest, UnconfiguredExtractor


def confirmed(amount, **kwargs):
    return MoneyInput(amount, confirmed=True, source_ref="fixture:company-quote", **kwargs)


def costs(total="20.00"):
    return [CostItem("purchase", confirmed(total))] + [
        CostItem(key, confirmed("0.00"))
        for key in ["packaging", "logistics", "expected_after_sales", "other_variable"]
    ]


def policy(metric="contribution_margin", threshold="50"):
    return BusinessPolicy(metric, threshold, True, "synthetic-owner", "2026-11-23", "fixture:policy", "demo-v1")


class AppPricingTests(unittest.TestCase):
    def test_margin_and_markup_are_distinct(self):
        a = evaluate_offer(confirmed("30"), costs(), policy())
        b = evaluate_offer(confirmed("30"), costs(), policy("cost_markup"))
        self.assertEqual(a.status, "BELOW_THRESHOLD")
        self.assertEqual(b.status, "MEETS_THRESHOLD")
        self.assertEqual(Decimal(b.values["cost_markup"]), Decimal("0.5"))

    def test_reference_offer_and_floor_round_up(self):
        result = evaluate_offer(confirmed("28"), costs("23.50"), policy(threshold="15"))
        self.assertEqual(result.status, "MEETS_THRESHOLD")
        self.assertEqual(Decimal(result.values["contribution"]), Decimal("4.50"))
        self.assertEqual(result.values["minimum_supply_income"], "27.65")

    def test_buyer_price_near_cost(self):
        result = evaluate_offer(confirmed("24"), costs("23.50"), policy(threshold="15"))
        self.assertEqual(result.status, "BELOW_THRESHOLD")
        self.assertEqual(Decimal(result.values["contribution"]), Decimal("0.50"))

    def test_negative_contribution(self):
        result = evaluate_offer(confirmed("22"), costs("23.50"), policy(threshold="15"))
        self.assertEqual(Decimal(result.values["contribution"]), Decimal("-1.50"))
        self.assertEqual(result.status, "BELOW_THRESHOLD")

    def test_missing_cost_not_zero(self):
        rows = costs()
        rows[1] = CostItem("packaging", confirmed(None))
        self.assertEqual(evaluate_offer(confirmed("30"), rows, policy()).status, "NEEDS_DATA")

    def test_unconfirmed_zero_does_not_pass(self):
        rows = costs()
        rows[1] = CostItem("packaging", MoneyInput("0"))
        self.assertEqual(evaluate_offer(confirmed("100"), rows, policy()).status, "NEEDS_DATA_CONFIRMATION")

    def test_currency_mismatch(self):
        self.assertEqual(evaluate_offer(confirmed("100", currency="EUR"), costs(), policy()).status, "UNIT_MISMATCH")

    def test_zero_income_invalid(self):
        self.assertEqual(evaluate_offer(confirmed("0"), costs(), policy()).status, "INVALID_INPUT")

    def test_zero_cost_markup_undefined(self):
        self.assertEqual(evaluate_offer(confirmed("1"), costs("0"), policy("cost_markup")).status, "UNDEFINED_METRIC")

    def test_margin_cannot_target_100(self):
        self.assertEqual(evaluate_offer(confirmed("30"), costs(), policy(threshold="100")).status, "INVALID_POLICY")

    def test_display_rounding_cannot_change_decision(self):
        result = evaluate_offer(confirmed("20000"), costs("10001"), policy())
        self.assertEqual(result.status, "BELOW_THRESHOLD")

    def test_exact_threshold_passes(self):
        self.assertEqual(evaluate_offer(confirmed("40"), costs(), policy()).status, "MEETS_THRESHOLD")

    def test_unconfigured_adapter_is_honest(self):
        result = UnconfiguredExtractor().extract(ExtractRequest("task", "snapshot", ("title",)))
        self.assertEqual(result.status, "not_configured")
        self.assertEqual(result.payload, {})

    def test_unconfirmed_policy_is_scenario_only(self):
        p = replace(policy(), confirmed_by=None)
        self.assertEqual(evaluate_offer(confirmed("100"), costs(), p).status, "NEEDS_POLICY_CONFIRMATION")


if __name__ == "__main__":
    unittest.main()
