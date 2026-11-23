"""Internal dry-run FillPlan builder (ARCH-03).

Produces a structured, read-only plan keyed by stable internal ``field_key`` and
existing frontend locator attributes (``data-testid`` / ``data-*``). The plan
never executes a fill, never contacts a platform, and internal keys are not
Temu page DOM IDs.
"""
from __future__ import annotations

from typing import Any

from ..domain import models

PAGE = "internal-workbench"
TEXT_PRESERVE = "保留原始字符串/十进制文本；不经过 Number 精度转换"


def _locator_attr(attr: str, key: str | None = None) -> dict[str, Any]:
    loc: dict[str, Any] = {"type": "attribute", "name": attr}
    if key is not None:
        loc["key"] = key
    return loc


def _locator_note(text: str) -> dict[str, Any]:
    return {"type": "note", "text": text}


def _step(seq: int, field_key: str, locator: dict[str, Any], value: Any,
          unit: str | None = None, conversion: str | None = None,
          needs_confirm: bool = False, source_ref: str | None = None,
          note: str | None = None) -> dict[str, Any]:
    return {
        "step": seq,
        "page": PAGE,
        "field_key": field_key,
        "locator": locator,
        "value": value,
        "unit": unit,
        "conversion_rule": conversion or TEXT_PRESERVE,
        "readback": {"expected": value},
        "needs_confirm": bool(needs_confirm),
        "source_ref": source_ref,
        "note": note,
    }


def _comp_steps(seq: int, sku_ref: str, comp: list[dict[str, Any]],
                template_ok: bool) -> tuple[list[dict[str, Any]], int]:
    steps: list[dict[str, Any]] = []
    for ci, item in enumerate(comp or []):
        prefix = f"sku.{sku_ref}.pack_composition[{ci}]"
        name = (item or {}).get("name")
        count = (item or {}).get("count")
        dims = (item or {}).get("product_dimensions_cm") or []
        steps.append(_step(seq, f"{prefix}.name", _locator_attr("data-comp-name", str(ci)),
                            name, needs_confirm=not name or not template_ok))
        seq += 1
        steps.append(_step(seq, f"{prefix}.count", _locator_attr("data-comp-count", str(ci)),
                           count, unit="件", needs_confirm=not count or not template_ok))
        seq += 1
        steps.append(_step(seq, f"{prefix}.product_dimensions_cm",
                            _locator_attr("data-comp-dims", str(ci)), dims,
                            unit="cm", conversion="逗号分隔的单件尺寸字符串",
                            needs_confirm=not dims or not template_ok))
        seq += 1
    return steps, seq


def _binding_steps(seq: int, sku_ref: str, bindings: list[dict[str, Any]],
                  template_ok: bool) -> tuple[list[dict[str, Any]], int]:
    steps: list[dict[str, Any]] = []
    for bi, binding in enumerate(bindings or []):
        prefix = f"sku.{sku_ref}.sale_spec_bindings[{bi}]"
        name = (binding or {}).get("name")
        value = (binding or {}).get("value")
        steps.append(_step(seq, f"{prefix}.name", _locator_attr("data-binding-name", str(bi)),
                           name, needs_confirm=not name or not template_ok))
        seq += 1
        steps.append(_step(seq, f"{prefix}.value", _locator_attr("data-binding-value", str(bi)),
                           value, needs_confirm=not value or not template_ok,
                           note="属性枚举与属性 ID 以后台真实类目模板为准"))
        seq += 1
    return steps, seq


def build_fill_plan(candidate: dict[str, Any],
                    field_map_version: str | None = None) -> dict[str, Any]:
    """Build the read-only dry-run plan for one candidate."""
    steps: list[dict[str, Any]] = []
    seq = 1
    template = candidate.get("template_binding") or {}
    template_ok = bool(template.get('category_id') and template.get('source_ref') and template.get('status')=='verified')
    blocking: list[str] = []

    if not template_ok:
        blocking.append('类目模板尚未验证：需真实类目 ID、来源与核验状态；销售属性/枚举待真实模板')

    for sku in candidate.get("skus") or []:
        sku_ref = sku.get("merchant_sku") or "unknown-sku"
        income = sku.get("supply_income") or {}
        income_confirmed = bool(income.get("confirmed"))
        specs = sku.get("specs") or {}
        dims = specs.get("dimensions") or {}
        weight = specs.get("weight") or {}

        steps.append(_step(seq, f"sku.{sku_ref}.merchant_sku",
                           _locator_attr("data-testid", "sku-merchant"),
                           sku.get("merchant_sku"),
                           needs_confirm=not sku.get("merchant_sku")))
        seq += 1
        steps.append(_step(seq, f"sku.{sku_ref}.merchant_group_code",
                           _locator_attr("data-sku-field", "merchant_group_code"),
                           sku.get("merchant_group_code")))
        seq += 1
        steps.append(_step(seq, f"sku.{sku_ref}.pieces",
                           _locator_attr("data-sku-field", "pieces"), sku.get("pieces"),
                           unit=sku.get("sales_unit")))
        seq += 1
        steps.append(_step(seq, f"sku.{sku_ref}.sales_unit",
                           _locator_attr("data-sku-field", "sales_unit"), sku.get("sales_unit"),
                           needs_confirm=not sku.get("sales_unit")))
        seq += 1

        steps.append(_step(seq, f"sku.{sku_ref}.supply_income.amount",
                           _locator_attr("data-income", "amount"), income.get("amount"),
                           unit=income.get("currency"),
                           conversion="两位以内十进制金额字符串，按文本保留",
                           needs_confirm=not income_confirmed,
                           source_ref=income.get("source_ref")))
        seq += 1
        steps.append(_step(seq, f"sku.{sku_ref}.supply_income.currency",
                           _locator_attr("data-income", "currency"), income.get("currency"),
                           needs_confirm=not income_confirmed))
        seq += 1
        steps.append(_step(seq, f"sku.{sku_ref}.supply_income.confirmed",
                           _locator_attr("data-income", "confirmed"), income_confirmed,
                           needs_confirm=not income_confirmed))
        seq += 1
        steps.append(_step(seq, f"sku.{sku_ref}.supply_income.source_ref",
                           _locator_attr("data-income", "source_ref"), income.get("source_ref"),
                           needs_confirm=not income_confirmed))
        seq += 1

        for key in ("length_cm", "width_cm", "height_cm"):
            steps.append(_step(seq, f"sku.{sku_ref}.specs.dimensions.{key}",
                               _locator_attr("data-spec", f"dimensions.{key}"),
                               dims.get(key), unit=dims.get("unit"),
                               conversion="十进制尺寸字符串，带显式单位",
                               needs_confirm=not dims.get(key) or not template_ok))
            seq += 1
        steps.append(_step(seq, f"sku.{sku_ref}.specs.dimensions.unit",
                           _locator_attr("data-spec", "dimensions.unit"), dims.get("unit"),
                           needs_confirm=not dims.get("unit") or not template_ok))
        seq += 1
        for key in ("net_weight_g", "gross_weight_g"):
            steps.append(_step(seq, f"sku.{sku_ref}.specs.weight.{key}",
                               _locator_attr("data-spec", f"weight.{key}"),
                               weight.get(key), unit=weight.get("unit"),
                               conversion="十进制重量字符串，带显式单位",
                               needs_confirm=not weight.get(key) or not template_ok))
            seq += 1
        steps.append(_step(seq, f"sku.{sku_ref}.specs.weight.unit",
                           _locator_attr("data-spec", "weight.unit"), weight.get("unit"),
                           needs_confirm=not weight.get("unit") or not template_ok))
        seq += 1

        for layer in ('item','package'):
            data=specs.get(layer) or {}
            for group,keys,unit in (('dimensions',('length_cm','width_cm','height_cm'),'cm'),('weight',('net_weight_g','gross_weight_g'),'g')):
                for key in keys:
                    value=(data.get(group) or {}).get(key)
                    path=f'{layer}.{group}.{key}'
                    steps.append(_step(seq,f'sku.{sku_ref}.specs.{path}',_locator_attr('data-spec',path),value,
                                       unit=unit,needs_confirm=not value or not template_ok))
                    seq+=1
        comp_steps, seq = _comp_steps(seq, sku_ref, sku.get("pack_composition") or [], template_ok)
        steps.extend(comp_steps)
        bind_steps, seq = _binding_steps(seq, sku_ref, sku.get("sale_spec_bindings") or [], template_ok)
        steps.extend(bind_steps)

        # Platform IDs are returned by the platform; never fabricated locally.
        for id_key in ("platform_product_id", "platform_skc_id", "platform_sku_id"):
            steps.append(_step(seq, f"sku.{sku_ref}.{id_key}",
                               _locator_note("平台返回后填写；本地不提供平台页面定位属性"),
                               candidate.get(id_key) if id_key == "platform_product_id" else sku.get(id_key),
                               needs_confirm=True,
                               note="空值待平台/真实模板返回，不填示例 ID"))
            seq += 1

        if not income_confirmed:
            blocking.append(f"SKU {sku_ref} 供货收入未确认，金额仅作情景")
        if any(not (c.get("money") or {}).get("confirmed") for c in (sku.get("costs") or [])):
            blocking.append(f"SKU {sku_ref} 存在未确认成本项")

    return {
        "plan_type": "rpa_dry_run",
        "status": "dry_run_only",
        "page_version": f"{PAGE}/{models.DTO_VERSION}",
        "field_mapping_version": field_map_version,
        "candidate_id": candidate.get("id"),
        "note": "只读填写计划；不执行真实填写，不向平台发送。内部 field_key 与定位属性不是 Temu 页面 DOM ID；平台 ID 与类目字段待真实模板/授权只读环境核对。",
        "steps": steps,
        "blocking": blocking,
    }
