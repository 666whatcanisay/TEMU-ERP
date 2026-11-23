/* Read-only workflow presentation. All money decisions come from the backend. */
window.WorkbenchUI = (() => {
  const esc = x => String(x ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const amount = x => x == null ? '—' : esc(x);
  const percent = x => x == null ? '—' : `${(Number(x)*100).toFixed(2)}%`;
  function finance(detail) {
    if (!detail?.skus?.length) return '';
    return `<section class="panel finance-panel" data-testid="financial-summary"><div class="panel-title"><h3>核价与经营判断</h3><span class="hint">按每个销售单位计算</span></div>${detail.skus.map(v=>{
      if(v.full_profit?.scenarios?.baseline) return ProfitUI.card(v,detail);
      if(v.full_profit) return `<div class="callout bad">完整利润暂不能计算：${(v.full_profit.errors||[]).map(esc).join('；')}</div>`;
      const ev=v.active_evaluation || v.buyer_evaluation || v.evaluation;
      const x=ev.values||{}, original=v.evaluation.values||{};
      const loss=x.contribution!=null&&Number(x.contribution)<0;
      const bad=loss||ev.status==='BELOW_THRESHOLD'||x.financial_threshold_passed==='false';
      const verified=ev.status==='MEETS_THRESHOLD'||ev.status==='BELOW_THRESHOLD';
      const title=loss?'当前价格亏损':bad?'当前价格低于门槛':ev.status==='MEETS_THRESHOLD'?'达到经营门槛':'待核验金额与政策';
      return `<div class="quote-summary ${bad?'negative':''}" data-testid="quote-summary" data-sku="${esc(v.sku.merchant_sku)}">
        <div class="panel-title"><strong>${esc(v.sku.merchant_sku)}</strong><span class="tag ${bad?'bad':verified?'good':'warn'}">${title}</span></div>
        <div class="quote-metrics">
          <div><small>${v.buyer_evaluation?'买手核价':'拟报供货价'} · ${esc(x.currency||v.sku.supply_income.currency)}</small><strong data-testid="active-price">${amount(x.supply_income)}</strong>${v.buyer_evaluation?`<small>原报价 ${amount(original.supply_income)}</small>`:''}</div>
          <div><small>可变成本</small><strong>${amount(x.variable_cost)}</strong><small>不含未录入的固定开支与税</small></div>
          <div><small>每套/件贡献</small><strong data-testid="contribution">${amount(x.contribution)}</strong><small>收入贡献率 ${percent(x.contribution_margin)}</small></div>
          <div><small>门槛供货价</small><strong data-testid="minimum-price">${amount(x.minimum_supply_income)}</strong><small>${esc(detail.policy?.threshold_percent||'未设置')}% · ${detail.policy?.metric==='cost_markup'?'成本加价率':'收入贡献率'}</small></div>
        </div>
        ${bad?`<p class="callout bad">${loss?'收入不足以覆盖已录成本。':'未达到当前经营门槛。'}${x.price_gap&&x.price_gap!=='0.00'?`按现有成本至少需提高供货价 ${amount(x.price_gap)} ${esc(x.currency)}。`:''}建议重新议价或暂缓。${!verified?' 金额或政策尚待核验。':''}</p>`:''}
        ${v.buyer_evaluation?`<details class="accordion"><summary>原报价对照与核价依据</summary><p class="meta">原报价 ${amount(original.supply_income)}，贡献 ${amount(original.contribution)}；买手价来源：${esc(v.buyer_supply_income.source_ref||'待补')} · ${v.buyer_supply_income.confirmed?'已核验':'待核验'}</p></details>`:''}
      </div>`;
    }).join('')}<div class="workflow-actions">${['paused','excluded'].includes(detail.candidate.internal_decision)?'<span class="tag warn">当前已暂缓/排除</span><button class="btn" data-restore-candidate>恢复评估</button>':`<button class="btn" data-quick-decision="paused">暂缓此商品</button><button class="btn" data-quick-decision="internal_review" ${detail.skus.every(v=>(v.active_evaluation||v.evaluation).status==='MEETS_THRESHOLD'&&(!v.full_profit||v.full_profit.scenarios?.baseline?.meets_target))?'':'disabled title="先核验金额与政策，并满足成本后的收益目标"'}>继续内部评审</button>`}</div></section>`;
  }
  function reviewSheet(p) {
    const labels={purchase:'采购',packaging:'包装',logistics:'国内物流',expected_after_sales:'预期售后',other_variable:'其他可变成本'};
    return `<h3>供货评审单 · ${esc(p.candidate_id)}</h3><p class="meta">${esc(p.created_at)} · 全托管 · ${esc(p.research_market)}</p>
      <h4 style="margin-top:16px">${esc(p.title||p.product_record?.title)}</h4><p class="meta">${esc(p.market_title||'')}</p>
      <div class="table-wrap" style="margin-top:12px"><table><thead><tr><th>商家 SKU</th><th>件数</th><th>原报价</th><th>当前核价</th><th>完整成本/旧版成本</th><th>目标底价</th><th>净收益/旧版贡献</th></tr></thead><tbody>${p.skus.map(s=>{
        const x=(s.active_evaluation||s.evaluation).values||{};
        const full=s.full_profit?.scenarios?.baseline;
        return `<tr><td>${esc(s.merchant_sku)}</td><td>${s.pieces}</td><td>${amount(s.supply_income.amount)}</td><td>${amount(x.supply_income)} ${esc(x.currency)}</td><td>${full?Number(full.total_cost).toFixed(2):amount(x.variable_cost)}</td><td>${full?amount(full.combined_target_price??full.target_price):amount(x.minimum_supply_income)}</td><td>${full?Number(full.net_profit).toFixed(2):amount(x.contribution)}</td></tr>`;
      }).join('')}</tbody></table></div>
      <p class="callout">${esc(p.next_action||'')}</p>
      <details class="accordion" open><summary>评审待办 · ${p.unverified_items.length} 项</summary>${p.unverified_items.map(x=>`<p class="meta">□ ${esc(x)}</p>`).join('')||'<p class="meta">已登记资料仍需按实际平台任务审核。</p>'}</details>
      <details class="accordion"><summary>规格、包装与成本明细</summary>${p.skus.map(s=>`<h4>${esc(s.merchant_sku)}</h4><p class="meta">${(s.pack_composition||[]).map(c=>`${esc(c.name)} × ${c.count} · ${esc((c.product_dimensions_cm||[]).join('×'))} cm`).join('；')}</p><p class="meta">包装 ${esc(Object.values(s.specs?.package?.dimensions||{}).filter(x=>x!=null&&x!=='cm').join('×'))} cm · 净重 ${esc(s.specs?.weight?.net_weight_g||'—')}g / 毛重 ${esc(s.specs?.weight?.gross_weight_g||'—')}g</p>${(s.costs||[]).map(c=>`<p class="meta">${esc(labels[c.key]||c.key)}：${amount(c.money.amount)} ${esc(c.money.currency)} · ${esc(c.money.source_ref||'待补凭证')}</p>`).join('')}`).join('')}</details>
      <details class="accordion"><summary>市场依据与核价历史</summary>${p.evidence_links.map(e=>`<p class="meta"><a href="${esc(e.url||'#')}" target="_blank" rel="noopener">${esc(e.id)}</a> · ${esc(e.locator||'')}</p>`).join('')}${p.feedback.map(f=>`<p class="meta">${esc(f.feedback_date||'')} · ${esc(f.feedback_text)} · ${esc(f.evidence_ref||'待补凭证')}</p>`).join('')}</details>
      ${p.skus.filter(s=>s.full_profit?.scenarios?.baseline).map(s=>`<details class="accordion"><summary>${esc(s.merchant_sku)} · 完整利润计算过程</summary>${ProfitUI.reportCharts(s.full_profit)}${ProfitUI.detailTable(s.full_profit.scenarios.baseline)}<p class="meta">保守情景净收益 ${esc(s.full_profit.scenarios.conservative.net_profit)}；${s.full_profit.notes.map(esc).join(' ')}</p></details>`).join('')}
      <p class="meta" style="margin-top:12px">内部评审资料；平台类目与任务字段以当前后台核验结果为准。完整模型为含税现金及分摊口径的净收益估算，实际账务与税费核实后方可确认已实现利润。</p>`;
  }
  return {finance,reviewSheet};
})();
