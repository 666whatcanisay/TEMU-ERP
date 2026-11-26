"""Application use-cases: orchestrate domain rules, storage and adapters.

UI talks to these use-cases; use-cases never call the network or model directly
except through injected adapter ports. A missing adapter returns an explicit
not_configured/unavailable result instead of a Mock success.
"""
from __future__ import annotations

import json
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..adapters import exporter_internal as exporter
from ..adapters.storage_relational import RelationalStore
from ..application import fillplan
from ..domain import evidence, models, pricing
from ..domain import profit_model
from ..domain.ports import AdapterResult, CollectRequest, ExtractRequest


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _money(money: dict[str, Any]) -> pricing.MoneyInput:
    return pricing.MoneyInput(
        amount=money.get("amount"),
        currency=money.get("currency", "CNY"),
        sales_unit=money.get("sales_unit", "set"),
        confirmed=bool(money.get("confirmed")),
        source_ref=money.get("source_ref"),
    )


def _policy(policy: dict[str, Any] | None) -> pricing.BusinessPolicy | None:
    if not policy:
        return None
    return pricing.BusinessPolicy(
        metric=policy.get("metric"),
        threshold_percent=policy.get("threshold_percent"),
        confirmed=bool(policy.get("confirmed")),
        confirmed_by=policy.get("confirmed_by"),
        confirmed_at=policy.get("confirmed_at"),
        source_ref=policy.get("source_ref"),
        version=policy.get("version") or "draft",
    )


def _eval_to_dict(result: pricing.Evaluation) -> dict[str, Any]:
    return {"status": result.status, "reasons": list(result.reasons), "values": result.values}


class WorkbenchService:
    def __init__(self, store: RelationalStore, collector=None, rule_extractor=None,
                 dsh=None, deepseek=None, registry_sources: list[dict[str, Any]] | None = None,
                 field_map: dict[str, Any] | None = None):
        self.store = store
        self.collector = collector
        self.rule_extractor = rule_extractor
        self.dsh = dsh
        self.deepseek = deepseek
        if hasattr(store,'ensure_reference_sources'):
            store.ensure_reference_sources(registry_sources or [])
            self.registry_sources = store.reference_sources()
        else:
            self.registry_sources = registry_sources or []
        self.field_map = field_map or {}
        self._llm_calls = 0

    # ---------- bootstrap / registry ----------
    def seed_if_empty(self, fixtures: dict[str, Any]) -> list[str]:
        if self.store.list_records("candidate"):
            return []
        created: list[str] = []
        for key in ("source", "candidate", "policy", "feedback"):
            record = fixtures.get(key)
            if record:
                errors = self.store.upsert_record(record)
                if not errors:
                    created.append(record["id"])
        return created

    def registry(self) -> dict[str, Any]:
        db_sources = self.store.list_records("source")
        merged = list(self.registry_sources)
        existing = by_id_registry(self.registry_sources)
        for src in db_sources:
            if src["id"] not in existing:
                merged.append(src)
        return {
            "sources": merged,
            "field_map": self.field_map,
            "adapter_statuses": self.store.adapter_statuses(),
            "dto_version": models.DTO_VERSION,
            'profit_schema':profit_model.SCHEMA,
            'database':{'engine':self.store.engine,'location':self.store.location,'schema_version':getattr(self.store,'schema_version','sqlite-v1')},
        }

    # ---------- policy ----------
    def get_policy(self) -> dict[str, Any] | None:
        rows = self.store.list_records("policy")
        return rows[0] if rows else None

    def save_policy(self, payload: dict[str, Any]) -> list[str]:
        payload.setdefault("record_type", "policy")
        payload.setdefault("id", "POLICY-CURRENT")
        payload.setdefault("version", "unconfirmed-v1")
        errors = models.validate_policy(payload)
        if errors:
            return errors
        current = self.get_policy()
        history = (current or {}).get("history") or []
        if current:
            history.append({"saved_at": _now(), "metric": current.get("metric"),
                             "threshold_percent": current.get("threshold_percent"),
                             "confirmed": current.get("confirmed")})
        payload["history"] = history[-20:]
        return self.store.upsert_record(payload)

    # ---------- sources ----------
    def list_sources(self) -> list[dict[str, Any]]:
        return self.store.list_records("source")

    def get_source(self, source_id: str) -> dict[str, Any] | None:
        return self.store.get_record("source", source_id)

    def save_source(self, payload: dict[str, Any]) -> list[str]:
        payload.setdefault("record_type", "source")
        payload.setdefault("id", models.new_id("SRC"))
        payload.setdefault("verification", "manual_entry_pending_review")
        return self.store.upsert_record(payload)

    # ---------- candidates ----------
    def list_candidates(self) -> list[dict[str, Any]]:
        candidates = self.store.list_records("candidate")
        policy = self.get_policy()
        return [self.candidate_summary(c, policy) for c in candidates]

    def candidate_summary(self, cand: dict[str, Any], policy: dict[str, Any] | None = None) -> dict[str, Any]:
        policy = policy or self.get_policy()
        sku_views = [self.sku_view(cand, sku, policy) for sku in cand.get("skus") or []]
        evidence_views = []
        for ref in cand.get("evidence_refs") or []:
            src = self.get_source(ref)
            if src:
                comp = evidence.assess_comparability(cand, src)
                caliber = evidence.sales_caliber(src)
                evidence_views.append({"source": src, "comparability": comp, "sales": caliber})
        return {
            "id": cand["id"],
            "title": cand.get("title") or cand["id"],
            "research_market": cand.get("research_market"),
            "internal_decision": cand.get("internal_decision"),
            "decision_label": models.DECISION_LABELS.get(cand.get("internal_decision")),
            "synthetic": bool(cand.get("synthetic")),
            "updated_at": self._record_updated(cand["id"]),
            "evidence_count": len(evidence_views),
            "next_action": self.next_action(cand, sku_views),
            "readiness": self.readiness(cand, sku_views, evidence_views),
            "sku_count": len(sku_views),
            "finance_statuses": [s['active_evaluation']['status'] for s in sku_views],
            'profit_summaries': [dict(sku=v['sku']['merchant_sku'],
                baseline=v['full_profit']['scenarios']['baseline'],conservative=v['full_profit']['scenarios']['conservative'])
                for v in sku_views if (v.get('full_profit') or {}).get('scenarios')],
        }

    def _record_updated(self, rid: str) -> str | None:
        return self.store.record_metadata('candidate', rid).get('updated_at')

    def get_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        cand = self.store.get_record("candidate", candidate_id)
        if not cand:
            return None
        policy = self.get_policy()
        sku_views = [self.sku_view(cand, sku, policy) for sku in cand.get("skus") or []]
        evidence_views = []
        for ref in cand.get("evidence_refs") or []:
            src = self.get_source(ref)
            if src:
                evidence_views.append({
                    "source": src,
                    "comparability": evidence.assess_comparability(cand, src),
                    "sku_comparisons": [evidence.assess_comparability(cand, src, s) for s in cand.get('skus') or []],
                    "sales": evidence.sales_caliber(src),
                })
        feedbacks = self.store.list_records("feedback", candidate_id)
        submissions = self.store.list_submissions(candidate_id)
        return {
            "candidate": cand,
            "skus": sku_views,
            "evidence": evidence_views,
            "feedbacks": feedbacks,
            "submissions": submissions,
            "revisions": self.store.revision_history(candidate_id),
            "policy": policy,
            "readiness": self.readiness(cand, sku_views, evidence_views),
        }

    def sku_view(self, cand: dict[str, Any], sku: dict[str, Any],
                 policy: dict[str, Any] | None) -> dict[str, Any]:
        price = _money(sku.get("supply_income") or {})
        costs = [pricing.CostItem(key=c["key"], money=_money(c["money"])) for c in sku.get("costs") or []]
        evaluation = pricing.evaluate_offer(price, costs, _policy(policy))
        view: dict[str, Any] = {"sku": sku, "evaluation": _eval_to_dict(evaluation)}

        # Buyer suggested price applies to this SKU only; costs are never adjusted to fit.
        buyer_money = self._latest_buyer_income(cand["id"], sku.get("merchant_sku"))
        if buyer_money:
            buyer_eval = pricing.evaluate_offer(_money(buyer_money), costs, _policy(policy))
            view["buyer_evaluation"] = _eval_to_dict(buyer_eval)
            view["buyer_supply_income"] = buyer_money
        view['active_evaluation'] = view.get('buyer_evaluation', view['evaluation'])
        view['active_price_kind'] = 'buyer' if buyer_money else 'offer'
        view['full_profit']=profit_model.evaluate_full(buyer_money or sku.get('supply_income') or {},sku)
        if (view['full_profit'] or {}).get('scenarios'):
            legacy_floor=view['active_evaluation'].get('values',{}).get('minimum_supply_income') if (policy or {}).get('confirmed') else None
            for scenario in view['full_profit']['scenarios'].values():
                target=scenario.get('target_price')
                scenario['combined_target_price']=str(max(Decimal(target),Decimal(legacy_floor))) if target and legacy_floor else target
                scenario['legacy_target_price']=legacy_floor
        return view

    def _latest_buyer_income(self, candidate_id: str, merchant_sku: str) -> dict[str, Any] | None:
        feedbacks = self.store.list_records("feedback", candidate_id)
        feedbacks.sort(key=lambda f: (f.get('feedback_date') or '', f.get('created_at') or '', f.get('id') or ''), reverse=True)
        for fb in feedbacks:
            income = fb.get("buyer_supply_income")
            if income and fb.get("sku_ref") == merchant_sku:
                return income
            # Legacy whole-candidate feedback is only unambiguous for a single SKU.
            candidate = self.store.get_record('candidate', candidate_id) or {}
            if income and not fb.get('sku_ref') and len(candidate.get('skus') or []) == 1:
                return income
        return None

    def save_candidate(self, record: dict[str, Any], reviewer: str | None = None) -> list[str]:
        record.setdefault("record_type", "candidate")
        if record['record_type'] != 'candidate':
            return ['record_type must be candidate']
        record.setdefault("mode_assumption", "fully_managed")
        record.setdefault("internal_decision", "research")
        errors = models.validate_candidate(record)
        if errors:
            return errors
        # A failed record write must not leave a history claiming it succeeded.
        with self.store.transaction():
            existing = self.store.get_record("candidate", record["id"])
            if existing:
                self._record_field_revisions(existing, record, reviewer)
            return self.store.upsert_record(record)

    def _record_field_revisions(self, before: dict[str, Any], after: dict[str, Any],
                                reviewer: str | None) -> None:
        for key in set(before) | set(after):
            if key != 'skus' and before.get(key) != after.get(key):
                self.store.add_revision(after['id'], None, key, before.get(key), after.get(key), reviewer, 'manual')
        before_skus = {s.get("merchant_sku"): s for s in before.get("skus") or []}
        after_skus = {s.get('merchant_sku'):s for s in after.get('skus') or []}
        for key in before_skus.keys() - after_skus.keys():
            self.store.add_revision(after['id'], key, 'sku_removed', before_skus[key], None, reviewer, 'manual')
        for sku in after.get("skus") or []:
            old = before_skus.get(sku.get("merchant_sku"))
            if not old:
                self.store.add_revision(after['id'], sku.get('merchant_sku'), 'sku_added', None, sku, reviewer, 'manual')
                continue
            for field_key in ("supply_income", "costs", "pieces", "sales_unit",
                              "specs", "pack_composition", "sale_spec_bindings",'profit_plan'):
                if json.dumps(old.get(field_key), ensure_ascii=False, sort_keys=True) != \
                        json.dumps(sku.get(field_key), ensure_ascii=False, sort_keys=True):
                    self.store.add_revision(
                        after["id"], sku.get("merchant_sku"), field_key,
                        old.get(field_key), sku.get(field_key), reviewer, "manual")

    def set_decision(self, candidate_id: str, decision: str, reason: str,
                      reviewer: str | None) -> list[str]:
        cand = self.store.get_record("candidate", candidate_id)
        if not cand:
            return ["candidate not found"]
        if decision not in models.DECISIONS:
            return [f"decision must be one of {models.DECISIONS}"]
        policy = self.get_policy()
        history = cand.get("decision_history") or []
        history.append({
            "decision": decision,
            "reason": reason,
            "reviewer": reviewer,
            "at": _now(),
            "policy_version": (policy or {}).get("version"),
        })
        cand["internal_decision"] = decision
        cand["decision_history"] = history[-30:]
        return self.store.upsert_record(cand)

    def restore_decision(self, candidate_id: str, reviewer: str | None) -> list[str]:
        """Reversible: bring a paused/excluded candidate back to research without deleting it."""
        return self.set_decision(candidate_id, "research", "撤销暂缓/排除，恢复继续评估", reviewer)

    # ---------- feedback ----------
    def add_feedback(self, payload: dict[str, Any]) -> dict[str, Any]:
        payload.setdefault("record_type", "feedback")
        payload.setdefault("id", models.new_id("FB"))
        payload.setdefault("verification", "draft")
        payload.setdefault('created_at', _now())
        candidate = self.store.get_record('candidate', payload.get('candidate_id'))
        if not candidate:
            return {'status': 'failed', 'errors': ['candidate_id: 商品不存在']}
        skus = candidate.get('skus') or []
        if payload.get('buyer_supply_income'):
            if not payload.get('sku_ref') and len(skus) == 1:
                payload['sku_ref'] = skus[0]['merchant_sku']
            sku = next((s for s in skus if s['merchant_sku'] == payload.get('sku_ref')), None)
            if not sku:
                return {'status': 'failed', 'errors': ['sku_ref: 核价必须关联具体 SKU']}
            money = payload['buyer_supply_income']
            if money.get('confirmed') and payload.get('verification') != 'human_confirmed':
                money['confirmed'] = False
        errors = models.validate_feedback(payload)
        confirmed_blockers = [e for e in errors if e in (
            "feedback_date: required for confirmed feedback",
            "evidence_ref: required for confirmed feedback",
        )]
        if payload.get("verification") == "human_confirmed" and confirmed_blockers:
            payload["verification"] = "draft"
            payload["note"] = "缺少日期/原话/证据索引，未能登记为已证实，已存为草稿。"
            if payload.get('buyer_supply_income'):
                payload['buyer_supply_income']['confirmed'] = False
            errors = models.validate_feedback(payload)
        if errors:
            return {"status": "failed", "errors": errors}
        self.store.upsert_record(payload)
        return {"status": "succeeded", "id": payload["id"]}

    # ---------- readiness / next action ----------
    def readiness(self, cand: dict[str, Any], sku_views: list[dict[str, Any]],
                  evidence_views: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        has_evidence = bool(cand.get('skus')) and all(
            any(evidence.assess_comparability(cand, e['source'], s)['comparable'] for e in evidence_views)
            for s in cand.get('skus') or [])
        items.append({"key": "market_evidence", "label": "同规格市场证据",
                      "status": "规格已对账" if has_evidence else ("资料不足或规格不同" if evidence_views else "待补"), "ok": has_evidence})
        supplier = cand.get("supplier") or {}
        supplier_ok = bool(supplier.get('url') and supplier.get('moq') and supplier.get('lead_days') not in (None,'') and supplier.get('confirmed') and supplier.get('source_ref'))
        items.append({"key": "supplier", "label": "供应商与供货能力",
                      "status": "供货条件已核对" if supplier_ok else "待补资料或核验", "ok": supplier_ok})
        binding = cand.get("template_binding") or {}
        template_ok = bool(binding.get('category_id') and binding.get('source_ref') and binding.get('status') == 'verified')
        items.append({"key": "template", "label": "类目与销售属性",
                      "status": "模板已核对" if template_ok else "待后台核对", "ok": template_ok})
        items.append({"key": "sku", "label": "商家 SKU 结构",
                      "status": f"{len(sku_views)} 个草稿", "ok": len(sku_views) > 0})
        quote_statuses = {v.get('active_evaluation', v['evaluation'])['status'] for v in sku_views}
        scenario_ready = bool(sku_views) and quote_statuses == {'MEETS_THRESHOLD'}
        full_below=any((v.get('full_profit') or {}).get('scenarios',{}).get('baseline',{}).get('status') in ('LOSS','BELOW_TARGET') for v in sku_views)
        if full_below:
            scenario_ready=False
        items.append({"key": "quote", "label": "报价情景",
                      "status": "达到经营门槛" if scenario_ready else ('低于净收益目标' if full_below else '低于门槛' if 'BELOW_THRESHOLD' in quote_statuses else '待补金额或核验'),
                      "ok": scenario_ready})
        materials = cand.get("materials") or {}
        material_count = sum(1 for v in materials.values() if v)
        requirements=cand.get('material_requirements') or {}
        required=requirements.get('required') or []
        requirements_known=bool(requirements.get('confirmed') and requirements.get('source_ref') and isinstance(requirements.get('required'),list))
        materials_ok=requirements_known and all(materials.get(k) for k in required)
        items.append({"key": "materials", "label": "样品与素材",
                      "status": (f'本次 {len(required)} 项要求已齐' if materials_ok else f'{material_count} 项已登记，按任务核对'), "ok": materials_ok})
        return items

    def next_action(self, cand: dict[str, Any], sku_views: list[dict[str, Any]]) -> str:
        decision = cand.get("internal_decision")
        if decision == "paused":
            return "已暂缓：保留原因与政策版本，可随时撤销恢复。"
        if decision == "excluded":
            return "已排除：本地记录保留，未删除来源或真实平台商品；可撤销。"
        full=[v['full_profit']['scenarios'] for v in sku_views if (v.get('full_profit') or {}).get('scenarios')]
        if any(x['baseline']['status']=='LOSS' for x in full):
            return '完整成本测算为亏损：按保本价重新核价，或核实成本/销量分摊后暂缓。'
        if any(x['baseline']['status']=='BELOW_TARGET' for x in full):
            return '完整成本后低于净收益目标：核对估值和分摊数量，按目标底价议价。'
        if any(x['conservative']['status']=='LOSS' for x in full):
            return '基准情景有收益，保守情景亏损：优先核实退回、损耗、扣款和周转成本。'
        if any(x['conservative']['status']=='BELOW_TARGET' for x in full):
            return '基准净收益达到预算目标，保守情景低于目标：优先核对采购、退回损耗、扣款和分摊数量。'
        active = [v.get('active_evaluation', v['evaluation']) for v in sku_views]
        if any(v.get('values', {}).get('contribution') is not None and
               Decimal(v['values']['contribution']) < 0 for v in active):
            return '当前核价亏损：建议暂缓，先与买手重新议价或核对成本；不覆盖原报价。'
        statuses = [v['status'] for v in active]
        if any(v.get('values',{}).get('financial_threshold_passed') == 'false' for v in active):
            return '当前核价低于经营门槛：按门槛供货价重新议价，或核实可降低的成本；未核验输入仅作测算。'
        if any(s == "BELOW_THRESHOLD" for s in statuses):
            return "报价低于已确认门槛：核对成本与供货价，由负责人决定重新报价或暂缓。"
        if statuses and all(s == "MEETS_THRESHOLD" for s in statuses):
            return "收益条件仅满足其一；仍需核对市场证据、供货能力与类目资料后再评审。"
        return "先补齐市场证据、供货能力与类目字段，再整理内部提报资料。"

    # ---------- internal submission package ----------
    def build_submission(self, candidate_id: str) -> dict[str, Any]:
        detail = self.get_candidate(candidate_id)
        if not detail:
            return {"status": "failed", "errors": ["candidate not found"]}
        cand = detail["candidate"]
        unverified = [r['label'] + '：' + r['status'] for r in detail['readiness'] if not r['ok']]
        if not cand.get('mode_confirmed'):
            unverified.append('店铺经营模式待核对')
        sku_lines = []
        for view in detail["skus"]:
            sku = view["sku"]
            ev = view["evaluation"]
            sku_lines.append({
                **sku,
                "merchant_sku": sku.get("merchant_sku"),
                "pieces": sku.get("pieces"),
                "sales_unit": sku.get("sales_unit"),
                "supply_income": sku.get("supply_income"),
                "evaluation": ev,
                'buyer_evaluation': view.get('buyer_evaluation'),
                'buyer_supply_income': view.get('buyer_supply_income'),
                'active_evaluation': view.get('active_evaluation'),
                'full_profit':view.get('full_profit'),
                "platform_sku_id": sku.get("platform_sku_id"),
                "platform_skc_id": sku.get("platform_skc_id"),
                "sale_spec_bindings": sku.get("sale_spec_bindings") or [],
            })
        evidence_links = [
            {"id": e["source"]["id"], "url": e["source"].get("url"),
             "locator": e["source"].get("locator"), "comparable": e["comparability"]["comparable"]}
            for e in detail["evidence"]
        ]
        package = {
            "id": models.new_id("SUB"),
            "record_type": "submission",
            "candidate_id": candidate_id,
            "created_at": _now(),
            "banner": "内部记录，非 Temu 导入模板；未经真实类目模板核对，不得直接上传平台。",
            "mode_assumption": "fully_managed",
            "mode_confirmed": bool(cand.get("mode_confirmed")),
            "title": cand.get('listing_title') or cand.get("title"),
            'market_title': cand.get('market_title'),
            "research_market": cand.get("research_market"),
            "rationale": cand.get("rationale"),
            "advantage": cand.get("advantage"),
            "supplier": cand.get("supplier"),
            "evidence_links": evidence_links,
            "skus": sku_lines,
            "materials": cand.get("materials") or {},
            "unverified_items": unverified,
            'policy': detail['policy'],
            'next_action': self.next_action(cand, detail['skus']),
            'product_record': cand,
            'source_registry':self.registry_sources,
            "field_mapping_version": self.field_map.get("schema_version"),
            "rpa_dry_run_plan": fillplan.build_fill_plan(cand, self.field_map.get("schema_version")),
            "feedback": detail["feedbacks"],
        }
        self.store.save_submission(package)
        return {"status": "succeeded", "package": package}

    def build_fill_plan(self, candidate_id: str) -> dict[str, Any]:
        cand = self.store.get_record("candidate", candidate_id)
        if not cand:
            return {"status": "failed", "errors": ["candidate not found"]}
        plan = fillplan.build_fill_plan(cand, self.field_map.get("schema_version"))
        return {"status": "succeeded", "plan": plan}

    # ---------- collection (P1) ----------
    def collect_page(self, task_id: str, url: str, allowed_hosts: tuple[str, ...], candidate_id: str | None=None) -> AdapterResult:
        candidate=self.store.get_record('candidate',candidate_id) if candidate_id else None
        if candidate_id and not candidate:
            return AdapterResult('failed',error_code='CANDIDATE_NOT_FOUND')
        if self.collector is None:
            self.store.set_adapter_status("collector_http", "not_configured",
                                          {"detail": "HTTP 采集适配器未配置。"})
            return AdapterResult("not_configured", error_code="COLLECTOR_NOT_CONFIGURED")
        request = CollectRequest(task_id=task_id, url=url, allowed_hosts=allowed_hosts)
        result = self.collector.collect(request)
        if result.status == "succeeded":
            payload = result.payload
            payload["captured_at"] = _now()
            source = {
                "record_type": "source",
                "id": f"WEB-{task_id}",
                "level": "market_observation",
                "url": url,
                "locator": payload.get("title") or "HTTP 采集页面标题待人工核对",
                "scope": {"country": None},
                "observed_at": datetime.now().date().isoformat(),
                "retrieved_at": payload["captured_at"],
                "effective_from": None,
                "version": None,
                "verification": "public_body_read_pending_review",
                "snapshot_ref": payload.get('file_path') or payload.get("snapshot_ref"),
                "sha256": payload.get("sha256"),
                "facts": {"title": payload.get("title")},
                "note": "自动采集快照，字段未经人工核对；评价/销量口径需逐条确认。",
            }
            self.store.upsert_record(source)
            self.store.save_snapshot(source["id"], payload.get("snapshot_ref"),
                                     payload.get("sha256"), payload.get("file_path"),
                                     "succeeded", payload)
            self.store.set_adapter_status("collector_http", "succeeded",
                                          {"last_url": url, "captured_at": payload["captured_at"]})
            if self.rule_extractor and payload.get("file_path"):
                extract = self.rule_extractor.extract(ExtractRequest(
                    task_id=task_id, snapshot_ref=payload["file_path"],
                    field_keys=("title", "display_price")))
                if extract.status == "succeeded":
                    source["facts"]["extracted_candidates"] = extract.payload.get("fields")
                    self.store.upsert_record(source)
            payload['source_id']=source['id']
            if candidate:
                refs=candidate.setdefault('evidence_refs',[])
                if source['id'] not in refs:
                    refs.append(source['id'])
                    self.save_candidate(candidate,reviewer='public-page-collector')
        else:
            self.store.set_adapter_status("collector_http", result.status,
                                          {"error_code": result.error_code,
                                           "detail": result.payload.get("error")})
            self.store.save_snapshot(f"WEB-{task_id}", None, None, None, result.status,
                                     {"url": url, "error": result.payload})
        return result

    # ---------- import / export ----------
    def export_bundle(self, fmt: str) -> dict[str, Any]:
        candidates = self.store.list_records("candidate")
        sources = self.store.list_records("source")
        policies = self.store.list_records("policy")
        feedbacks = self.store.list_records("feedback")
        if fmt == "json":
            bundle = exporter.build_json_bundle(candidates, sources, policies, feedbacks)
            bundle["exported_at"] = _now()
            return {"format": "json", "content": bundle,
                    "warning": exporter.INTERNAL_JSON_MARKER}
        rows = exporter.candidates_to_csv_rows(candidates)
        return {"format": "csv", "content": exporter.write_csv(rows),
                "columns": exporter.CANDIDATE_CSV_COLUMNS,
                "warning": exporter.INTERNAL_CSV_MARKER}

    def import_bundle(self, fmt: str, text: str) -> dict[str, Any]:
        report: dict[str, Any] = {"imported": [], "duplicates": [], "errors": []}
        if fmt == "json":
            bundle, errors = exporter.parse_json_bundle(text)
            report["errors"].extend(errors)
            if errors:
                return report
            records = bundle.get("records") or {}
            for rtype, key in (("source", "sources"), ("candidate", "candidates"),
                               ("policy", "policies"), ("feedback", "feedbacks")):
                for record in records.get(key) or []:
                    self._import_record(record, rtype, report)
        else:
            rows, errors = exporter.parse_csv(text)
            report["errors"].extend(errors)
            self._import_csv_rows(rows, report)
        return report

    def _import_record(self, record: dict[str, Any], rtype: str, report: dict[str, Any]) -> None:
        if not isinstance(record, dict):
            report["errors"].append({"record_type": rtype, "error": "record is not an object"})
            return
        rid = record.get("id")
        existing = self.store.get_record(rtype, rid) if rid else None
        if existing:
            report["duplicates"].append({"record_type": rtype, "id": rid})
            return
        errors = self.store.upsert_record(record)
        if errors:
            report["errors"].append({"record_type": rtype, "id": rid, "errors": errors})
        else:
            report["imported"].append({"record_type": rtype, "id": rid})

    def _import_csv_rows(self, rows: list[dict[str, Any]], report: dict[str, Any]) -> None:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(row.get("candidate_id") or row["merchant_sku"], []).append(row)
        for cand_id, group in grouped.items():
            first = group[0]
            existing = self.store.get_record("candidate", cand_id)
            if existing:
                report["duplicates"].append({"record_type": "candidate", "id": cand_id})
                continue
            skus = [self._csv_row_to_sku(row, report) for row in group]
            if any(s is None for s in skus):
                continue
            record = {
                "record_type": "candidate",
                "id": cand_id,
                "mode_assumption": "fully_managed",
                "mode_confirmed": False,
                "research_market": first.get("research_market") or "DE",
                "platform_product_id": first.get("platform_product_id") or None,
                "category_path_ids": [],
                "template_binding": {"status": "unverified", "category_id": None, "source_ref": None},
                "evidence_refs": [x for x in (first.get("evidence_refs") or "").split(";") if x],
                "internal_decision": first.get("internal_decision") or "research",
                "decision_history": [],
                "synthetic": first.get("synthetic") == "true",
                "skus": skus,
            }
            if first.get('candidate_json'):
                try:
                    metadata = json.loads(first['candidate_json'])
                    if not isinstance(metadata, dict) or metadata.get('id') != cand_id:
                        raise ValueError('candidate_json 与 candidate_id 不一致')
                    record = {**metadata, **{k:record[k] for k in ('research_market','internal_decision','platform_product_id','evidence_refs','synthetic')}, 'skus': skus}
                except (ValueError, TypeError) as exc:
                    report['errors'].append({'id':cand_id,'error':str(exc)})
                    continue
            errors = self.store.upsert_record(record)
            if errors:
                report["errors"].append({"record_type": "candidate", "id": cand_id, "errors": errors})
            else:
                report["imported"].append({"record_type": "candidate", "id": cand_id})

    def _csv_row_to_sku(self, row: dict[str, Any], report: dict[str, Any]) -> dict[str, Any] | None:
        income = {
            "amount": row.get("supply_income_amount") or None,
            "currency": row.get("supply_income_currency") or "CNY",
            "sales_unit": row.get("sales_unit") or "set",
            "confirmed": row.get("supply_income_confirmed") == "true",
            "source_ref": "csv:import",
        }
        cost_keys = {"cost_purchase": "purchase", "cost_packaging": "packaging",
                     "cost_logistics": "logistics", "cost_expected_after_sales": "expected_after_sales",
                     "cost_other_variable": "other_variable"}
        costs = []
        for col, key in cost_keys.items():
            costs.append({"key": key, "money": {
                "amount": row.get(col) or None, "currency": income["currency"],
                "sales_unit": income["sales_unit"], "confirmed": False, "source_ref": "csv:import"}})
        try:
            pieces = int(row.get("pieces") or 1)
        except ValueError:
            report["errors"].append({"row": row.get("merchant_sku"), "error": "pieces not an integer"})
            return None
        base = {}
        if row.get('sku_json'):
            try:
                base = json.loads(row['sku_json'])
                if not isinstance(base, dict):
                    raise ValueError('sku_json must be an object')
            except (ValueError, TypeError) as exc:
                report['errors'].append({'row':row.get('merchant_sku'),'error':str(exc)})
                return None
        if base:
            original_income = base.get('supply_income') or {}
            changed = any(original_income.get(k) != income.get(k) for k in ('amount','currency','sales_unit'))
            income = {**original_income, **{k:income[k] for k in ('amount','currency','sales_unit')},
                      'confirmed':bool(original_income.get('confirmed') and income.get('confirmed'))}
            if changed:
                income.update(confirmed=False, source_ref='csv:edited')
            original_costs = {c['key']:c for c in base.get('costs') or []}
            for cost in costs:
                old = original_costs.get(cost['key'])
                if old and old['money'].get('amount') == cost['money']['amount']:
                    cost['money'] = old['money']
        return {
            **base,
            "merchant_sku": row.get("merchant_sku"),
            "merchant_group_code": row.get("merchant_group_code"),
            "platform_sku_id": row.get("platform_sku_id") or None,
            "platform_skc_id": row.get("platform_skc_id") or None,
            "sales_unit": income["sales_unit"],
            "pieces": pieces,
            "sale_spec_bindings": base.get('sale_spec_bindings') or [],
            "pack_composition": base.get('pack_composition') or [],
            "supply_income": income,
            "costs": costs,
        }

    # ---------- backup / restore ----------
    def backup(self, target_path: str) -> Path:
        return self.store.backup(target_path)

    def restore(self, source_path: str) -> list[str]:
        errors=self.store.restore(source_path)
        if not errors and hasattr(self.store,'ensure_reference_sources'):
            self.store.ensure_reference_sources(self.registry_sources)
        return errors


def by_id_registry(sources: list[dict[str, Any]]) -> set[str]:
    return {s["id"] for s in sources}
