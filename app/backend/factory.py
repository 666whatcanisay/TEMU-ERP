"""Wire storage, registry and adapters into a service instance."""
from __future__ import annotations

import json
from pathlib import Path

from .adapters.collector_http import HttpEvidenceCollector
from .adapters.extraction_llm import DSHExtractor, DeepSeekApiExtractor
from .adapters.extraction_rules import RuleExtractor
from .adapters.store_factory import create_store
from .application.services import WorkbenchService
from . import config


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_service(seed: bool = True) -> WorkbenchService:
    store = create_store()
    collector = HttpEvidenceCollector(config.CACHE_DIR / "snapshots")
    rule_extractor = RuleExtractor()
    dsh = DSHExtractor()
    deepseek = DeepSeekApiExtractor()

    registry_sources = _load_json(config.RESEARCH_DIR / "sources.json").get("sources", [])
    field_map = _load_json(config.CONTRACTS_DIR / "temu_field_map.json")

    service = WorkbenchService(
        store=store,
        collector=collector,
        rule_extractor=rule_extractor,
        dsh=dsh,
        deepseek=deepseek,
        registry_sources=registry_sources,
        field_map=field_map,
    )

    # Persist honest default adapter statuses. Adapters that have not yet run
    # against a real page are marked needs_review, not succeeded.
    captured=[s for s in store.list_records('source') if s.get('sha256') and s.get('snapshot_ref') and Path(s['snapshot_ref']).is_file()]
    store.set_adapter_status('collector_http','succeeded' if captured else 'needs_review',
        {'detail':f'已保存 {len(captured)} 条公开页面快照；成功状态指最近采集结果，不代表持续在线。' if captured else '公开只读采集已装配，等待读取页面。'})
    extracted=[s for s in captured if (s.get('facts') or {}).get('extracted_candidates')]
    store.set_adapter_status('extractor_rule','succeeded' if extracted else 'needs_review',
        {'detail':f'{len(extracted)} 条快照有候选字段；候选仍需对照原文核对。'})
    store.set_adapter_status("extractor_dsh", dsh.status()["status"], dsh.status())
    store.set_adapter_status("extractor_deepseek", deepseek.status()["status"], deepseek.status())
    store.set_adapter_status("category_template", "not_configured",
                             {"detail": "等待公司当前全托管类目脱敏模板或授权只读结果。"})
    store.set_adapter_status("platform_read", "not_configured",
                             {"detail": "未配置已授权的 Temu 只读连接。"})
    store.set_adapter_status("submission_exporter", "succeeded",
                             {"detail": "仅导出内部标准 CSV/JSON，非平台导入模板。"})
    store.set_adapter_status("rpa_fill", "not_configured",
                             {"detail": "仅预留 dry-run FillPlan；不执行真实提报填写。"})

    if seed:
        fixtures = {
            "source": _load_json(config.FIXTURES_DIR / "public-source-ikea.json"),
            "candidate": _load_json(config.FIXTURES_DIR / "synthetic-candidate.json"),
            "policy": _load_json(config.FIXTURES_DIR / "company-policy.example.json"),
            "feedback": _load_json(config.FIXTURES_DIR / "buyer-feedback-synthetic.json"),
        }
        service.seed_if_empty(fixtures)
    return service
