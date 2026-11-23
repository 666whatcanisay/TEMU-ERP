/* Temu 选品提报工作台 · 前端（原生 JS，无构建步骤）。
 * 前端只调用本地用例接口；计算与校验在后端领域模块完成。 */
"use strict";

const state = {
  view: "research",
  candidates: [],
  meta: null,
  detail: null,
  selectedId: null,
  panel: null,
  draft: null,
};

const STAGE_LABELS = {
  unsubmitted: "尚未提报", selection: "选品中", sample: "待寄样/看样", review: "审版中",
  pricing: "核价中", first: "待首单/备货", stock: "备货/发货/质检", sale: "平台已安排售卖",
  returned: "退回/不通过",
};
const DECISION_LABELS = {
  research: "继续补证据", request_sample: "联系供应商评估", internal_review: "拟内部评审",
  paused: "暂缓", excluded: "排除",
};
const MATERIALS = [
  ["supplier", "供应商报价、样品及交期"],
  ["photos", "自有或授权的商品/包装实拍"],
  ["measure", "尺寸与称重材料"],
  ["compliance", "原产地、生产与目标市场合规材料"],
  ["template", "全托管实际类目字段模板"],
  ["sample", "寄样或线上看样任务"],
];
const STATUS_LABELS = {
  NEEDS_DATA: "待补金额", NEEDS_POLICY: "未配置政策（仅情景）",
  NEEDS_POLICY_CONFIRMATION: "政策未确认（仅情景）", NEEDS_DATA_CONFIRMATION: "金额/来源未确认（仅情景）",
  UNIT_MISMATCH: "币种/单位不一致", INVALID_INPUT: "输入异常", INVALID_POLICY: "政策参数异常",
  UNDEFINED_METRIC: "成本为零，加价率无定义", MEETS_THRESHOLD: "达到收益门槛", BELOW_THRESHOLD: "低于门槛",
};
const STATUS_CLASS = {
  MEETS_THRESHOLD: "good", BELOW_THRESHOLD: "bad", NEEDS_DATA: "warn", UNIT_MISMATCH: "bad",
  INVALID_INPUT: "bad", INVALID_POLICY: "bad", UNDEFINED_METRIC: "bad",
};

const HELP_TIPS = {
  profit:{title:'完整利润测算',body:'供货收入扣除商品履约、商家责任退款、退回、损耗、扣款、平台服务、运营/开发分摊、资金占用和税费准备。默认风险与费用为可改估值，金额出处与费用类型出处分开。'},
  "pricing-margin": { title: "收入贡献率", body: "贡献率 =（供货收入 P − 可变成本 C）/ P，按供货收入计算。未扣固定人工、租金与税。" },
  "pricing-markup": { title: "成本加价率", body: "加价率 =（P − C）/ C，按成本计算。贡献率与加价率是两个口径，不能混称。" },
  policy: { title: "经营门槛政策", body: "40/50/60/70% 是可配置的公司门槛，不是 Temu 官方规定。政策未确认前，结果只作为情景展示，不自动判定可选品。" },
  ids: { title: "商家编码与平台 ID", body: "商家货号与平台商品/SKC/SKU ID 相互独立。平台 ID 未返回时保持空值，不从商家货号推导，也不复制 SDK 示例数值。" },
  sales: { title: "销量口径", body: "评价数、搜索趋势指数、展示排名都不是销量；未观察到统计窗口的销量保持空值，不补写月销量。" },
  materials: { title: "材料登记", body: "勾选“已提供”不等于“符合平台标准”。竞品图片仅作研究参考，提报素材须自有或已获授权。" },
  submission: { title: "内部提报记录", body: "这里生成的是内部整理记录，不是 Temu 平台导入模板；未经真实类目模板核对，不能直接上传平台。" },
  specs: { title: "尺寸与重量", body: "单件、套装与包装的尺寸、净重/毛重分开记录并标注单位；缺值先留空，不合理或单位错配要回到具体记录核对。销售轴与单位枚举以后台真实类目模板为准。" },
  composition: { title: "套装组成", body: "套装内每件物品的名称、数量与尺寸逐条登记，不靠标题文字推断；同款多件与混合套装的分类映射待真实模板核对，未确认前保持空值。" },
  bindings: { title: "销售属性组合", body: "颜色、件数等只是样例组织法，不能硬编码所有类目按颜色建 SKC；平台销售属性、枚举与属性 ID 以后台真实模板为准，未返回前属性 ID 保持空值。" },
};

const HELP_SOURCES = {
  profit:['PROFIT-ASSUMPTIONS','MIAO-FULL-FINANCE','DXM-FINANCE','CN-CIT'],
  'pricing-margin':['INTERNAL-METHOD'], 'pricing-markup':['INTERNAL-METHOD'], policy:['INTERNAL-METHOD'],
  ids:['SDK-GO-CREATE','DXM-FULL'], sales:['GOOGLE-TRENDS','INTERNAL-METHOD'],
  materials:['DXM-FULL','TEMU-IP','EU-GPSR','DE-PACK'], submission:['DXM-FULL','TEMU-ATTRS-ENTRY'],
  specs:['MIAO-FULL','DXM-FULL'], composition:['MIAO-FULL','DXM-FULL'], bindings:['SDK-GO-ATTRS','TEMU-ATTRS-ENTRY'],
};
const COST_KEYS = ["purchase", "packaging", "logistics", "expected_after_sales", "other_variable"];

function emptyMoney() {
  return { amount: null, currency: "CNY", sales_unit: "set", confirmed: false, source_ref: null };
}

function emptySpecs() {
  return {
    dimensions: { length_cm: null, width_cm: null, height_cm: null, unit: "cm" },
    weight: { net_weight_g: null, gross_weight_g: null, unit: "g" },
  };
}

function blankSku(merchantSku, groupCode) {
  return {
    merchant_sku: merchantSku,
    merchant_group_code: groupCode || null,
    platform_sku_id: null,
    platform_skc_id: null,
    sales_unit: "set",
    pieces: 1,
    sale_spec_bindings: [],
    specs: emptySpecs(),
    pack_composition: [],
    supply_income: emptyMoney(),
    costs: COST_KEYS.map((key) => ({ key, money: emptyMoney() })),
  };
}

function ensureSpecs(sku) {
  if (!sku.specs || typeof sku.specs !== "object") sku.specs = emptySpecs();
  sku.specs.dimensions = sku.specs.dimensions || { length_cm: null, width_cm: null, height_cm: null, unit: "cm" };
  sku.specs.weight = sku.specs.weight || { net_weight_g: null, gross_weight_g: null, unit: "g" };
  for(const layer of ['item','package']) sku.specs[layer] ||= emptySpecs();
  return sku;
}

function esc(x) {
  return String(x == null ? "" : x).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function api(path, options = {}) {
  const resp = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok && data.errors?.length) return {status:'failed',...data};
  if (!resp.ok) { const message=data.error||`HTTP ${resp.status}`; toast(message); throw new Error(message); }
  return data;
}

function toast(msg) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { el.hidden = true; }, 3200);
}

// ---------- data loading ----------
async function init() {
  const query=new URLSearchParams(location.search);
  state.selectedId=query.get('candidate');
  state.view=['research','submission','feedback'].includes(query.get('view'))?query.get('view'):'research';
  state.meta = await api("/api/meta");
  await refreshCandidates();
  if (state.selectedId) await loadDetail(state.selectedId);
  bindChrome();
  render();
}

async function refreshCandidates() {
  const data = await api("/api/candidates");
  state.candidates = data.candidates;
  if (!state.selectedId && state.candidates.length) state.selectedId = state.candidates[0].id;
}

async function loadDetail(id) {
  state.editingSourceId=null;
  state.selectedId = id;
  state.detail = await api(`/api/candidates/${id}`);
  state.draft = JSON.parse(JSON.stringify(state.detail.candidate));
  history.replaceState(null,'',`?candidate=${encodeURIComponent(id)}&view=${state.view}`);
}

// ---------- chrome ----------
function bindChrome() {
  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchView(btn.dataset.view));
  });
  document.querySelectorAll("[data-panel]").forEach((btn) => {
    btn.addEventListener("click", () => openDrawer(btn.dataset.panel));
  });
  document.getElementById("drawer-backdrop").addEventListener("click", closeDrawer);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { closeDrawer(); closePopover(); }
  });
  document.addEventListener("click", (e) => {
    if (!e.target.closest("#help-popover") && !e.target.closest(".help-btn")) closePopover();
  });
}

function switchView(view) {
  state.view = view;
  if(state.selectedId) history.replaceState(null,'',`?candidate=${encodeURIComponent(state.selectedId)}&view=${view}`);
  closeDrawer();
  render();
}

function render() {
  ProfitUI.configure(state.meta||{});
  document.querySelectorAll(".nav-btn").forEach((b) => b.classList.toggle("active", b.dataset.view === state.view));
  const root = document.getElementById("view-root");
  if (state.view === "research") root.innerHTML = renderResearch();
  else if (state.view === "submission") root.innerHTML = renderSubmission();
  else root.innerHTML = renderFeedback();
  if (state.view === 'research' && state.detail) renderResearchDetail();
  bindViewEvents();
  if (state.view === 'submission' && state.detail?.candidate.title === '新候选商品') {
    const form = document.getElementById('product-information');
    const firstResult = root.querySelector('.finance-panel, #preparation-summary');
    if (form && firstResult) root.insertBefore(form, firstResult);
  }
}

// ---------- shared bits ----------
function sourceById(id) {
  return (state.meta?.sources || []).find((s) => s.id === id);
}

function helpButton(key, sourceId) {
  const attr = sourceId ? `data-source="${esc(sourceId)}"` : `data-help="${esc(key)}"`;
  return `<button class="help-btn" ${attr} tabindex="0" aria-label="查看说明与来源">?</button>`;
}

function statusTag(status) {
  const cls = STATUS_CLASS[status] || "warn";
  return `<span class="tag ${cls}">${esc(STATUS_LABELS[status] || status)}</span>`;
}

function fmtNum(x) {
  if (x == null || x === "") return "—";
  return x;
}

function renderExtractedCandidates(source) {
  const facts = source && source.facts;
  const cands = facts && facts.extracted_candidates;
  if (!cands || typeof cands !== "object") return "";
  const entries = Object.entries(cands);
  if (!entries.length) return "";
  const rows = entries.map(([key, f]) => {
    const field = f || {};
    return `<div class="extracted-row" data-testid="extracted-candidate">
      <span class="tag warn">${esc(field.confirmation || "extracted_candidate")}</span>
      <strong>${esc(key)}</strong>
      <span>${esc(String(field.value == null ? "" : field.value))}</span>
      <span class="meta">${esc(field.locator || "")} · ${esc(field.extraction_method || "rule")}</span>
    </div>`;
  }).join("");
  return `<div class="extracted-box" data-testid="extracted-box">
    <p class="meta">程序提取候选（未人工确认，不能当作已核对字段；需在编辑器中手动校正后保存）：</p>
    ${rows}
  </div>`;
}

// ---------- view: research ----------
function renderResearch() {
  const rows = state.candidates.map((c) => `
    <div class="list-row">
      <div class="main">
        <div class="title">${esc(c.title)}</div>
        <div class="meta">市场：${esc(c.research_market || "—")} · 证据 ${c.evidence_count} 条 · ${esc(c.next_action)}</div>
      </div>
      ${statusDecision(c.internal_decision)}
      <button class="btn small" data-open="${esc(c.id)}">查看详情</button>
    </div>`).join("");

  return `
    <div class="view-head">
      <div><h2>候选研究</h2><p>汇集市场依据，核对规格与供货空间。</p></div>
      <button class="btn primary" data-new-candidate data-testid="new-candidate">新建候选</button>
    </div>
    ${ProfitUI.portfolio(state.candidates)}
    <section class="panel" id="candidate-list">
      <div class="panel-title"><h3>候选列表</h3><span class="hint">当前决定与下一步</span></div>
      <div class="list">${rows || "<p class='meta'>暂无候选。</p>"}</div>
    </section>
    <section id="research-detail"></section>`;
}

function statusDecision(decision) {
  const map = { research: "brand", request_sample: "brand", internal_review: "good", paused: "warn", excluded: "bad" };
  return `<span class="tag ${map[decision] || ""}">${esc(DECISION_LABELS[decision] || decision)}</span>`;
}

async function openCandidate(id) {
  try {
    await loadDetail(id);
    if (state.view !== 'research') return;
    renderResearchDetail();
    bindResearchEvents();
    revealEntry(document.getElementById('research-detail'));
    document.getElementById('candidate-detail-title')?.focus({preventScroll:true});
  } catch (_) {
    toast('商品详情未能加载，请重试。');
  }
}

function renderResearchDetail() {
  const root = document.getElementById("research-detail");
  if (!root || !state.detail) return;
  const d = state.detail;
  const evidence = d.evidence.map((e) => {
    const s = e.source;
    const comp = e.comparability;
    const sales = e.sales;
    return `
      <div class="evidence-item">
        <div style="display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap">
          <h4>${esc(s.title || s.id)} ${helpButton(null, s.id)}</h4>
          <span class="tag">${esc(s.level)}</span>
        </div>
        <p>${esc(s.locator || "")}</p>
        ${s.url ? `<p><a href="${esc(WorkbenchURL(s.url))}" target="_blank" rel="noopener noreferrer">打开来源原文</a></p>` : "<p>无外部官方来源链接。</p>"}
        ${renderExtractedCandidates(s)}
        <div class="callout ${comp.comparable?'good':'warn'}">${comp.comparable?'规格可比':comp.status==='insufficient'?'资料不足':'规格不同'}${comp.reasons.length?'：'+comp.reasons.map(esc).join('；'):''}</div>
        <p>${s.facts?.display_price!=null?`展示价 ${esc(s.facts.display_price)} ${esc(s.facts.currency||'')} · `:''}${esc(s.scope?.pieces||'—')} 件/销售单位</p>
        ${e.sku_comparisons?.length>1?`<details class="accordion"><summary>逐 SKU 对账</summary>${e.sku_comparisons.map(x=>`<p>${esc(x.sku_ref)}：${x.comparable?'规格可比':x.status==='insufficient'?'资料不足':'规格不同'} ${x.reasons.map(esc).join('；')}</p>`).join('')}</details>`:''}
        ${sales.warnings.length ? `<div class="callout">${sales.warnings.map(esc).join("；")}</div>` : ""}
        <p>观察/记录：${esc(s.observed_at || s.retrieved_at || "—")} · 核验状态：${esc(s.verification)}</p>
        <button class="link-btn" data-edit-evidence="${esc(s.id)}">编辑观察数据</button>
      </div>`;
  }).join("");

  const c = d.candidate;
  root.innerHTML = `
    <section class="panel" data-testid="candidate-overview">
      <div class="panel-title"><h3 id="candidate-detail-title" tabindex="-1">${esc(c.title || c.id)} · 商品详情</h3><button class="link-btn" data-back-candidate-list>返回候选列表</button></div>
      <p class="meta">${esc(c.id)} · 研究市场 ${esc(c.research_market||'—')} · 材质 ${esc(c.material||'待填写')} · ${d.skus.length} 个 SKU</p>
      <div class="table-wrap" style="margin-top:12px"><table>
        <thead><tr><th>商家 SKU</th><th>件数/销售单位</th><th>当前供货价</th><th>基准净收益估算</th></tr></thead>
        <tbody>${d.skus.map(v=>{
          const sku=v.sku, active=v.active_evaluation||v.evaluation;
          const full=v.full_profit?.scenarios?.baseline;
          return `<tr><td>${esc(sku.merchant_sku)}</td><td>${esc(sku.pieces)} 件 / ${esc(({set:'套',piece:'件',pack:'包'})[sku.sales_unit]||sku.sales_unit)}</td><td>${esc(active.values?.supply_income??'待填写')} ${esc(active.values?.currency||sku.supply_income?.currency||'')}</td><td>${full?Number(full.net_profit).toFixed(2)+' '+esc(full.currency):'待补完整成本'}</td></tr>`;
        }).join('')}</tbody></table></div>
      <div class="workflow-actions"><button class="btn primary" data-research-product>查看商品资料与利润</button></div>
    </section>
    <section class="panel">
      <div class="panel-title"><h3>${esc(c.title || c.id)} · 证据与判断</h3>${statusDecision(c.internal_decision)}</div>
      <div class="fields">
        <label class="field wide">看到的事实与口径（人工录入）
          <textarea id="ev-text" rows="2" placeholder="记录国家、变体、价格条件、观察日期；没有显示的销量不要补写"></textarea>
        </label>
        <label class="field">来源链接<input id="ev-url" type="url" placeholder="https:// 商品或证据页面"></label>
        <label class="field">来源类型
          <select id="ev-level">
            <option value="market_observation">站外竞品/市场观察</option>
            <option value="supplier_info">供应商信息</option>
            <option value="industry_reference">行业参考</option>
          </select>
        </label>
      </div>
      <details class="accordion"><summary>规格与价格对账</summary>
        <div class="fields">
          <label class="field">展示价格<input id="ev-price" inputmode="decimal"></label>
          <label class="field">币种<input id="ev-currency" value="EUR"></label>
          <label class="field">每销售单位件数<input id="ev-pieces" type="number" min="1"></label>
          <label class="field">单件长,宽,高（cm）<input id="ev-dimensions" placeholder="12, 7, 5.5"></label>
          <label class="field">材质<input id="ev-material" placeholder="与候选统一口径，如 plastic"></label>
          <label class="field">市场<input id="ev-country" value="DE"></label>
          <label class="field">观察日期<input id="ev-date" type="date" value="${new Date().toLocaleDateString('en-CA')}"></label>
          <label class="check-line"><input id="ev-confirmed" type="checkbox"> 已对照原文核对上述数据</label>
        </div>
      </details>
      <div class="panel-title" style="margin-top:12px">
        <span></span>
        <button class="btn primary" id="add-evidence">加入证据记录</button>
      </div>
      <div>${evidence || "<p class='meta'>尚无关联证据。</p>"}</div>
    </section>
    <section class="panel">
      <div class="panel-title"><h3>内部决定</h3><span class="hint">内部判断，不代表买手或平台意见</span></div>
      <div class="fields">
        <label class="field">当前建议
          <select id="decision-select">
            ${Object.entries(DECISION_LABELS).map(([k, v]) => `<option value="${k}" ${c.internal_decision === k ? "selected" : ""}>${v}</option>`).join("")}
          </select>
        </label>
        <label class="field">理由与待核对假设<textarea id="decision-reason" rows="2">${esc(c.decision_history?.slice(-1)[0]?.reason || "")}</textarea></label>
      </div>
      <div class="panel-title" style="margin-top:12px">
        <span></span>
        <span style="display:flex;gap:8px">
          ${(c.internal_decision === "paused" || c.internal_decision === "excluded") ? '<button class="btn" id="restore-decision">撤销暂缓/排除</button>' : ""}
          <button class="btn primary" id="save-decision">保存决定</button>
        </span>
      </div>
    </section>`;
}

// ---------- view: submission ----------
function renderSubmission() {
  if (!state.detail || state.detail.candidate.id !== state.selectedId) {
    if (state.selectedId) loadDetail(state.selectedId).then(render);
    return `<div class="panel"><p>加载中…</p></div>`;
  }
  const d = state.detail;
  const c = d.candidate;
  const isNew = c.title === '新候选商品';
  const readiness = d.readiness.map((r) => `
    <div class="ready-row"><span>${esc(r.label)}</span>${statusTag(r.ok ? "MEETS_THRESHOLD" : "NEEDS_DATA").replace("达到收益门槛", r.status).replace("待补金额", r.status)}</div>
  `).join("");

  const skuRows = d.skus.map((v, i) => {
    const sku = v.sku;
    const ev = v.active_evaluation || v.evaluation;
    const full=v.full_profit?.scenarios?.baseline;
    return `
      <tr data-testid="sku-row" data-sku="${esc(sku.merchant_sku)}">
        <td><strong>${esc(sku.merchant_sku)}</strong><div class="meta">${esc(sku.merchant_group_code || "")}</div></td>
        <td>${sku.pieces} 件 / ${esc(({set:'套',piece:'件',pack:'包'})[sku.sales_unit]||sku.sales_unit)}</td>
        <td>${fmtNum(ev.values?.supply_income)} ${esc(ev.values?.currency || "")}</td>
        <td>${full?`<span class="tag ${full.status==='MEETS_TARGET'&&ev.status==='MEETS_THRESHOLD'?'good':full.status==='LOSS'||full.status==='BELOW_TARGET'?'bad':'warn'}">${full.status==='LOSS'?'亏损':full.status==='BELOW_TARGET'?'低于净目标':ev.status==='MEETS_THRESHOLD'?'预算达标':'原贡献条件待满足'}</span>`:statusTag(ev.status)}</td>
        <td>${full?Number(full.net_profit).toFixed(2):(ev.values?.contribution??'—')+'（五项贡献）'}</td>
        <td style="display:flex;gap:6px;flex-wrap:wrap">
          <button class="btn small" data-edit-sku="${i}" data-testid="edit-sku">编辑</button>
          ${d.skus.length > 1 ? `<button class="btn small" data-remove-sku="${i}" data-testid="remove-sku">删除</button>` : ""}
        </td>
      </tr>`;
  }).join("");

  const materials = MATERIALS.map(([key, label]) => `
    <div class="ready-row"><span>${esc(label)}</span><span style="display:flex;gap:12px"><label><input type="checkbox" data-material-required="${key}" ${c.material_requirements?.required?.includes(key)?'checked':''}> 本次要求</label><label><input type="checkbox" data-material="${key}" ${c.materials?.[key]?'checked':''}> 已备</label></span></div>`).join('');

  return `
    <div class="view-head">
      <div><h2>商品提报</h2><p>整理商品与 SKU 资料，准备内部评审。</p></div>
      <div class="submission-head-actions" style="display:flex;gap:8px">
        <select id="candidate-picker">${state.candidates.map((x) => `<option value="${esc(x.id)}" ${x.id === c.id ? "selected" : ""}>${esc(x.title)}</option>`).join("")}</select>
        <button class="btn primary" id="generate-submission" data-testid="generate-submission">生成内部提报资料</button>
      </div>
    </div>

    <section class="panel entry-shortcuts" aria-label="商品录入入口">
      <div><strong>${isNew?'开始填写新商品':'商品资料录入'}</strong><p class="meta">先填名称和货源，再填规格、包装、供货价与成本。</p></div>
      <div class="workflow-actions"><button class="btn ${isNew?'primary':''}" data-open-product>填写商品信息</button><button class="btn" data-open-first-sku>填写规格与成本</button></div>
    </section>
    ${WorkbenchUI.finance(d)}
    <section class="panel" id="preparation-summary">
      <details class="accordion"><summary>资料准备 <span class="tag warn">${d.readiness.filter(r=>!r.ok).length} 项待核对</span></summary>
      <div class="grid-2">
        <div>
          <div class="ready-row"><span>商家货号</span><strong>${esc(c.id)}</strong></div>
          <div class="ready-row"><span>SKU 数量</span><span>${d.skus.length}</span></div>
          <div class="ready-row"><span>研究市场</span><span>${esc(c.research_market || "—")}</span></div>
          <div class="ready-row"><span>平台商品 ID</span><span>${c.platform_product_id ? esc(c.platform_product_id) : "空（待平台返回）"}</span></div>
        </div>
        <div>${readiness}</div>
      </div>
      </details>
    </section>

    <section class="panel" id="product-information">
      <details class="accordion" id="product-details" ${isNew?'open':''}>
        <summary>商品信息 ${helpButton("ids")}</summary>
        <div class="fields" style="margin-top:12px">
          <label class="field wide">商品名称 / 中文标题<input id="f-title" value="${esc(c.title || "")}" placeholder="填写商品名称，例如：透明抽屉收纳盒6件套"></label>
          <label class="field wide">提报英文标题<input id="f-listing-title" data-testid="listing-title" value="${esc(c.listing_title||'')}"></label>
          <label class="field wide">德国市场标题<input id="f-market-title" value="${esc(c.market_title||'')}"></label>
          <label class="field">材质<input id="f-material" value="${esc(c.material||'')}" placeholder="如 plastic；细分材质以实物为准"></label>
          <label class="field wide">选品理由（市场证据分开写）<textarea id="f-rationale" rows="3">${esc(c.rationale || "")}</textarea></label>
          <label class="field wide">差异与供货优势（未证实内容保留为假设）<textarea id="f-advantage" rows="2">${esc(c.advantage || "")}</textarea></label>
          <label class="field">供应商链接<input id="f-supplier-url" value="${esc(c.supplier?.url || "")}" placeholder="真实货源链接，尚未提供"></label>
          <label class="field">MOQ（销售单位）<input id="f-moq" type="number" min="1" value="${esc(c.supplier?.moq || "")}"></label>
          <label class="field">交期（天）<input id="f-lead" type="number" min="0" value="${esc(c.supplier?.lead_days || "")}"></label>
          <label class="field wide">供货凭证<input id="f-supplier-ref" value="${esc(c.supplier?.source_ref||'')}" placeholder="报价单、供应商链接或文件索引"></label>
          <label class="check-line"><input id="f-supplier-confirmed" type="checkbox" ${c.supplier?.confirmed?'checked':''}> 已核对供货条件与凭证</label>
        </div>
        <div class="workflow-actions"><button class="btn ${isNew?'primary':''}" id="save-product" ${isNew?'data-next-sku':''}>${isNew?'保存并填写规格与成本':'保存商品资料'}</button></div>
      </details>

      <details class="accordion" id="sku-details" open>
        <summary>规格、包装与成本（SKU） ${helpButton("pricing-margin")}${helpButton("pricing-markup")}</summary>
        <div class="table-wrap" style="margin-top:12px">
          <table>
            <thead><tr><th>商家 SKU</th><th>件数/单位</th><th>供货收入</th><th>收益判定</th><th>基准净收益</th><th></th></tr></thead>
            <tbody>${skuRows}</tbody>
          </table>
        </div>
        <div class="panel-title" style="margin-top:10px">
          <span class="hint">同一商品下多个 SKU 独立编辑；平台销售轴以后台模板为准。</span>
          <button class="btn" id="add-sku" data-testid="add-sku">新增 SKU</button>
        </div>
        <div id="sku-editor"></div>
      </details>

      <details class="accordion">
        <summary>材料登记 ${helpButton("materials")}</summary>
        <div style="margin-top:10px">${materials}</div>
        <label class="field">本次要求依据<input id="materials-ref" value="${esc(c.material_requirements?.source_ref||'')}" placeholder="买手任务或真实类目模板索引"></label>
        <label class="check-line"><input id="materials-confirmed" type="checkbox" ${c.material_requirements?.confirmed?'checked':''}> 已核对本次材料要求</label>
        <div class="workflow-actions"><button class="btn" id="save-materials">保存材料清单</button></div>
        <p class="meta">按实际任务要求核对；登记不等于通过平台或合规审核。</p>
      </details>

      <details class="accordion">
        <summary>字段修订记录（${d.revisions.length}）</summary>
        <div class="table-wrap" style="margin-top:12px">
          <table>
            <thead><tr><th>时间</th><th>SKU</th><th>字段</th><th>修订前 → 修订后</th><th>记录人</th></tr></thead>
            <tbody>${revisionRows(d.revisions)}</tbody>
          </table>
        </div>
      </details>
      ${c.provenance?`<details class="accordion"><summary>资料依据与测算口径</summary><div class="meta">${Object.entries(c.provenance).map(([key,value])=>`<p><strong>${esc(({public_product:'商品公开资料',costs:'成本测算',packaging:'包装输入',feedback:'核价记录',policy:'经营门槛'})[key]||key)}</strong>：${esc(value.scope||value.reference||value.source_id||'')} ${value.url?`<a href="${esc(value.url)}" target="_blank" rel="noopener">原文</a>`:''}</p>`).join('')}</div></details>`:''}
    </section>

    <section class="panel" id="submission-output" hidden>
      <div class="panel-title"><h3>内部提报记录</h3><span class="tag warn">非 Temu 导入模板</span></div>
      <div class="callout warn" id="submission-banner"></div>
      <textarea id="submission-text" rows="14" readonly></textarea>
    </section>`;
}

function revisionRows(revisions) {
  if (!revisions || !revisions.length) {
    return '<tr><td colspan="5" class="meta">暂无字段修订；初始录入与后续修改都会留痕。</td></tr>';
  }
  return revisions.map((r) => `
    <tr>
      <td>${esc(r.created_at || "—")}</td>
      <td>${esc(r.sku_ref || "全部")}</td>
      <td>${esc(r.field_key)}</td>
      <td><span class="meta">${esc(JSON.stringify(r.before ?? null))}</span> → ${esc(JSON.stringify(r.after ?? null))}</td>
      <td>${esc(r.reviewer || "本地")}</td>
    </tr>`).join("");
}

function bindingRows(bindings) {
  return bindings.map((b, bi) => `
    <div class="comp-row" data-testid="binding-row">
      <label class="field">属性名<input data-binding-name="${bi}" value="${esc(b.name || "")}" placeholder="如：颜色"></label>
      <label class="field">属性值<input data-binding-value="${bi}" value="${esc(b.value ?? "")}" placeholder="如：透明"></label>
      <button class="btn small" data-binding-remove="${bi}" data-testid="remove-binding">移除</button>
    </div>`).join("") || '<p class="meta">暂无销售属性；颜色/件数等仅为样例组织法。</p>';
}

function skuEditor(sku, index) {
  ensureSpecs(sku);
  const costLabels = { purchase: "采购", packaging: "包装耗材", logistics: "国内正向运费", expected_after_sales: sku.profit_plan?'旧版售后汇总（完整模型排除）':"预期售后", other_variable: "入库/验货等其他变动费" };
  const costRows = COST_KEYS.map((key) => {
    const item = (sku.costs || []).find((x) => x.key === key) || { money: {} };
    const m = item.money || {};
    return `
      <div class="cost-item">
        <label class="field">${esc(costLabels[key])}<input type="text" inputmode="decimal" data-cost="${key}" value="${esc(m.amount ?? "")}" placeholder="0.00"></label>
        <details class="accordion"><summary>凭证与确认 <span data-cost-status="${key}" class="tag ${m.confirmed?'good':'warn'}">${m.confirmed?'已确认':'待确认'}</span></summary>
          <label class="field">来源/报价单<input data-cost-key="${key}" data-cost-field="source_ref" value="${esc(m.source_ref||'')}" placeholder="报价单编号、链接或本地文件索引"></label>
          <div class="fields"><label class="field">币种<input data-cost-key="${key}" data-cost-field="currency" value="${esc(m.currency||'CNY')}"></label><label class="field">销售单位<input data-cost-key="${key}" data-cost-field="sales_unit" value="${esc(m.sales_unit||sku.sales_unit)}"></label></div>
          <label class="check-line"><input type="checkbox" data-cost-key="${key}" data-cost-field="confirmed" ${m.confirmed?'checked':''}> 已核对本项金额与凭证</label>
        </details>
      </div>`;
  }).join("");
  const income = sku.supply_income || {};
  const dims = sku.specs.dimensions;
  const weight = sku.specs.weight;
  const compRows = (sku.pack_composition || []).map((item, ci) => `
    <div class="comp-row" data-testid="composition-row">
      <label class="field">物品名称<input data-comp-name="${ci}" value="${esc(item.name || "")}" placeholder="如：相同尺寸收纳盒"></label>
      <label class="field">数量<input data-comp-count="${ci}" type="number" min="1" value="${item.count ?? 1}"></label>
      <label class="field wide">单件尺寸（长,宽,高，${esc(dims.unit || "cm")}）<input data-comp-dims="${ci}" value="${esc((item.product_dimensions_cm || []).join(", "))}" placeholder="28, 9, 5"></label>
      <button class="btn small" data-comp-remove="${ci}" data-testid="remove-composition">移除</button>
    </div>`).join("");
  return `
    <div class="panel" style="margin-top:12px">
      <div class="panel-title"><h3>编辑 ${esc(sku.merchant_sku)}</h3><button class="link-btn" data-close-editor>收起</button></div>
      <div class="fields">
        <label class="field">商家 SKU 编码<input data-sku-field="merchant_sku" data-testid="sku-merchant" value="${esc(sku.merchant_sku)}"></label>
        <label class="field">商家分组编码<input data-sku-field="merchant_group_code" value="${esc(sku.merchant_group_code || "")}"></label>
        <label class="field">件数<input data-sku-field="pieces" type="number" min="1" value="${sku.pieces}"></label>
        <label class="field">销售单位<input data-sku-field="sales_unit" value="${esc(sku.sales_unit)}"></label>
        <label class="field">供货收入金额<input data-income="amount" inputmode="decimal" value="${esc(income.amount ?? "")}"></label>
        <label class="field">币种<input data-income="currency" value="${esc(income.currency || "CNY")}"></label>
        <label class="field">金额已确认<input type="checkbox" data-income="confirmed" ${income.confirmed ? "checked" : ""}></label>
        <label class="field">收入来源/凭证<input data-income="source_ref" value="${esc(income.source_ref || "")}"></label>
      </div>
      <div class="fields" style="margin-top:10px">${costRows}</div>
      ${ProfitUI.editor(sku,helpButton)}

      <details class="accordion" style="margin-top:12px">
        <summary>整套与包装尺寸 ${helpButton("specs")}</summary>
        <p class="meta">下方为销售单位本体；单件与运输包装分开记录。</p>
        <div class="fields" style="margin-top:10px">
          <label class="field">长<input data-spec="dimensions.length_cm" inputmode="decimal" value="${esc(dims.length_cm ?? "")}"></label>
          <label class="field">宽<input data-spec="dimensions.width_cm" inputmode="decimal" value="${esc(dims.width_cm ?? "")}"></label>
          <label class="field">高<input data-spec="dimensions.height_cm" inputmode="decimal" value="${esc(dims.height_cm ?? "")}"></label>
          <label class="field">长度单位<select data-spec="dimensions.unit">
            ${["cm"].map((u) => `<option value="${u}" ${dims.unit === u ? "selected" : ""}>${u}</option>`).join("")}
          </select></label>
          <label class="field">净重<input data-spec="weight.net_weight_g" inputmode="decimal" value="${esc(weight.net_weight_g ?? "")}"></label>
          <label class="field">毛重<input data-spec="weight.gross_weight_g" inputmode="decimal" value="${esc(weight.gross_weight_g ?? "")}"></label>
          <label class="field">重量单位<select data-spec="weight.unit">
            ${["g"].map((u) => `<option value="${u}" ${weight.unit === u ? "selected" : ""}>${u}</option>`).join("")}
          </select></label>
        </div>
        ${['item','package'].map(layer=>`<details class="accordion"><summary>${layer==='item'?'单件本体':'运输包装'}（cm / g）</summary><div class="fields">${['length_cm','width_cm','height_cm'].map((key,i)=>`<label class="field">${['长','宽','高'][i]} cm<input data-spec="${layer}.dimensions.${key}" inputmode="decimal" value="${esc(sku.specs[layer].dimensions[key]??'')}"></label>`).join('')}${['net_weight_g','gross_weight_g'].map((key,i)=>`<label class="field">${['净重','毛重'][i]} g<input data-spec="${layer}.weight.${key}" inputmode="decimal" value="${esc(sku.specs[layer].weight[key]??'')}"></label>`).join('')}</div></details>`).join('')}
      </details>

      <details class="accordion" style="margin-top:10px">
        <summary>套装组成 ${helpButton("composition")}</summary>
        <div style="margin-top:10px">
          ${compRows || "<p class='meta'>暂无组成明细；同款多件或混合套装须逐条登记。</p>"}
        </div>
        <button class="btn" id="add-composition" style="margin-top:10px" data-testid="add-composition">添加组成项</button>
      </details>

      <details class="accordion" style="margin-top:10px">
        <summary>销售属性组合 ${helpButton("bindings")}</summary>
        <div style="margin-top:10px">
          ${bindingRows(sku.sale_spec_bindings || [])}
        </div>
        <button class="btn" id="add-binding" style="margin-top:10px" data-testid="add-binding">添加属性</button>
      </details>

      <div class="callout">平台 SKC/SKU ID 由平台返回，未提交前保持空值；不在此填写示例 ID。</div>
      <button class="btn primary" data-save-sku="${index}" data-testid="save-sku">保存 SKU</button>
    </div>`;
}

// ---------- view: feedback ----------
function renderFeedback() {
  if (!state.detail) return `<div class="panel"><p>加载中…</p></div>`;
  const d = state.detail;
  const rows = d.feedbacks.map((f) => `
    <div class="evidence-item">
      <div style="display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap">
        <h4>${esc(STAGE_LABELS[f.platform_stage] || f.platform_stage)}</h4>
        <span class="tag ${f.verification === "human_confirmed" ? "good" : "warn"}">${f.verification==='human_confirmed'?'已核对':f.verification==='draft'?'待核对':'待复核'}</span>
      </div>
      <p>${esc(f.feedback_text)}</p>
      <p>日期：${esc(f.feedback_date || "未填")} · 证据索引：${esc(f.evidence_ref || "无")} · SKU：${esc(f.sku_ref || "全部")}</p>
      ${f.buyer_supply_income ? `<p>平台建议供货价：${fmtNum(f.buyer_supply_income.amount)} ${esc(f.buyer_supply_income.currency || "")}</p>` : ""}
    </div>`).join("");

  return `
    <div class="view-head">
      <div><h2>反馈跟进</h2><p>记录核价与任务，及时重算收益。</p></div>
      <select id="candidate-picker">${state.candidates.map((x) => `<option value="${esc(x.id)}" ${x.id === d.candidate.id ? "selected" : ""}>${esc(x.title)}</option>`).join("")}</select>
    </div>
    ${WorkbenchUI.finance(d)}
    <section class="panel">
      <div class="panel-title"><h3>反馈记录</h3><span class="hint">按任务记录，保留核价历史</span></div>
      <div>${rows || "<p class='meta'>暂无反馈记录。</p>"}</div>
    </section>
    <section class="panel">
      <div class="panel-title"><h3>登记一次反馈</h3><span class="hint">缺少日期、原话或证据索引时只能存为草稿</span></div>
      <div class="fields">
        <label class="field">平台阶段
          <select id="fb-stage">${Object.entries(STAGE_LABELS).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select>
        </label>
        <label class="field">反馈日期<input id="fb-date" type="date"></label>
        <label class="field">关联商家 SKU<select id="fb-sku">${d.skus.map(v=>`<option value="${esc(v.sku.merchant_sku)}">${esc(v.sku.merchant_sku)} · ${esc(v.sku.supply_income.currency)}/${esc(v.sku.sales_unit)}</option>`).join('')}</select></label>
        <label class="field">平台建议供货价<input id="fb-price" inputmode="decimal" placeholder="仅填入对应 SKU"></label>
        <label class="field wide">反馈原话与要求<textarea id="fb-text" rows="3" placeholder="原样记录平台/买手要求；与内部解释分开"></textarea></label>
        <label class="field wide">平台任务编号 / 截图索引<input id="fb-ref" placeholder="证据索引，已证实记录必填"></label>
        <label class="field"><input type="checkbox" id="fb-confirmed"> 人工已核实（需填日期、原话与证据索引，否则自动降为草稿）</label>
      </div>
      <div class="panel-title" style="margin-top:12px"><span></span><button class="btn primary" id="save-feedback" data-testid="save-feedback">保存反馈</button></div>
    </section>`;
}

// ---------- drawers ----------
function openDrawer(kind) {
  state.panel = kind;
  const drawer = document.getElementById("side-drawer");
  const backdrop = document.getElementById("drawer-backdrop");
  if (kind === "sources") drawer.innerHTML = sourcesDrawer();
  else drawer.innerHTML = settingsDrawer();
  drawer.hidden = false;
  backdrop.hidden = false;
  bindDrawerEvents();
}
function closeDrawer() {
  document.getElementById("side-drawer").hidden = true;
  document.getElementById("drawer-backdrop").hidden = true;
  state.panel = null;
}

function sourcesDrawer() {
  const groups = {};
  for (const s of state.meta.sources) {
    (groups[s.level] ||= []).push(s);
  }
  const body = Object.entries(groups).map(([level, list]) => `
    <h3>${esc(level)}</h3>
    ${list.map((s) => `
      <div class="evidence-item">
        <h4>${esc(s.title || s.id)}</h4>
        <p>发布方：${esc(s.publisher || "—")} · 核验：${esc(s.verification)}</p>
        <p>${esc(s.locator || "")}</p>
        ${s.url ? `<a href="${esc(WorkbenchURL(s.url))}" target="_blank" rel="noopener noreferrer">打开来源</a>` : "<p>无外部链接（内部方法/待确认）。</p>"}
        ${s.limit ? `<p class="callout">边界：${esc(s.limit)}</p>` : ""}
      </div>`).join("")}
  `).join("");
  return `<h3>来源依据与级别</h3><p class="callout">官方政策、第三方 SDK、厂商 ERP 文档、行业参考、市场观察与公司政策分开标注；第三方实现不等于官方已确认。</p>${body}`;
}

function settingsDrawer() {
  const policy = state.detail?.policy || {};
  const adapters = Object.entries(state.meta.adapter_statuses || {}).map(([key, a]) => `
    <div class="ready-row"><span>${esc(key)}</span><span class="tag ${a.status === "succeeded" ? "good" : "warn"}">${esc(a.status)}</span></div>
  `).join("");
  return `
    <h3>经营政策 ${helpButton("policy")}</h3>
    <div class="fields">
      <label class="field">口径
        <select id="pol-metric">
          <option value="" ${!policy.metric ? "selected" : ""}>未设置</option>
          <option value="contribution_margin" ${policy.metric === "contribution_margin" ? "selected" : ""}>收入贡献率</option>
          <option value="cost_markup" ${policy.metric === "cost_markup" ? "selected" : ""}>成本加价率</option>
        </select>
      </label>
      <label class="field">门槛 %<input id="pol-threshold" value="${esc(policy.threshold_percent || "")}" placeholder="40 / 50 / 60 / 70 仅为示例"></label>
      <label class="field">已确认<input type="checkbox" id="pol-confirmed" ${policy.confirmed ? "checked" : ""}></label>
      <label class="field">确认人<input id="pol-by" value="${esc(policy.confirmed_by || "")}"></label>
      <label class="field">确认日期<input id="pol-at" type="date" value="${esc(policy.confirmed_at || "")}"></label>
      <label class="field">政策来源<input id="pol-source" value="${esc(policy.source_ref || "")}"></label>
    </div>
    <button class="btn primary" id="save-policy" style="margin-top:12px">保存政策</button>

    <h3 style="margin-top:22px">集成与端口状态</h3>
    <div>${adapters}</div>

    <h3 style="margin-top:22px">导入 / 导出</h3>
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <button class="btn" id="export-json">导出内部 JSON</button>
      <button class="btn" id="export-csv">导出内部 CSV</button>
      <button class="btn" id="import-json">导入 JSON</button>
      <button class="btn" id="import-csv">导入 CSV</button>
    </div>
    <textarea id="import-content" rows="4" placeholder="粘贴内部 JSON/CSV 内容；文件编码 UTF-8"></textarea>
    <p class="meta">CSV 保存商品与 SKU；JSON 包含来源、政策和反馈；完整历史请备份数据库。</p>

    <h3 style="margin-top:22px">备份与恢复</h3>
    <div style="display:flex;gap:8px">
      <button class="btn" id="backup">备份数据库</button>
      <button class="btn" id="restore">从备份恢复</button>
    </div>
    <div id="backup-list" style="margin-top:10px"></div>

    <h3 style="margin-top:22px">公开页面读取（小样本）</h3>
    <div class="fields">
      <label class="field wide">页面 URL<input id="collect-url" type="url" placeholder="仅限公开只读页面"></label>
    </div>
    <button class="btn" id="collect-page" style="margin-top:10px">读取并保存快照</button>
    <p class="callout">网页取不到时保留失败证据与手动入口；不靠模型生成页面内容。</p>`;
}

// ---------- events ----------
function bindViewEvents() {
  document.querySelectorAll('[data-profit-scene]').forEach(b=>b.addEventListener('click',()=>{ProfitUI.setScene(b.dataset.profitScene);render();}));
  document.querySelectorAll('[data-restore-candidate]').forEach(b=>b.addEventListener('click',async()=>{
    await api(`/api/candidates/${state.selectedId}/restore`,{method:'POST',body:{reviewer:'local-user'}});
    await refreshCandidates(); await loadDetail(state.selectedId); render();
  }));
  document.querySelectorAll('[data-quick-decision]').forEach(b=>b.addEventListener('click',async()=>{
    await api(`/api/candidates/${state.selectedId}/decision`,{method:'POST',body:{decision:b.dataset.quickDecision,
      reason:b.dataset.quickDecision==='paused'?'根据当前核价与成本评估，暂缓并待重新议价':'转内部评审；平台字段与材料仍按待办核对',reviewer:'local-user'}});
    await refreshCandidates(); await loadDetail(state.selectedId); render(); toast('内部决定已记录');
  }));
  document.querySelectorAll("[data-open]").forEach((b) => b.addEventListener("click", () => openCandidate(b.dataset.open)));
  document.querySelectorAll("[data-new-candidate]").forEach((b) => b.addEventListener("click", newCandidate));
  const picker = document.getElementById("candidate-picker");
  if (picker) picker.addEventListener("change", async () => { await loadDetail(picker.value); render(); });

  if (state.view === "research") bindResearchEvents();
  if (state.view === "submission") bindSubmissionEvents();
  if (state.view === "feedback") bindFeedbackEvents();
  bindHelpButtons();
}

function bindResearchEvents() {
  document.querySelector('[data-back-candidate-list]')?.addEventListener('click',()=>revealEntry(document.getElementById('candidate-list')));
  document.querySelector('[data-research-product]')?.addEventListener('click',()=>{
    switchView('submission');
    window.scrollTo({top:0,behavior:'instant'});
  });
  document.querySelectorAll('[data-edit-evidence]').forEach(b=>b.addEventListener('click',()=>{
    const s=state.detail.evidence.find(e=>e.source.id===b.dataset.editEvidence).source;
    state.editingSourceId=s.id;
    const values={'ev-url':s.url,'ev-text':s.facts?.note||s.locator,'ev-level':s.level,
      'ev-price':s.facts?.display_price??s.facts?.extracted_candidates?.display_price?.value,'ev-currency':s.facts?.currency||s.facts?.extracted_candidates?.display_price?.currency||'EUR', 'ev-pieces':s.scope?.pieces,
      'ev-dimensions':(s.scope?.product_dimensions_cm||[]).join(', '),'ev-material':s.scope?.material,
      'ev-country':s.scope?.country||'DE','ev-date':s.observed_at};
    Object.entries(values).forEach(([id,value])=>document.getElementById(id).value=value??'');
    document.getElementById('ev-confirmed').checked=s.verification==='public_body_reviewed';
    document.getElementById('add-evidence').textContent='保存观察数据';
    document.getElementById('ev-url').focus();
  }));
  const add = document.getElementById("add-evidence");
  if (add) add.addEventListener("click", addEvidence);
  const save = document.getElementById("save-decision");
  if (save) save.addEventListener("click", saveDecision);
  const restore = document.getElementById("restore-decision");
  if (restore) restore.addEventListener("click", restoreDecision);
  bindHelpButtons();
}

async function addEvidence() {
  const url = document.getElementById("ev-url").value.trim();
  const text = document.getElementById("ev-text").value.trim();
  const level = document.getElementById("ev-level").value;
  if (!/^https?:\/\//i.test(url) || !text) { toast("请填写 http(s) 来源链接和看到的事实。"); return; }
  const original=state.detail.evidence.find(e=>e.source.id===state.editingSourceId)?.source||{};
  const source = {
    ...original,
    record_type: "source", level, url,
    locator: text.slice(0, 200),
    scope: {...original.scope, country:document.getElementById('ev-country').value.trim(),
      material:document.getElementById('ev-material').value.trim()||null,
      pieces:document.getElementById('ev-pieces').value?Number(document.getElementById('ev-pieces').value):null,
      product_dimensions_cm:document.getElementById('ev-dimensions').value.split(/[,，]/).map(x=>x.trim()).filter(Boolean)},
    observed_at:document.getElementById('ev-date').value||null,
    verification:document.getElementById('ev-confirmed').checked?'public_body_reviewed':'manual_entry_pending_review',
    facts: {...original.facts, note: text, display_price:document.getElementById('ev-price').value||null,
      currency:document.getElementById('ev-currency').value.trim()||null},
  };
  const res = await api("/api/sources", { method: "POST", body: source });
  if (res.errors?.length) { toast(res.errors.join("；")); return; }
  const detail = await api(`/api/candidates/${state.selectedId}`);
  detail.candidate.evidence_refs = detail.candidate.evidence_refs || [];
  if(!detail.candidate.evidence_refs.includes(res.id)) detail.candidate.evidence_refs.push(res.id);
  await api("/api/candidates", { method: "POST", body: detail.candidate });
  await loadDetail(state.selectedId);
  state.meta=await api('/api/meta'); state.editingSourceId=null;
  renderResearchDetail();
  bindResearchEvents();
  toast("证据已录入，待人工核对。");
}

async function saveDecision() {
  const decision = document.getElementById("decision-select").value;
  const reason = document.getElementById("decision-reason").value.trim();
  const res = await api(`/api/candidates/${state.selectedId}/decision`, {
    method: "POST", body: { decision, reason, reviewer: "local-user" },
  });
  if (res.errors?.length) { toast(res.errors.join("；")); return; }
  await refreshCandidates(); await loadDetail(state.selectedId);
  renderResearchDetail(); bindResearchEvents();
  toast("决定已保存。");
}

async function restoreDecision() {
  const res = await api(`/api/candidates/${state.selectedId}/restore`, { method: "POST", body: { reviewer: "local-user" } });
  if (res.errors?.length) { toast(res.errors.join("；")); return; }
  await refreshCandidates(); await loadDetail(state.selectedId);
  renderResearchDetail(); bindResearchEvents();
  toast("已撤销暂缓/排除，恢复继续评估。");
}

function revealEntry(element) {
  if (!element) return;
  if (element.tagName === 'DETAILS') element.open = true;
  element.style.scrollMarginTop = `${(document.querySelector('.topbar')?.offsetHeight || 0) + 14}px`;
  element.scrollIntoView({block:'start', behavior:'instant'});
}

function openProductEntry() {
  revealEntry(document.getElementById('product-details'));
  const title = document.getElementById('f-title');
  title?.focus({preventScroll:true});
  if (title?.value === '新候选商品') title.select();
}

function openSkuEntry(index) {
  const details = document.getElementById('sku-details');
  if (details) details.open = true;
  const sku = state.draft.skus[index];
  if (!sku) return;
  ensureSpecs(sku);
  const editor = document.getElementById('sku-editor');
  editor.innerHTML = skuEditor(sku, index);
  bindSkuEditor(index);
  revealEntry(editor);
}

function bindSubmissionEvents() {
  document.querySelector('[data-open-product]')?.addEventListener('click', openProductEntry);
  document.querySelector('[data-open-first-sku]')?.addEventListener('click', () => openSkuEntry(0));
  state.draft.material_requirements ||= {required:[],confirmed:false,source_ref:null};
  document.querySelectorAll('[data-material-required]').forEach(el=>el.addEventListener('change',()=>{
    const r=state.draft.material_requirements;
    r.required=[...document.querySelectorAll('[data-material-required]:checked')].map(x=>x.dataset.materialRequired);
    r.confirmed=false; document.getElementById('materials-confirmed').checked=false;
  }));
  const materialsRef=document.getElementById('materials-ref');
  if(materialsRef) materialsRef.addEventListener('input',()=>{state.draft.material_requirements.source_ref=materialsRef.value; state.draft.material_requirements.confirmed=false; document.getElementById('materials-confirmed').checked=false;});
  const materialsConfirmed=document.getElementById('materials-confirmed');
  if(materialsConfirmed) materialsConfirmed.addEventListener('change',()=>{state.draft.material_requirements.confirmed=materialsConfirmed.checked;});
  const saveMaterials=document.getElementById('save-materials');
  if(saveMaterials) saveMaterials.addEventListener('click',async()=>{if(await persistDraft())return;await loadDetail(state.selectedId);render();toast('材料要求已保存');});
  const saveProduct=document.getElementById('save-product');
  if(saveProduct) saveProduct.addEventListener('click',async()=>{
    const nextSku = saveProduct.hasAttribute('data-next-sku');
    if(await persistDraft()) return;
    await refreshCandidates(); await loadDetail(state.selectedId); render(); toast('商品资料已保存');
    if (nextSku) openSkuEntry(0);
  });
  document.querySelectorAll("[data-edit-sku]").forEach((b) => b.addEventListener("click", () => {
    const i = Number(b.dataset.editSku);
    openSkuEntry(i);
  }));
  document.querySelectorAll("[data-remove-sku]").forEach((b) => b.addEventListener("click", () => removeSku(Number(b.dataset.removeSku))));
  const addSkuBtn = document.getElementById("add-sku");
  if (addSkuBtn) addSkuBtn.addEventListener("click", addSku);
  document.querySelectorAll("[data-material]").forEach((cb) => cb.addEventListener("change", () => {
    state.draft.materials = state.draft.materials || {};
    state.draft.materials[cb.dataset.material] = cb.checked;
  }));
  const gen = document.getElementById("generate-submission");
  if (gen) gen.addEventListener("click", generateSubmission);
  const title = document.getElementById("f-title");
  if (title) title.addEventListener("change", () => { state.draft.title = title.value; });
  const material=document.getElementById('f-material');
  if(material) material.addEventListener('change',()=>{state.draft.material=material.value;});
  for(const [id,key] of [['f-listing-title','listing_title'],['f-market-title','market_title']]) {
    const input=document.getElementById(id); if(input) input.addEventListener('change',()=>{state.draft[key]=input.value;});
  }
  const rationale = document.getElementById("f-rationale");
  if (rationale) rationale.addEventListener("change", () => { state.draft.rationale = rationale.value; });
  const advantage = document.getElementById("f-advantage");
  if (advantage) advantage.addEventListener("change", () => { state.draft.advantage = advantage.value; });
  const supplierUrl = document.getElementById("f-supplier-url");
  if (supplierUrl) supplierUrl.addEventListener("change", () => {
    state.draft.supplier = { ...(state.draft.supplier || {}), url: supplierUrl.value,confirmed:false };
    document.getElementById('f-supplier-confirmed').checked=false;
  });
  const moq = document.getElementById("f-moq");
  if (moq) moq.addEventListener("change", () => {
    state.draft.supplier = { ...(state.draft.supplier || {}), moq: moq.value,confirmed:false };
    document.getElementById('f-supplier-confirmed').checked=false;
  });
  const lead = document.getElementById("f-lead");
  if (lead) lead.addEventListener("change", () => {
    state.draft.supplier = { ...(state.draft.supplier || {}), lead_days: lead.value,confirmed:false };
    document.getElementById('f-supplier-confirmed').checked=false;
  });
  document.getElementById('f-supplier-ref')?.addEventListener('input',e=>{state.draft.supplier ||= {}; state.draft.supplier.source_ref=e.target.value; state.draft.supplier.confirmed=false; document.getElementById('f-supplier-confirmed').checked=false;});
  document.getElementById('f-supplier-confirmed')?.addEventListener('change',e=>{state.draft.supplier ||= {}; state.draft.supplier.confirmed=e.target.checked;});
}

function bindSkuEditor(index) {
  const root = document.getElementById("sku-editor");
  const sku = ensureSpecs(state.draft.skus[index]);
  root.querySelectorAll('[data-profit-input]').forEach(el=>el.addEventListener('input',()=>{
    sku.profit_plan.inputs ||= {}; sku.profit_plan.inputs[el.dataset.profitInput]=el.value;
  }));
  root.querySelector('[data-enable-profit]')?.addEventListener('click',()=>{
    sku.profit_plan={version:'full-cost/2.0',inputs:{},value_basis:'budget_assumptions'};
    const old=sku.costs.find(c=>c.key==='expected_after_sales');
    if(old&&old.money.amount==null) Object.assign(old.money,{amount:'0.00',confirmed:true,source_ref:'PROFIT-ASSUMPTIONS:aggregate-replaced'});
    root.innerHTML=skuEditor(sku,index);bindSkuEditor(index);
  });
  root.querySelectorAll("[data-sku-field]").forEach((el) => el.addEventListener("input", () => {
    state.draft.skus[index][el.dataset.skuField] = el.value;
  }));
  root.querySelectorAll("[data-income]").forEach((el) => el.addEventListener("input", () => {
    const field = el.dataset.income;
    const income = state.draft.skus[index].supply_income;
    income[field] = field === "confirmed" ? el.checked : el.value;
    if (field !== 'confirmed') {income.confirmed = false; root.querySelector('[data-income=confirmed]').checked=false;}
  }));
  root.querySelectorAll("[data-cost]").forEach((el) => el.addEventListener("input", () => {
    const key = el.dataset.cost;
    const item = state.draft.skus[index].costs.find((x) => x.key === key);
    if (item) { item.money.amount = el.value; item.money.confirmed = false; updateCostReview(root,key,item.money); }
  }));
  root.querySelectorAll('[data-cost-field]').forEach(el=>el.addEventListener('input',()=>{
    const money=sku.costs.find(c=>c.key===el.dataset.costKey).money;
    const field=el.dataset.costField;
    money[field]=field==='confirmed'?el.checked:el.value;
    if(field!=='confirmed') money.confirmed=false;
    updateCostReview(root,el.dataset.costKey,money);
  }));
  root.querySelectorAll("[data-spec]").forEach((el) => el.addEventListener("input", () => {
    const parts=el.dataset.spec.split('.'), field=parts.pop();
    const target=parts.reduce((obj,key)=>obj[key],sku.specs);
    target[field]=el.value===''?null:el.value;
  }));
  bindComposition(root, index);
  bindBindings(root, index);
  root.querySelectorAll("[data-save-sku]").forEach((b) => b.addEventListener("click", async () => {
    const pieces = Number(state.draft.skus[index].pieces);
    state.draft.skus[index].pieces = Number.isInteger(pieces) && pieces >= 1 ? pieces : 1;
    normalizeComposition(state.draft.skus[index]);
    const errors = await persistDraft();
    if (!errors) { await refreshCandidates(); await loadDetail(state.selectedId); render(); toast("SKU 已保存。"); }
  }));
  const close = root.querySelector("[data-close-editor]");
  if (close) close.addEventListener("click", () => { root.innerHTML = ""; });
}

function updateCostReview(root,key,money) {
  root.querySelector(`[data-cost-key="${key}"][data-cost-field=confirmed]`).checked=money.confirmed;
  const tag=root.querySelector(`[data-cost-status="${key}"]`);
  tag.className=`tag ${money.confirmed?'good':'warn'}`; tag.textContent=money.confirmed?'已确认':'待确认';
}

function bindComposition(root, index) {
  const sku = state.draft.skus[index];
  root.querySelectorAll("[data-comp-name]").forEach((el) => el.addEventListener("input", () => {
    sku.pack_composition[Number(el.dataset.compName)].name = el.value;
  }));
  root.querySelectorAll("[data-comp-count]").forEach((el) => el.addEventListener("input", () => {
    const n = Number(el.value);
    sku.pack_composition[Number(el.dataset.compCount)].count = Number.isInteger(n) && n >= 1 ? n : 1;
  }));
  root.querySelectorAll("[data-comp-dims]").forEach((el) => el.addEventListener("input", () => {
    const dims = el.value.split(/[,，]/).map((s) => s.trim()).filter(Boolean);
    sku.pack_composition[Number(el.dataset.compDims)].product_dimensions_cm = dims;
  }));
  root.querySelectorAll("[data-comp-remove]").forEach((b) => b.addEventListener("click", () => {
    sku.pack_composition.splice(Number(b.dataset.compRemove), 1);
    document.getElementById("sku-editor").innerHTML = skuEditor(sku, index);
    bindSkuEditor(index);
  }));
  const add = root.querySelector("#add-composition");
  if (add) add.addEventListener("click", () => {
    sku.pack_composition.push({ name: "", count: 1, product_dimensions_cm: [], classification: null });
    document.getElementById("sku-editor").innerHTML = skuEditor(sku, index);
    bindSkuEditor(index);
  });
}

function bindBindings(root, index) {
  const sku = state.draft.skus[index];
  root.querySelectorAll("[data-binding-name]").forEach((el) => el.addEventListener("input", () => {
    sku.sale_spec_bindings[Number(el.dataset.bindingName)].name = el.value;
  }));
  root.querySelectorAll("[data-binding-value]").forEach((el) => el.addEventListener("input", () => {
    sku.sale_spec_bindings[Number(el.dataset.bindingValue)].value = el.value || null;
  }));
  root.querySelectorAll("[data-binding-remove]").forEach((b) => b.addEventListener("click", () => {
    sku.sale_spec_bindings.splice(Number(b.dataset.bindingRemove), 1);
    document.getElementById("sku-editor").innerHTML = skuEditor(sku, index);
    bindSkuEditor(index);
  }));
  const add = root.querySelector("#add-binding");
  if (add) add.addEventListener("click", () => {
    sku.sale_spec_bindings.push({ name: "", value: null, parent_spec_id: null, spec_id: null, source_ref: null });
    document.getElementById("sku-editor").innerHTML = skuEditor(sku, index);
    bindSkuEditor(index);
  });
}

function normalizeBindings(sku) {
  sku.sale_spec_bindings = (sku.sale_spec_bindings || [])
    .filter((b) => b.name && b.name.trim())
    .map((b) => ({
      name: b.name.trim(),
      value: b.value || null,
      parent_spec_id: b.parent_spec_id ?? null,
      spec_id: b.spec_id ?? null,
      source_ref: b.source_ref || null,
    }));
}

function normalizeComposition(sku) {
  sku.pack_composition = (sku.pack_composition || [])
    .filter((item) => item.name && item.name.trim())
    .map((item) => ({
      name: item.name.trim(),
      count: Number.isInteger(item.count) && item.count >= 1 ? item.count : 1,
      product_dimensions_cm: item.product_dimensions_cm || [],
      classification: item.classification ?? null,
    }));
}

async function addSku() {
  const group = state.draft.skus?.[0]?.merchant_group_code || state.draft.id;
  const seq = (state.draft.skus || []).length + 1;
  const sku = blankSku(`${state.draft.id}-SKU${seq}`, group);
  state.draft.skus.push(sku);
  const errors = await persistDraft();
  if (errors) return;
  await loadDetail(state.selectedId);
  render();
  const i = state.detail.skus.length - 1;
  document.getElementById("sku-editor").innerHTML = skuEditor(state.draft.skus[i], i);
  bindSkuEditor(i);
}

async function removeSku(index) {
  if (state.draft.skus.length <= 1) { toast("至少保留一个 SKU。"); return; }
  state.draft.skus.splice(index, 1);
  const errors = await persistDraft();
  if (errors) return;
  await loadDetail(state.selectedId);
  render();
  toast("SKU 已删除（本地记录）。");
}

async function persistDraft() {
  (state.draft.skus || []).forEach((sku) => {
    const count=Number(sku.pieces);
    if(Number.isInteger(count)) sku.pieces=count;
    ensureSpecs(sku);
    normalizeComposition(sku);
    normalizeBindings(sku);
  });
  const res = await api("/api/candidates", { method: "POST", body: state.draft });
  if (res.errors?.length) { toast(res.errors.join("；")); return res.errors; }
  return null;
}

async function generateSubmission() {
  if (await persistDraft()) return;
  const res = await api(`/api/candidates/${state.selectedId}/submission`, { method: "POST", body: {} });
  if (res.status !== "succeeded") { toast((res.errors || ["生成失败"]).join("；")); return; }
  const pkg = res.package;
  const output=document.getElementById('submission-output');
  output.hidden=false;
  output.innerHTML=WorkbenchUI.reviewSheet(pkg)+`<div class="workflow-actions"><button class="btn" id="download-review">下载评审单</button><button class="btn" id="download-package">下载 JSON</button></div><details class="accordion"><summary>结构化资料与字段计划</summary><textarea id="submission-text" rows="12" readonly>${esc(JSON.stringify(pkg,null,2))}</textarea></details>`;
  const download=(content,type,ext)=>{
    const link=document.createElement('a'), url=URL.createObjectURL(new Blob([content],{type}));
    link.href=url; link.download=`${pkg.candidate_id}-review.${ext}`; link.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
  };
  document.getElementById('download-package').onclick=()=>download(JSON.stringify(pkg,null,2),'application/json','json');
  document.getElementById('download-review').onclick=async()=>{
    const [css,popover]=await Promise.all(['/static/styles.css','/static/profit-popover.js'].map(path=>fetch(path).then(r=>r.text())));
    download(`<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${esc(pkg.candidate_id)} 供货评审单</title><style>${css}</style><body><main id="view-root"><section class="panel">${WorkbenchUI.reviewSheet(pkg)}</section></main><script>${popover.replace(/<\/script/gi,'<\\/script')}</script></body></html>`,'text/html;charset=utf-8','html');
  };
  output.scrollIntoView({behavior:'smooth',block:'start'});
  toast('评审单已生成，可下载给内部同事核对。');
}

function bindFeedbackEvents() {
  const save = document.getElementById("save-feedback");
  if (save) save.addEventListener("click", saveFeedback);
}

async function saveFeedback() {
  const payload = {
    candidate_id: state.selectedId,
    platform_stage: document.getElementById("fb-stage").value,
    feedback_date: document.getElementById("fb-date").value || null,
    feedback_text: document.getElementById("fb-text").value.trim(),
    evidence_ref: document.getElementById("fb-ref").value.trim() || null,
    sku_ref: document.getElementById("fb-sku").value.trim() || null,
    verification: document.getElementById("fb-confirmed").checked ? "human_confirmed" : "draft",
  };
  if(payload.evidence_ref?.startsWith('casebook:')) payload.data_origin='scenario_assumption';
  const price = document.getElementById("fb-price").value.trim();
  if (price) {
    const sku=state.detail.skus.find(v=>v.sku.merchant_sku===payload.sku_ref)?.sku;
    payload.buyer_supply_income = { amount: price, currency: sku.supply_income.currency, sales_unit: sku.sales_unit,
      confirmed:payload.verification==='human_confirmed', source_ref:payload.evidence_ref };
  }
  if (!payload.feedback_text) { toast("请填写反馈原话。"); return; }
  const res = await api(`/api/candidates/${state.selectedId}/feedback`, { method: "POST", body: payload });
  if (res.status !== "succeeded") { toast((res.errors || ["保存失败"]).join("；")); return; }
  await refreshCandidates(); await loadDetail(state.selectedId); render();
  toast("反馈已保存为本地记录，平台状态未改变。");
}

async function newCandidate() {
  const id = `ORG-${Date.now().toString(36).toUpperCase()}`;
  const record = {
    record_type: "candidate", id, mode_assumption: "fully_managed", mode_confirmed: false,
    research_market: "DE", platform_product_id: null, category_path_ids: [],
    template_binding: { status: "unverified", category_id: null, source_ref: null },
    evidence_refs: [], internal_decision: "research", decision_history: [], synthetic: false,
    title: "新候选商品",
    skus: [blankSku(`${id}-SKU1`, id)],
  };
  const res = await api("/api/candidates", { method: "POST", body: record });
  if (res.errors?.length) { toast(res.errors.join("；")); return; }
  await refreshCandidates(); state.view = "submission"; await loadDetail(id); render();
  openProductEntry();
}

// ---------- drawer events ----------
function bindDrawerEvents() {
  document.querySelectorAll('#pol-metric,#pol-threshold,#pol-by,#pol-at,#pol-source').forEach(el=>el.addEventListener('input',()=>{
    document.getElementById('pol-confirmed').checked=false;
  }));
  const savePol = document.getElementById("save-policy");
  if (savePol) savePol.addEventListener("click", savePolicy);
  document.getElementById("export-json")?.addEventListener("click", () => exportBundle("json"));
  document.getElementById("export-csv")?.addEventListener("click", () => exportBundle("csv"));
  document.getElementById("import-json")?.addEventListener("click", () => importBundle("json"));
  document.getElementById("import-csv")?.addEventListener("click", () => importBundle("csv"));
  document.getElementById("backup")?.addEventListener("click", doBackup);
  document.getElementById("restore")?.addEventListener("click", doRestore);
  document.getElementById("collect-page")?.addEventListener("click", collectPage);
  bindHelpButtons();
  refreshBackupList();
}

async function savePolicy() {
  const payload = {
    record_type: "policy",
    metric: document.getElementById("pol-metric").value || null,
    threshold_percent: document.getElementById("pol-threshold").value || null,
    confirmed: document.getElementById("pol-confirmed").checked,
    confirmed_by: document.getElementById("pol-by").value || null,
    confirmed_at: document.getElementById("pol-at").value || null,
    source_ref: document.getElementById("pol-source").value || null,
    version: "local-v1",
  };
  const res = await api("/api/policy", { method: "PUT", body: payload });
  if (res.errors?.length) { toast(res.errors.join("；")); return; }
  await loadDetail(state.selectedId);
  toast("政策已保存；未确认口径仅作情景展示。");
  await refreshCandidates(); render();
}

async function exportBundle(format) {
  const data = await api(`/api/export?format=${format}`);
  const blob = new Blob([format === "json" ? JSON.stringify(data.content, null, 2) : data.content],
    { type: format === "json" ? "application/json" : "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `workbench-internal-${format}-${Date.now()}.${format}`;
  a.click();
  URL.revokeObjectURL(a.href);
}

async function importBundle(format) {
  const content = document.getElementById("import-content").value;
  if (!content) { toast("请先粘贴要导入的内容。"); return; }
  const res = await api("/api/import", { method: "POST", body: { format, content } });
  const r = res.report;
  toast(`导入 ${r.imported.length} 条，重复 ${r.duplicates.length} 条，错误 ${r.errors.length} 条。`);
  if (r.errors.length) console.warn("import errors", r.errors);
  await refreshCandidates();
}

async function doBackup() {
  const res = await api("/api/backup", { method: "POST", body: {} });
  toast(`已备份：${res.backup}`);
  refreshBackupList();
}

async function doRestore() {
  const list = await api("/api/backups");
  if (!list.backups.length) { toast("暂无备份可恢复。"); return; }
  const latest = list.backups[0].filename;
  const res = await api("/api/restore", { method: "POST", body: { filename: latest } });
  if (res.errors?.length) { toast(res.errors.join("；")); return; }
  await refreshCandidates(); await loadDetail(state.selectedId).catch(() => {});
  toast(`已从 ${latest} 恢复。`);
}

async function refreshBackupList() {
  const el = document.getElementById("backup-list");
  if (!el) return;
  const list = await api("/api/backups");
  el.innerHTML = list.backups.map((b) => `<div class="ready-row"><span>${esc(b.filename)}</span><span>${Math.round(b.bytes / 1024)} KB</span></div>`).join("") || "<p class='meta'>暂无备份。</p>";
}

async function collectPage() {
  const url = document.getElementById("collect-url").value.trim();
  if (!/^https?:\/\//i.test(url)) { toast("请输入 http(s) 页面地址。"); return; }
  const res = await api("/api/collect", { method: "POST", body: { url, task_id: `manual-${Date.now()}`,candidate_id:state.selectedId } });
  if (res.status === "succeeded") toast("快照已保存，字段待人工核对。");
  else toast(`读取失败：${res.error_code || res.status}（已保留失败证据，可手动录入）。`);
  await refreshCandidates();
  state.meta=await api('/api/meta');
  if(state.selectedId) {await loadDetail(state.selectedId);render();}
}

// ---------- help popover ----------
function bindHelpButtons() {
  document.querySelectorAll(".help-btn").forEach((btn) => {
    if(btn.dataset.boundHelp) return;
    btn.dataset.boundHelp='true';
    btn.addEventListener("mouseenter", () => showPopover(btn));
    btn.addEventListener("focus", () => {if(btn.matches(':focus-visible')) showPopover(btn);});
    btn.addEventListener("click", (e) => { e.stopPropagation(); togglePopover(btn); });
  });
}

function togglePopover(btn) {
  const pop = document.getElementById("help-popover");
  const current = pop.dataset.for;
  const target = btn.dataset.source || btn.dataset.help;
  if (!pop.hidden && current === target) {
    closePopover();
  } else showPopover(btn);
}

function showPopover(btn) {
  const pop = document.getElementById("help-popover");
  let title, body, source = null;
  if (btn.dataset.source) {
    source = sourceById(btn.dataset.source);
    if (source) {
      title = source.title || source.id;
      body = source.locator || "";
    } else { title = "来源未找到"; body = "该来源未在注册表中。"; }
  } else {
    const tip = HELP_TIPS[btn.dataset.help];
    title = tip?.title || "说明";
    body = tip?.body || "";
  }
  pop.dataset.for = btn.dataset.source || btn.dataset.help;
  pop.innerHTML = `
    <button class="pop-close" aria-label="关闭" onclick="document.getElementById('help-popover').hidden=true">×</button>
    <h4>${esc(title)}</h4>
    <p>${esc(body)}</p>
    ${!source?`<div class="help-sources">${(HELP_SOURCES[btn.dataset.help]||[]).map(id=>{
      const s=sourceById(id); return s?.url?`<p><a href="${esc(WorkbenchURL(s.url))}" target="_blank" rel="noopener noreferrer">${esc(s.publisher||s.title||id)} · 原文依据</a><small>${esc(s.limit||'')}</small></p>`:'';
    }).join('')}<p><a href="/static/standards.html" target="_blank">查看本工具标准与核验边界</a></p></div>`:''}
    ${source ? `
      <dl>
        <dt>发布方</dt><dd>${esc(source.publisher || "—")}</dd>
        <dt>级别</dt><dd>${esc(source.level)}</dd>
        <dt>核验</dt><dd>${esc(source.verification)}</dd>
        <dt>日期</dt><dd>${esc(source.reviewed_at || source.observed_at || "—")}</dd>
      </dl>
      ${source.url ? `<a href="${esc(WorkbenchURL(source.url))}" target="_blank" rel="noopener noreferrer">打开来源原文</a>` : "<p>无外部官方来源链接。</p>"}
      ${source.limit ? `<p class='callout'>边界：${esc(source.limit)}</p>` : ""}
    ` : ""}`;
  pop.hidden = false;
  const rect = btn.getBoundingClientRect();
  pop.style.left = Math.max(8, Math.min(rect.left, window.innerWidth - pop.offsetWidth - 8)) + 'px';
  pop.style.top = Math.max(8, Math.min(rect.bottom + 8, window.innerHeight - pop.offsetHeight - 8)) + 'px';
}

function closePopover() {
  document.getElementById("help-popover").hidden = true;
}

init().catch((err) => {
  console.error(err);
  document.getElementById("view-root").innerHTML =
    `<section class="panel"><h3>启动失败</h3><p class="callout bad">${esc(err.message)}</p></section>`;
});
