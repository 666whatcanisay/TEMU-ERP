"""Portable source/contract checks; no network or credentials required."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
required = [
    "README.md", "RUNBOOK.md", "docs/WORKFLOW.md", "docs/ARCHITECTURE.md",
    "docs/PROFIT_MODEL.md", "docs/INTERVIEW.md", "research/sources.json",
    "contracts/domain.schema.json", "contracts/temu_field_map.json", "fixtures/demo-catalog.json",
]
for name in required:
    path = ROOT / name
    assert path.is_file() and path.stat().st_size > 0, f"missing/empty: {name}"

json_paths = []
for folder in ["research", "contracts", "fixtures"]:
    json_paths.extend((ROOT / folder).glob("*.json"))
for path in json_paths:
    json.loads(path.read_text(encoding="utf-8"))

sources = json.loads((ROOT / "research/sources.json").read_text(encoding="utf-8"))["sources"]
source_ids = {source["id"] for source in sources}
assert len(source_ids) == len(sources), "duplicate source ID"
for source in sources:
    if source["level"] != "internal_method":
        assert source.get("url", "").startswith("https://"), f"missing source URL: {source['id']}"

mapping = json.loads((ROOT / "contracts/temu_field_map.json").read_text(encoding="utf-8"))
for item in mapping["mappings"]:
    assert item["source_id"] in source_ids, f"unknown source: {item}"
    assert item.get("note"), f"missing mapping boundary: {item}"

candidate = json.loads((ROOT / "fixtures/synthetic-candidate.json").read_text(encoding="utf-8"))
assert candidate["platform_product_id"] is None
for sku in candidate["skus"]:
    assert sku["platform_sku_id"] is None
    assert sku["platform_skc_id"] is None
    for item in sku["costs"]:
        assert isinstance(item["money"]["amount"], str)

schema_status = "not executed (optional jsonschema dependency unavailable)"
try:
    import jsonschema
except ImportError:
    pass
else:
    schema = json.loads((ROOT / "contracts/domain.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(schema)
    for path in (ROOT / "fixtures").glob("*.json"):
        document = json.loads(path.read_text(encoding="utf-8"))
        for record in document.get('records', [document]):
            validator.validate(record)
    schema_status = "all fixtures validated with jsonschema"

# Project-authored files must never contain actual API credentials.
assert ".env" in (ROOT / ".gitignore").read_text(encoding="utf-8"), "local credentials must stay ignored"
print(json.dumps({"required_files": len(required), "json_files": len(json_paths), "sources": len(sources), "field_mappings": len(mapping["mappings"]), "schema_validation": schema_status}, ensure_ascii=False))
