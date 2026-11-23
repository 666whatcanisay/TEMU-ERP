/* Complete supplier economics presentation. Calculations are backend-only. */
// Keep internal method links on the address being used, including phone tunnels.
window.WorkbenchURL = value => {
  try {
    const url = new URL(value, window.location.href);
    if (['127.0.0.1', 'localhost'].includes(url.hostname) && url.port === '8765')
      return new URL(url.pathname + url.search + url.hash, window.location.origin).href;
  } catch (_) { /* Preserve existing non-URL reference identifiers. */ }
  return value;
};
window.ProfitUI=(()=>{
  let meta={},scene='baseline';
  const e=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const n=x=>Number(x||0), money=x=>x==null?'—':n(x).toFixed(2), pct=x=>x==null?'—':(n(x)*100).toFixed(2)+'%';
  const source=id=>{
    const s=(meta.sources||[]).find(s=>s.id===id);
    return s?.url?`<a href="${e(WorkbenchURL(s.url))}" target="_blank" rel="noopener">${e(s.publisher||s.title||id)}</a>`:
      /^https?:\/\//.test(id||'')?`<a href="${e(id)}" target="_blank" rel="noopener">原文</a>`:`<span>${e(id||'内部预算')}</span>`;
  };
  function breakdown(s,key,label,sceneLabel){
    const groups=key==='allocation-capital'?['allocation','capital']:[key];
    let rows=s.rows.filter(r=>groups.includes(r.group));
    let total=s.groups.filter(g=>groups.includes(g.key)).reduce((sum,g)=>sum+n(g.amount),0).toFixed(4);
    let explanation='按每销售单位分摊；正数为成本，负数为补贴或回收冲回。';
    if(key==='income'){
      rows=[{label:'当前供货收入',amount:s.price,formula:'当前情景采用的每销售单位供货价',kind:'recorded',source_id:'PROFIT-ASSUMPTIONS'}];
      total=s.price; explanation='这是供货收入，不是消费者零售价；来源与核价凭证见商品资料。';
    } else if(key==='net'){
      rows=[{label:'供货收入',amount:s.price,formula:'本次供货价',kind:'recorded'},...s.groups.map(g=>({label:g.label,amount:(-n(g.amount)).toFixed(4),formula:'从供货收入扣减；负成本冲回收入',kind:'estimate'}))];
      total=s.net_profit; explanation=`供货收入 ${s.price} − 完整成本 ${s.total_cost} = 净收益 ${s.net_profit}；预算测算，尚非账单确认利润。`;
    }
    const visible=rows.filter(r=>n(r.amount)!==0), omitted=rows.length-visible.length;
    const shown=visible.length?visible:rows;
    const sourceIds=[...new Set(['PROFIT-ASSUMPTIONS',...rows.map(r=>r.source_id)])].filter(id=>(meta.sources||[]).some(s=>s.id===id&&s.url));
    return `<header class="profit-breakdown-head"><div><h4>${e(label)} · 费用明细</h4><p>${e(sceneLabel)}情景 · ${e(s.currency)} / ${e(({set:'套',piece:'件',pack:'包'})[s.sales_unit]||s.sales_unit)}</p></div><button type="button" class="profit-breakdown-close" aria-label="关闭费用明细">×</button></header>
      <table class="profit-breakdown-table"><thead><tr><th>项目</th><th>当前计算</th><th>金额</th></tr></thead><tbody>${shown.map(r=>`<tr><td>${e(r.label)}<small>${r.kind==='actual'?'账单金额':r.kind==='recorded'?'录入金额':'预算估值'}</small></td><td>${e(r.formula)}</td><td>${e(r.amount)}</td></tr>`).join('')}</tbody><tfoot><tr><th>${key==='net'?'净收益':'合计'}</th><td>图上按分显示 ${money(total)} ${e(s.currency)}</td><th>${e(total)}</th></tr></tfoot></table>
      <p class="profit-breakdown-note">${e(explanation)}${omitted&&visible.length?` 另有 ${omitted} 项金额为0，完整明细仍保留。`:''}</p>
      <div class="profit-breakdown-sources">${sourceIds.map(source).join(' · ')}</div><p class="profit-breakdown-note">出处用于核对费用类别；未取得真实账单的金额和概率为可调整预算，不是平台统一费率。</p>`;
  }
  function waterfall(s,sceneLabel='基准'){
    const by=Object.fromEntries(s.groups.map(x=>[x.key,n(x.amount)]));
    const blocks=[['供货收入',n(s.price),'total','income'],['商品履约',-by.direct,null,'direct'],['退款风险',-by.risk,null,'risk'],['平台服务',-by.fulfillment,null,'fulfillment'],['分摊资金',-(by.allocation+by.capital),null,'allocation-capital'],['税费',-by.tax,null,'tax'],['净收益',n(s.net_profit),'total','net']];
    let at=0;const levels=[];
    blocks.forEach(([label,v,type,key],i)=>{const start=type==='total'?0:at; const end=type==='total'?v:at+v; levels.push({label,v,start,end,type,key});if(i===0||type!=='total')at=end;});
    const min=Math.min(0,...levels.flatMap(x=>[x.start,x.end])),max=Math.max(1,...levels.flatMap(x=>[x.start,x.end]));
    const y=x=>205-(x-min)/(max-min)*160;
    return `<div class="profit-waterfall"><svg viewBox="0 0 620 255" role="group" aria-label="每销售单位供货收入到税后净收益瀑布图"><title>单位 ${e(s.currency)}；悬停、聚焦或点击各项目查看明细</title><line x1="15" y1="${y(0)}" x2="610" y2="${y(0)}" stroke="#cbd5e1"/>${levels.map((x,i)=>{
      const x0=24+i*84,top=Math.min(y(x.start),y(x.end)),h=Math.max(2,Math.abs(y(x.start)-y(x.end)));
      return `<g class="chart-mark" data-profit-breakdown="${x.key}" tabindex="0" role="button" aria-haspopup="dialog" aria-expanded="false" aria-label="${e(x.label)} ${money(x.v)} ${e(s.currency)}，查看计算明细"><rect class="chart-hit-area" x="${x0-12}" y="8" width="80" height="242" fill="transparent"/><rect class="chart-value-bar" x="${x0}" y="${top}" width="56" height="${h}" rx="3" fill="${x.type==='total'?(x.v<0?'#b23a3a':'#c24e0c'):x.v>0?'#1f7a55':'#8fa5bb'}"/><text x="${x0+28}" y="${Math.max(16,top-7)}" text-anchor="middle" fill="#273449" font-size="12">${x.type==='total'?'':x.v<0?'−':'+'}${money(Math.abs(x.v))}</text><text x="${x0+28}" y="235" text-anchor="middle" fill="#627083" font-size="11">${x.label}</text></g>`;
    }).join('')}</svg>${levels.map(x=>`<template data-breakdown-content="${x.key}">${breakdown(s,x.key,x.label,sceneLabel)}</template>`).join('')}</div>`;
  }
  function sensitivity(all){
    const b=all.baseline.sensitivity,c=all.conservative.sensitivity;
    const values=[...b,...c].map(x=>n(x.net_profit)),min=Math.min(0,...values),max=Math.max(1,...values),range=max-min||1;
    const x=i=>50+i*62,y=v=>205-(v-min)/range*160;
    return `<svg viewBox="0 0 620 255" role="img" aria-label="供货价与税后净收益敏感性曲线"><title>横轴供货价，纵轴每销售单位税后净收益；情景并非实际历史</title><line x1="45" y1="${y(0)}" x2="565" y2="${y(0)}" stroke="#cbd5e1"/><text x="5" y="20" font-size="10" fill="#627083">净收益</text>${[['基准',b,'#c24e0c',false],['保守',c,'#627083',true]].map(([label,data,color,dash])=>`<polyline points="${data.map((p,i)=>`${x(i)},${y(n(p.net_profit))}`).join(' ')}" fill="none" stroke="${color}" stroke-width="2.5" ${dash?'stroke-dasharray="5 4"':''}/>${data.map((p,i)=>`<g tabindex="0" class="chart-mark" role="graphics-symbol" aria-label="${label} 供货价${p.price} 净收益${money(p.net_profit)}"><title>${label}：供货价 ${money(p.price)} → 净收益 ${money(p.net_profit)}</title><circle cx="${x(i)}" cy="${y(n(p.net_profit))}" r="4" fill="${color}"/>${!dash&&i%2===0?`<text x="${x(i)}" y="230" text-anchor="middle" font-size="10" fill="#627083">${money(p.price)}</text>`:''}</g>`).join('')}`).join('')}<text x="240" y="250" font-size="10" fill="#627083">供货价（${e(all.baseline.currency)}）</text></svg><div class="chart-legend"><span><i style="background:#c24e0c"></i>基准</span><span><i style="background:#627083"></i>保守</span></div>`;
  }
  function detailTable(s){
    return `<div class="table-wrap"><table><thead><tr><th>费用</th><th>每销售单位</th><th>计算过程</th><th>依据</th></tr></thead><tbody>${s.rows.map(r=>`<tr><td>${e(r.label)}<small class="meta"> · ${r.kind==='actual'?'账单替换':r.kind==='recorded'?'已录入':'估值'}</small></td><td>${e(r.amount)}</td><td>${e(r.formula)}</td><td>${source(r.source_id)}${r.kind==='estimate'?`<br><small>数值：${source(r.value_source_id)}</small>`:''}</td></tr>`).join('')}<tr><th>成本合计</th><th>${e(s.total_cost)}</th><td>供货价 − 成本合计 = ${e(s.net_profit)}</td><td>${e(s.currency)}/${e(s.sales_unit)}</td></tr></tbody></table></div>`;
  }
  function card(v,detail){
    const full=v.full_profit,all=full.scenarios,s=all[scene],bad=s.status==='LOSS'||s.status==='BELOW_TARGET';
    return `<div class="quote-summary ${bad?'negative':''}" data-testid="full-profit" data-sku="${e(v.sku.merchant_sku)}">
      <div class="panel-title"><strong>${e(v.sku.merchant_sku)}</strong><span class="tag ${bad?'bad':v.active_evaluation.status==='MEETS_THRESHOLD'?'good':'warn'}">${s.status==='LOSS'?'完整成本后亏损':s.status==='BELOW_TARGET'?'低于净收益目标':v.active_evaluation.status==='MEETS_THRESHOLD'?'净收益预算达标':'净收益达标，原贡献条件待满足'}</span></div>
      <div class="profit-scene"><span>税后净收益估算 · ${scene==='baseline'?'基准':'保守'}情景</span><div><button class="btn small ${scene==='baseline'?'active-scene':''}" data-profit-scene="baseline">基准</button><button class="btn small ${scene==='conservative'?'active-scene':''}" data-profit-scene="conservative">保守</button><button class="help-btn" data-source="PROFIT-ASSUMPTIONS" aria-label="利润计算与估值依据">?</button></div></div>
      <div class="quote-metrics"><div><small>${v.buyer_evaluation?'当前买手核价':'拟报供货价'} · ${e(s.currency)}</small><strong data-testid="active-price">${money(s.price)}</strong><small>原报价 ${money(v.sku.supply_income.amount)}</small></div><div><small>完整成本（含税费准备）</small><strong data-testid="full-cost">${money(s.total_cost)}</strong><small>采购/履约/风险/分摊/资金/税费</small></div><div><small>税后净收益估算</small><strong data-testid="net-profit">${money(s.net_profit)}</strong><small>对名义供货价 ${pct(s.net_margin)}</small></div><div><small>综合目标底价</small><strong data-testid="net-target-price">${money(s.combined_target_price??s.target_price)}</strong><small>净收益${e(s.target_percent)}%底价 ${money(s.target_price)} · 保本 ${money(s.break_even_price)}</small></div></div>
      ${bad?`<p class="callout bad">${s.status==='LOSS'?'当前价格不足以覆盖完整成本。':'当前估值下未达到净收益目标。'}${s.target_price?`综合目标供货价至少 ${money(s.combined_target_price??s.target_price)} ${e(s.currency)}。`:'当前参数下目标不可达。'}</p>`:''}
      ${scene==='baseline'&&all.conservative.status!=='MEETS_TARGET'?`<p class="callout warn">保守情景净收益 ${money(all.conservative.net_profit)}，${pct(all.conservative.net_margin)}${all.conservative.status==='LOSS'?'，出现亏损':'，低于净收益目标'}：优先核实采购、退回、扣款与分摊数量。</p>`:''}
      <div class="profit-charts"><div><h4>收入如何变成净收益</h4>${waterfall(s,scene==='baseline'?'基准':'保守')}</div><div><h4>核价变化影响</h4>${sensitivity(all)}</div></div>
      <details class="accordion"><summary>计算过程与费用明细 · ${s.rows.length} 项</summary>${detailTable(s)}<p class="meta">${full.notes.map(e).join(' ')}</p></details>
      <details class="accordion"><summary>原报价与五项贡献口径</summary><p class="meta">原报价 ${money(v.sku.supply_income.amount)}；当前五项贡献 ${e(v.active_evaluation.values?.contribution||'—')}，贡献率 ${pct(v.active_evaluation.values?.contribution_margin)}。原贡献率政策 ${e(detail.policy?.threshold_percent||'未设置')}% 对应底价 ${money(s.legacy_target_price)}；五项贡献未扣完整运营/资金/税费，与净收益率目标分开。综合底价取已确认原政策与净收益目标底价的较高值。</p><p class="meta">核价凭证：${e(v.buyer_supply_income?.source_ref||v.sku.supply_income.source_ref||'待补')}</p></details>
      <details class="accordion"><summary>数量分摊与首批资金</summary><p class="meta">首批资金需求估算 ${money(s.initial_cash_required)} ${e(s.currency)}（商品/正向履约、分配保证金和一次性费用）；保证金本金不作为利润成本。全店月加权结算数量 ${e(s.allocation_inputs.company_weighted_units)}，本SKU权重 ${e(s.allocation_inputs.sku_weight)}，开发摊销量 ${e(s.allocation_inputs.lifetime_units)}，资金占用 ${e(s.allocation_inputs.cash_days)}天。这些数量为测算输入，不是已观测销量。</p></details>
      <p class="meta">估值可在「编辑 SKU → 完整成本参数」调整；${source('MIAO-FULL-FINANCE')} · ${source('PROFIT-ASSUMPTIONS')}</p>
    </div>`;
  }
  function editor(sku,help){
    if(!sku.profit_plan)return `<button class="btn" data-enable-profit>启用完整利润测算</button>`;
    const groups={labor:'逐件人工',fulfillment:'平台服务与收款',risk:'退回损耗与扣款',income:'可核对补贴与退费',allocation:'固定费用与开发分摊',capital:'资金占用',tax:'税费准备',target:'目标'};
    return `<details class="accordion"><summary>完整成本参数 ${help('profit')}</summary><p class="meta">默认数值为可调整预算；规则出处不代表其公布了默认金额或概率。原售后汇总项在完整模型中排除。</p>${Object.entries(groups).map(([group,label])=>`<details class="accordion"><summary>${label}</summary><div class="fields">${(meta.profit_schema||[]).filter(f=>f.group===group).map(f=>`<label class="field">${e(f.label)} · ${e(f.unit)} ${help(null,f.source_id)}<input data-profit-input="${f.key}" inputmode="decimal" value="${e(sku.profit_plan.inputs?.[f.key]??f.default)}"><span class="sub">${e(f.note)}</span></label>`).join('')}</div></details>`).join('')}</details>`;
  }
  function portfolio(candidates){
    const items=candidates.flatMap(c=>(c.profit_summaries||[]).map(p=>({...p,id:c.id,title:c.title})));
    if(!items.length)return '';
    const limit=Math.max(1,...items.flatMap(p=>[Math.abs(n(p.baseline.net_profit)),Math.abs(n(p.conservative.net_profit))]));
    return `<section class="panel" data-testid="profit-portfolio"><div class="panel-title"><h3>候选净收益对比</h3><span class="hint">${items.length} 个商品/SKU · ${e(items[0].baseline.currency)}/销售单位</span></div><div class="chart-legend"><span><i style="background:#c24e0c"></i>基准</span><span><i style="background:#627083"></i>保守</span><span>零轴左侧为亏损</span></div>${items.map(p=>`<div class="profit-compare-row"><button class="link-btn" data-open="${e(p.id)}">${e(p.title)}<small>${e(p.sku)} · ${p.baseline.sales_unit==='set'?'每套':'每件'}</small></button><div>${[['基准',p.baseline,'#c24e0c'],['保守',p.conservative,'#627083']].map(([label,s,color])=>{const val=n(s.net_profit);return `<div class="profit-track" tabindex="0" aria-label="${e(p.title)} ${label} 净收益${money(val)}" title="${label}：供货价${money(s.price)}，完整成本${money(s.total_cost)}，净收益${money(val)}"><div class="profit-bar" style="left:${val<0?50-Math.abs(val)/limit*48:50}%;width:${Math.abs(val)/limit*48}%;background:${val<0?'#b23a3a':color}"></div></div>`;}).join('')}</div><div class="profit-comparison-values"><strong>${money(p.baseline.net_profit)}</strong><small>保守 ${money(p.conservative.net_profit)}</small></div></div>`).join('')}<details class="accordion"><summary>查看报价与底价表</summary><div class="table-wrap"><table><thead><tr><th>商品</th><th>供货价</th><th>完整成本</th><th>净收益估算</th><th>保守净收益</th><th>综合目标底价</th></tr></thead><tbody>${items.map(p=>`<tr><td>${e(p.title)}</td><td>${money(p.baseline.price)}</td><td>${money(p.baseline.total_cost)}</td><td>${money(p.baseline.net_profit)}</td><td>${money(p.conservative.net_profit)}</td><td>${money(p.baseline.combined_target_price??p.baseline.target_price)}</td></tr>`).join('')}</tbody></table></div></details><p class="meta">供货与成本输入为预算；各商品销售单位、分摊权重和计划数量不同，不按图表推断真实销量或市场排名。</p></section>`;
  }
  const reportCharts=full=>`<div class="profit-charts"><div><h4>收入到税后净收益 · 基准</h4>${waterfall(full.scenarios.baseline)}</div><div><h4>核价敏感性</h4>${sensitivity(full.scenarios)}</div></div>`;
  return {configure:x=>{meta=x;},setScene:x=>{scene=x;},card,editor,portfolio,detailTable,reportCharts};
})();
