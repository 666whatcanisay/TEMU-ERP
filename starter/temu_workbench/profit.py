"""Deterministic supply-offer calculations. No UI, database, or network dependencies.

Percentages are company policy, never hardcoded platform requirements.
MEETS_THRESHOLD concerns this financial criterion only, not market fit or approval.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_CEILING, localcontext
import re


REQUIRED_COSTS = frozenset({
    "purchase", "packaging", "logistics", "expected_after_sales", "other_variable"
})
MONEY_PATTERN = re.compile(r"^[0-9]+(?:\.[0-9]{1,2})?$")


@dataclass(frozen=True)
class MoneyInput:
    amount: str | None
    currency: str = "CNY"
    sales_unit: str = "set"
    confirmed: bool = False
    source_ref: str | None = None


@dataclass(frozen=True)
class CostItem:
    key: str
    money: MoneyInput


@dataclass(frozen=True)
class BusinessPolicy:
    metric: str  # contribution_margin or cost_markup
    threshold_percent: str | None
    confirmed: bool = False
    confirmed_by: str | None = None
    confirmed_at: str | None = None
    source_ref: str | None = None
    version: str = "draft"


@dataclass(frozen=True)
class Evaluation:
    status: str
    reasons: tuple[str, ...] = ()
    values: dict[str, str | None] = field(default_factory=dict)


def _money(value: str | None) -> Decimal:
    if value is None or value == "":
        raise ValueError("missing amount")
    if not isinstance(value, str) or len(value) > 32 or not MONEY_PATTERN.fullmatch(value):
        raise ValueError("money must be a nonnegative decimal string with <=2 decimals")
    parsed = Decimal(value)
    if not parsed.is_finite():
        raise ValueError("money must be finite")
    return parsed


def _policy_target(policy: BusinessPolicy) -> Decimal:
    if policy.metric not in {"contribution_margin", "cost_markup"}:
        raise ValueError("unknown metric")
    try:
        if not isinstance(policy.threshold_percent, str):
            raise ValueError("missing threshold")
        target = Decimal(policy.threshold_percent)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("invalid threshold") from exc
    if not target.is_finite() or target < 0:
        raise ValueError("threshold must be finite and nonnegative")
    if policy.metric == "contribution_margin" and target >= 100:
        raise ValueError("contribution-margin threshold must be below 100%")
    return target / Decimal(100)


def evaluate_offer(
    price: MoneyInput,
    costs: list[CostItem],
    policy: BusinessPolicy | None = None,
) -> Evaluation:
    keys = [item.key for item in costs]
    if len(keys) != len(set(keys)):
        return Evaluation("INVALID_INPUT", ("duplicate cost key",))
    missing = REQUIRED_COSTS.difference(keys)
    if missing:
        return Evaluation("NEEDS_DATA", tuple("missing cost: " + key for key in sorted(missing)))
    all_money = [price] + [item.money for item in costs]
    if any(item.amount is None or item.amount == "" for item in all_money):
        return Evaluation("NEEDS_DATA", ("unknown amounts are not zero",))
    if not price.currency or not price.sales_unit:
        return Evaluation("NEEDS_DATA", ("currency and sales unit required",))
    if any(item.currency != price.currency for item in all_money):
        return Evaluation("UNIT_MISMATCH", ("normalize currency with sourced exchange rate first",))
    if any(item.sales_unit != price.sales_unit for item in all_money):
        return Evaluation("UNIT_MISMATCH", ("normalize sales units first",))
    try:
        p = _money(price.amount)
        parsed_costs = [_money(item.money.amount) for item in costs]
        if p <= 0:
            raise ValueError("supply income must be greater than zero")
    except (ValueError, InvalidOperation) as exc:
        return Evaluation("INVALID_INPUT", (str(exc),))

    with localcontext() as ctx:
        ctx.prec = 50
        c = sum(parsed_costs, Decimal(0))
        contribution = p - c
        values: dict[str, str | None] = {
            "currency": price.currency,
            "sales_unit": price.sales_unit,
            "supply_income": str(p),
            "variable_cost": str(c),
            "contribution": str(contribution),
            "contribution_margin": str(contribution / p),
            "cost_markup": str(contribution / c) if c else None,
            "minimum_supply_income": None,
            "scope": "before fixed overhead and taxes not included in cost items",
        }
        if policy is None or policy.threshold_percent is None:
            return Evaluation("NEEDS_POLICY", ("company metric and threshold are not configured",), values)
        try:
            target = _policy_target(policy)
        except ValueError as exc:
            return Evaluation("INVALID_POLICY", (str(exc),), values)
        if policy.metric == "cost_markup" and c == 0:
            return Evaluation("UNDEFINED_METRIC", ("markup cannot be divided by zero cost",), values)

        denominator = p if policy.metric == "contribution_margin" else c
        minimum = c / (1 - target) if policy.metric == "contribution_margin" else c * (1 + target)
        values["minimum_supply_income"] = str(minimum.quantize(Decimal("0.01"), rounding=ROUND_CEILING))
        policy_confirmed = all((policy.confirmed, policy.confirmed_by, policy.confirmed_at, policy.source_ref))
        if not policy_confirmed:
            return Evaluation("NEEDS_POLICY_CONFIRMATION", ("scenario only; company policy is not confirmed",), values)
        if any(not item.confirmed or not item.source_ref for item in all_money):
            return Evaluation("NEEDS_DATA_CONFIRMATION", ("scenario only; price or cost provenance is unconfirmed",), values)

        # Compare unrounded operands. A display rounded to 50% must not pass 50%.
        passes = contribution >= denominator * target
        return Evaluation(
            "MEETS_THRESHOLD" if passes else "BELOW_THRESHOLD",
            ("financial criterion only; market, supplier, template, materials and human review remain separate",),
            values,
        )
