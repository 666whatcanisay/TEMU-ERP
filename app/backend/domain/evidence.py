"""Evidence is comparable, incomparable, or insufficient; absence is not a match."""
from __future__ import annotations
from decimal import Decimal, InvalidOperation
from typing import Any


def _dimensions(value: dict[str, Any]) -> tuple[Decimal, ...]:
    dims = value.get('product_dimensions_cm') or value.get('dimensions_cm') or []
    try:
        return tuple(Decimal(str(d)) for d in dims) if len(dims) == 3 and all(d is not None for d in dims) else ()
    except (InvalidOperation, TypeError):
        return ()


def assess_comparability(candidate: dict[str, Any], source: dict[str, Any], sku: dict | None = None) -> dict:
    scope, facts = source.get('scope') or {}, source.get('facts') or {}
    sku = sku or next(iter(candidate.get('skus') or []), {})
    reasons, missing = [], []
    components = sku.get('pack_composition') or []
    source_components = scope.get('pack_composition') or []
    if source_components:
        def composition(items):
            return sorted((int(x.get('count') or 0), _dimensions(x)) for x in items)
        if not components or any(not _dimensions(x) for x in components + source_components):
            missing.append('组成尺寸未齐')
        elif composition(components) != composition(source_components):
            reasons.append('组成数量或单件尺寸不同')
    else:
        candidate_dims = _dimensions(components[0]) if len(components) == 1 else ()
        source_dims = _dimensions(scope)
        if not candidate_dims or not source_dims:
            missing.append('缺少双方完整单件尺寸/组成')
        elif candidate_dims != source_dims:
            reasons.append('尺寸规格不同')
    source_pieces = scope.get('pieces')
    if source_pieces is None and 'single' in str(scope.get('display_unit', '')):
        source_pieces = 1
    if not source_pieces or not sku.get('pieces'):
        missing.append('缺少每销售单位件数')
    elif source_pieces != sku['pieces']:
        reasons.append('单件/套装件数不同')
    if not scope.get('country') or not candidate.get('research_market'):
        missing.append('缺少市场/国家')
    elif scope['country'] != candidate['research_market']:
        reasons.append('目标市场不同')
    if not source.get('observed_at'):
        missing.append('缺少观察日期')
    if 'pending' in str(source.get('verification','')) or source.get('verification') in ('draft','extracted_candidate'):
        missing.append('来源原文尚待核对')
    if not facts.get('currency') or facts.get('display_price') is None:
        missing.append('缺少价格或币种')
    market_currency = candidate.get('market_currency') or ('EUR' if candidate.get('research_market') == 'DE' else None)
    if market_currency and facts.get('currency') and facts['currency'] != market_currency:
        fx = source.get('exchange_rate') or {}
        if not all(fx.get(k) for k in ('rate', 'source_id', 'observed_at')):
            missing.append('跨零售币种缺少带日期和来源的汇率')
    if not (scope.get('material') and (sku.get('material') or candidate.get('material'))):
        missing.append('材质未对账')
    else:
        normalize = lambda s: str(s).strip().lower().replace('kunststoff', 'plastic').replace('塑料', 'plastic')
        if normalize(scope['material']) != normalize(sku.get('material') or candidate['material']):
            reasons.append('材质标注不同')
    status = 'incomparable' if reasons else ('insufficient' if missing else 'comparable')
    return {'status': status, 'comparable': status == 'comparable', 'reasons': reasons + missing,
            'source_id': source.get('id'), 'sku_ref': sku.get('merchant_sku'),
            'scope': '规格与展示价格可比性；不等于同厂同款、销量或需求已证实'}


def sales_caliber(source: dict[str, Any]) -> dict[str, Any]:
    facts = source.get('facts') or {}
    sales, warnings = facts.get('sales'), []
    if sales is not None and not facts.get('sales_window'):
        warnings.append('未标注统计窗口的销量不能当作月销量；已按待核处理')
        sales = None
    if facts.get('display_review_count') is not None:
        warnings.append('评价数不是销量；可能跨规格汇总')
    if facts.get('trend_index') is not None:
        warnings.append('搜索趋势相对指数不是绝对需求量或销量')
    return {'sales': sales, 'warnings': warnings}
