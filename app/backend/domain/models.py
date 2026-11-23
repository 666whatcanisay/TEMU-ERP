"""Domain DTOs, record factories and lightweight validation.

Contracts: ``contracts/domain.schema.json`` (internal contract, NOT a Temu API
schema). Platform IDs are always preserved as original opaque strings; we never
coerce them through a JS/Number or fabricate category/attribute IDs.
"""
from __future__ import annotations

import re
from decimal import Decimal
from datetime import datetime, timezone
from typing import Any
from . import profit_model

DTO_VERSION = "1.0"

DECISIONS = ("research", "request_sample", "internal_review", "paused", "excluded")
DECISION_LABELS = {
    "research": "继续补证据",
    "request_sample": "联系供应商评估",
    "internal_review": "拟内部评审",
    "paused": "暂缓",
    "excluded": "排除",
}
FEEDBACK_STAGES = (
    "unsubmitted", "selection", "sample", "review", "pricing",
    "first", "stock", "sale", "returned",
)
FEEDBACK_VERIFICATION = ("draft", "needs_review", "human_confirmed")
COST_KEYS = ("purchase", "packaging", "logistics", "expected_after_sales", "other_variable")
MONEY_PATTERN = re.compile(r"^[0-9]+(?:\.[0-9]{1,2})?$")
MEASURE_PATTERN = re.compile(r"^[0-9]+(?:\.[0-9]{1,2})?$")
LENGTH_UNITS = ("cm",)
WEIGHT_UNITS = ("g",)
OPAQUE_ID_TYPES = (str, type(None))


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"


def is_opaque_id(value: Any) -> bool:
    """Platform IDs must stay strings or null; reject numbers that lose precision."""
    return value is None or isinstance(value, str)


def normalize_opaque(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return value
    # A numeric id arriving over JSON must not be silently rounded: keep its
    # exact decimal text when possible, otherwise flag it upstream.
    return str(value)


def validate_money(money: dict[str, Any], path: str, errors: list[str]) -> None:
    if not isinstance(money, dict):
        errors.append(f"{path}: money must be an object")
        return
    amount = money.get("amount")
    if amount is not None and amount != "":
        if not isinstance(amount, str) or not MONEY_PATTERN.fullmatch(amount):
            errors.append(f"{path}.amount: must be a nonnegative decimal string with <=2 decimals")
    if not money.get("currency"):
        errors.append(f"{path}.currency: required")
    if not money.get("sales_unit"):
        errors.append(f"{path}.sales_unit: required")
    if not isinstance(money.get("confirmed"), bool):
        errors.append(f"{path}.confirmed: boolean required")
    if money.get('confirmed') and (amount is None or amount == '' or not money.get('source_ref')):
        errors.append(f'{path}: 确认金额必须填写金额和来源凭证')


def _measure(value: Any, path: str, errors: list[str]) -> None:
    if value is None or value == "":
        return
    if not isinstance(value, str) or not MEASURE_PATTERN.fullmatch(value):
        errors.append(f"{path}: must be a nonnegative decimal string with <=2 decimals")
    elif Decimal(value) <= 0:
        errors.append(f'{path}: 已测量的尺寸/重量必须大于零；未知请留空')


def validate_specs(specs: Any, path: str, errors: list[str]) -> None:
    """FIELD-04: item/set/package dimensions and weight are separate objects
    with explicit units. Missing values stay null; mismatched units or
    unreasonable values are located to this record instead of being filled in."""
    if specs is None:
        return
    if not isinstance(specs, dict):
        errors.append(f"{path}: specs must be an object")
        return
    dims = specs.get("dimensions")
    if dims is not None:
        if not isinstance(dims, dict):
            errors.append(f"{path}.dimensions: object required")
        else:
            for key in ("length_cm", "width_cm", "height_cm"):
                _measure(dims.get(key), f"{path}.dimensions.{key}", errors)
            if dims.get("unit") and dims["unit"] not in LENGTH_UNITS:
                errors.append(f"{path}.dimensions.unit: one of {LENGTH_UNITS}")
    weight = specs.get("weight")
    if weight is not None:
        if not isinstance(weight, dict):
            errors.append(f"{path}.weight: object required")
        else:
            for key in ("net_weight_g", "gross_weight_g"):
                _measure(weight.get(key), f"{path}.weight.{key}", errors)
            if weight.get("unit") and weight["unit"] not in WEIGHT_UNITS:
                errors.append(f"{path}.weight.unit: one of {WEIGHT_UNITS}")
            net, gross = weight.get('net_weight_g'), weight.get('gross_weight_g')
            if isinstance(net, str) and isinstance(gross, str) and MEASURE_PATTERN.fullmatch(net) and MEASURE_PATTERN.fullmatch(gross):
                if Decimal(net) > Decimal(gross):
                    errors.append(f'{path}.weight.gross_weight_g: 毛重不能小于净重')
    for layer in ('item', 'package'):
        if specs.get(layer) is not None:
            validate_specs(specs[layer], f'{path}.{layer}', errors)


def validate_composition(items: Any, path: str, errors: list[str]) -> None:
    """FIELD-05: set composition is kept as explicit line items, not inferred
    from the title string. Classification mapping stays null until a real
    category template confirms it."""
    if items is None:
        return
    if not isinstance(items, list):
        errors.append(f"{path}: pack_composition must be an array")
        return
    for ci, item in enumerate(items):
        cpath = f"{path}[{ci}]"
        if not isinstance(item, dict):
            errors.append(f"{cpath}: composition item must be an object")
            continue
        if not isinstance(item.get("name"), str) or not item["name"].strip():
            errors.append(f"{cpath}.name: required")
        count = item.get("count")
        if not isinstance(count, int) or count < 1:
            errors.append(f"{cpath}.count: integer >= 1 required")
        dims = item.get("product_dimensions_cm")
        if dims is not None:
            if not isinstance(dims, list) or not all(
                isinstance(d, str) and MEASURE_PATTERN.fullmatch(d) for d in dims
            ):
                errors.append(f"{cpath}.product_dimensions_cm: list of nonnegative decimal strings")
        if item.get("classification") is not None and not isinstance(item["classification"], str):
            errors.append(f"{cpath}.classification: string or null")


def validate_bindings(items: Any, path: str, errors: list[str]) -> None:
    """Sale-spec bindings are internal sample组织法; platform parent/spec IDs stay
    opaque null until a real category template returns them."""
    if items is None:
        return
    if not isinstance(items, list):
        errors.append(f"{path}: sale_spec_bindings must be an array")
        return
    for bi, item in enumerate(items):
        bpath = f"{path}[{bi}]"
        if not isinstance(item, dict):
            errors.append(f"{bpath}: binding must be an object")
            continue
        if not isinstance(item.get("name"), str) or not item["name"].strip():
            errors.append(f"{bpath}.name: required")
        if "value" in item and item["value"] is not None and not isinstance(item["value"], str):
            errors.append(f"{bpath}.value: string or null")
        for key in ("parent_spec_id", "spec_id"):
            if not is_opaque_id(item.get(key)):
                errors.append(f"{bpath}.{key}: opaque string or null")


def validate_sku(sku: dict[str, Any], index: int, errors: list[str]) -> None:
    path = f"skus[{index}]"
    if not isinstance(sku, dict):
        errors.append(f'{path}: SKU must be an object')
        return
    if 'profit_plan' in sku:
        errors.extend(profit_model.validate_plan(sku['profit_plan']))
    if not isinstance(sku.get("merchant_sku"), str) or not sku["merchant_sku"].strip():
        errors.append(f"{path}.merchant_sku: required")
    for key in ("platform_sku_id", "platform_skc_id"):
        if not is_opaque_id(sku.get(key)):
            errors.append(f"{path}.{key}: must be an opaque string or null")
    if not isinstance(sku.get("pieces"), int) or sku["pieces"] < 1:
        errors.append(f"{path}.pieces: integer >= 1 required")
    validate_money(sku.get("supply_income") or {}, f"{path}.supply_income", errors)
    validate_specs(sku.get("specs"), f"{path}.specs", errors)
    validate_composition(sku.get("pack_composition"), f"{path}.pack_composition", errors)
    composition = sku.get('pack_composition') or []
    if composition and isinstance(composition, list) and all(isinstance(i, dict) and isinstance(i.get('count'), int) for i in composition):
        if sum(i['count'] for i in composition) != sku.get('pieces'):
            errors.append(f'{path}.pack_composition: 组成数量合计必须等于销售件数 pieces')
    validate_bindings(sku.get("sale_spec_bindings"), f"{path}.sale_spec_bindings", errors)
    costs = sku.get("costs") or []
    seen: set[str] = set()
    for ci, item in enumerate(costs):
        cpath = f"{path}.costs[{ci}]"
        key = item.get("key")
        if key in seen:
            errors.append(f"{cpath}: duplicate cost key {key}")
        seen.add(key)
        validate_money(item.get("money") or {}, f"{cpath}.money", errors)
    missing = [k for k in COST_KEYS if k not in seen]
    if missing:
        errors.append(f"{path}: missing cost categories {', '.join(missing)}")


def validate_candidate(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if record.get("record_type") != "candidate":
        errors.append("record_type must be candidate")
    if not isinstance(record.get("id"), str) or not record["id"].strip():
        errors.append("id: required")
    if record.get("mode_assumption") != "fully_managed":
        errors.append("mode_assumption: only fully_managed is in scope")
    if not is_opaque_id(record.get("platform_product_id")):
        errors.append("platform_product_id: opaque string or null")
    decision = record.get("internal_decision")
    if decision not in DECISIONS:
        errors.append(f"internal_decision: one of {DECISIONS}")
    requirements=record.get('material_requirements') or {}
    if requirements.get('confirmed') and (not requirements.get('source_ref') or not isinstance(requirements.get('required'),list)):
        errors.append('material_requirements: 确认本次材料要求须有来源和明确清单')
    supplier=record.get('supplier') or {}
    if supplier.get('confirmed') and not supplier.get('source_ref'):
        errors.append('supplier.source_ref: 确认供货条件必须附凭证')
    for key,minimum in (('moq',1),('lead_days',0)):
        value=supplier.get(key)
        if value not in (None,''):
            try:
                if str(int(value)) != str(value) or int(value)<minimum:
                    raise ValueError()
            except (ValueError,TypeError):
                errors.append(f'supplier.{key}: 必须为大于等于 {minimum} 的整数')
    if requirements.get('required') and (not isinstance(requirements['required'],list) or any(k not in ('supplier','photos','measure','compliance','template','sample') for k in requirements['required'])):
        errors.append('material_requirements.required: 材料清单包含未知类别')
    skus = record.get("skus") or []
    if not skus:
        errors.append("skus: at least one SKU required")
    for i, sku in enumerate(skus):
        validate_sku(sku, i, errors)
    codes = [s.get('merchant_sku') for s in skus if isinstance(s, dict)]
    if len(set(codes)) != len(codes):
        errors.append('skus.merchant_sku: 同一商品内 SKU 编码不能重复')
    return errors


def validate_source(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if record.get("record_type") != "source":
        errors.append("record_type must be source")
    if not isinstance(record.get("id"), str) or not record["id"].strip():
        errors.append("id: required")
    url = record.get("url")
    if url is not None and not (isinstance(url, str) and url.startswith(("http://", "https://"))):
        errors.append("url: must be http(s) or null")
    if not record.get("locator"):
        errors.append("locator: required")
    if not record.get("verification"):
        errors.append("verification: required")
    return errors


def validate_policy(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if record.get("record_type") != "policy":
        errors.append("record_type must be policy")
    metric = record.get("metric")
    if metric not in (None, "contribution_margin", "cost_markup"):
        errors.append("metric: unknown")
    threshold = record.get("threshold_percent")
    if threshold is not None and threshold != "":
        if not isinstance(threshold, str) or not re.fullmatch(r"\d+(?:\.\d+)?", threshold):
            errors.append("threshold_percent: numeric string or null")
    if not isinstance(record.get("confirmed"), bool):
        errors.append("confirmed: boolean required")
    if record.get('confirmed') and not all(record.get(k) for k in ('metric','threshold_percent','confirmed_by','confirmed_at','source_ref')):
        errors.append('policy: 确认经营门槛需填写口径、门槛、确认人、日期和依据')
    if isinstance(threshold,str) and re.fullmatch(r'\d+(?:\.\d+)?',threshold):
        if record.get('metric')=='contribution_margin' and Decimal(threshold)>=100:
            errors.append('threshold_percent: 收入贡献率门槛必须小于100%')
    return errors


def validate_feedback(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if record.get("record_type") != "feedback":
        errors.append("record_type must be feedback")
    for field in ("id", "candidate_id", "platform_stage", "feedback_text"):
        if not record.get(field):
            errors.append(f"{field}: required")
    if record.get("verification") not in FEEDBACK_VERIFICATION:
        errors.append(f"verification: one of {FEEDBACK_VERIFICATION}")
    if record.get('platform_stage') not in FEEDBACK_STAGES:
        errors.append('platform_stage: unknown stage')
    if record.get('buyer_supply_income'):
        validate_money(record['buyer_supply_income'], 'buyer_supply_income', errors)
    # FLOW-02: a confirmed record needs date + original words + evidence index.
    if record.get("verification") == "human_confirmed":
        if not record.get("feedback_date"):
            errors.append("feedback_date: required for confirmed feedback")
        if not record.get("evidence_ref"):
            errors.append("evidence_ref: required for confirmed feedback")
    return errors


VALIDATORS = {
    "candidate": validate_candidate,
    "source": validate_source,
    "policy": validate_policy,
    "feedback": validate_feedback,
}


def validate_record(record: dict[str, Any]) -> list[str]:
    validator = VALIDATORS.get(record.get("record_type", ""))
    if validator is None:
        return [f"unknown record_type: {record.get('record_type')!r}"]
    return validator(record)


def empty_money(currency: str = "CNY", sales_unit: str = "set") -> dict[str, Any]:
    return {
        "amount": None,
        "currency": currency,
        "sales_unit": sales_unit,
        "confirmed": False,
        "source_ref": None,
    }


def empty_costs() -> list[dict[str, Any]]:
    return [{"key": key, "money": empty_money()} for key in COST_KEYS]


def empty_specs() -> dict[str, Any]:
    return {
        "dimensions": {"length_cm": None, "width_cm": None, "height_cm": None, "unit": "cm"},
        "weight": {"net_weight_g": None, "gross_weight_g": None, "unit": "g"},
    }


def empty_sku(merchant_sku: str, group_code: str | None = None) -> dict[str, Any]:
    return {
        "merchant_sku": merchant_sku,
        "merchant_group_code": group_code,
        "platform_sku_id": None,
        "platform_skc_id": None,
        "sales_unit": "set",
        "pieces": 1,
        "sale_spec_bindings": [],
        "specs": empty_specs(),
        "pack_composition": [],
        "supply_income": empty_money(),
        "costs": empty_costs(),
    }
