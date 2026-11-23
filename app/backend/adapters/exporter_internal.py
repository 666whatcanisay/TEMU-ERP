"""Internal-standard export only. No Temu import template is produced tonight.

DATA-04: exported files carry an explicit internal marker. Without a verified
live category template we must never label output "ready to import to Temu".
"""
from __future__ import annotations

import csv
import io
import json
from typing import Any

INTERNAL_CSV_MARKER = "# temu-workbench-internal/1.0 — 内部记录，非 Temu 导入模板"
INTERNAL_JSON_MARKER = "temu-workbench-internal/1.0"

CANDIDATE_CSV_COLUMNS = [
    "internal_marker", "candidate_id", "research_market", "internal_decision",
    "merchant_sku", "merchant_group_code", "pieces", "sales_unit",
    "supply_income_amount", "supply_income_currency", "supply_income_confirmed",
    "platform_product_id", "platform_skc_id", "platform_sku_id",
    "cost_purchase", "cost_packaging", "cost_logistics",
    "cost_expected_after_sales", "cost_other_variable",
    "evidence_refs", "synthetic",
    "candidate_json", "sku_json",
]


def build_json_bundle(candidates: list[dict[str, Any]], sources: list[dict[str, Any]],
                       policies: list[dict[str, Any]], feedbacks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": INTERNAL_JSON_MARKER,
        "warning": "内部记录，非 Temu 导入模板；平台字段与枚举待真实类目模板核对。",
        "exported_at": None,  # filled by service
        "records": {
            "candidates": candidates,
            "sources": sources,
            "policies": policies,
            "feedbacks": feedbacks,
        },
    }


def _cost_map(sku: dict[str, Any]) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for item in sku.get("costs") or []:
        out[item["key"]] = (item.get("money") or {}).get("amount")
    return out


def candidates_to_csv_rows(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cand in candidates:
        for sku in cand.get("skus") or []:
            costs = _cost_map(sku)
            income = sku.get("supply_income") or {}
            rows.append({
                "internal_marker": INTERNAL_CSV_MARKER,
                "candidate_id": cand.get("id"),
                "research_market": cand.get("research_market"),
                "internal_decision": cand.get("internal_decision"),
                "merchant_sku": sku.get("merchant_sku"),
                "merchant_group_code": sku.get("merchant_group_code"),
                "pieces": sku.get("pieces"),
                "sales_unit": sku.get("sales_unit"),
                "supply_income_amount": income.get("amount"),
                "supply_income_currency": income.get("currency"),
                "supply_income_confirmed": "true" if income.get("confirmed") else "false",
                "platform_product_id": cand.get("platform_product_id"),
                "platform_skc_id": sku.get("platform_skc_id"),
                "platform_sku_id": sku.get("platform_sku_id"),
                "cost_purchase": costs.get("purchase"),
                "cost_packaging": costs.get("packaging"),
                "cost_logistics": costs.get("logistics"),
                "cost_expected_after_sales": costs.get("expected_after_sales"),
                "cost_other_variable": costs.get("other_variable"),
                "evidence_refs": ";".join(cand.get("evidence_refs") or []),
                "synthetic": "true" if cand.get("synthetic") else "false",
                'candidate_json': json.dumps({k:v for k,v in cand.items() if k != 'skus'}, ensure_ascii=False, separators=(',', ':')),
                'sku_json': json.dumps(sku, ensure_ascii=False, separators=(',', ':')),
            })
    return rows


def write_csv(rows: list[dict[str, Any]]) -> str:
    buffer = io.StringIO()
    buffer.write(INTERNAL_CSV_MARKER + "\n")
    writer = csv.DictWriter(buffer, fieldnames=CANDIDATE_CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def parse_csv(text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (rows, errors). Encoding/column problems are reported per row."""
    errors: list[dict[str, Any]] = []
    lines = text.splitlines()
    if lines and lines[0].startswith("#"):
        lines = lines[1:]
    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    if reader.fieldnames is None:
        return [], [{"row": 0, "error": "empty or unreadable CSV header"}]
    missing = [c for c in CANDIDATE_CSV_COLUMNS if c not in reader.fieldnames and c not in ('candidate_json','sku_json')]
    if missing:
        errors.append({"row": 0, "error": f"missing columns: {', '.join(missing)}"})
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(reader, start=2):
        if None in raw:
            errors.append({'row': index, 'error': 'too many columns'})
            continue
        if not any((v or "").strip() for v in raw.values()):
            continue
        if not (raw.get("merchant_sku") or "").strip():
            errors.append({"row": index, "error": "merchant_sku is required"})
            continue
        if raw.get('internal_marker') != INTERNAL_CSV_MARKER:
            errors.append({'row':index, 'error':'not a recognized internal workbench row'})
            continue
        rows.append(raw)
    return rows, errors


def parse_json_bundle(text: str | dict) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    try:
        bundle = text if isinstance(text, dict) else json.loads(text)
    except json.JSONDecodeError as exc:
        return {}, [{"row": 0, "error": f"invalid JSON: {exc}"}]
    if not isinstance(bundle, dict):
        return {}, [{'row':0,'error':'JSON bundle must be an object'}]
    if bundle.get("schema_version") != INTERNAL_JSON_MARKER:
        errors.append({"row": 0, "error": "not a recognized internal workbench bundle"})
    return bundle, errors
