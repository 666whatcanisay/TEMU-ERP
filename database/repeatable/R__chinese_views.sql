-- 面向 Navicat 的中文只读展示。原表、编码、金额精度保持原样。
-- TEMPTABLE 使视图不可更新。金额保留 NULL，显示到分，不代替完整利润引擎。
CREATE OR REPLACE ALGORITHM=TEMPTABLE SQL SECURITY INVOKER VIEW `明细_来源网址` AS
SELECT s.title AS `来源名称`,s.url AS `原始网址`,
 CASE s.source_level
 WHEN 'market_observation' THEN '市场商品观察'
 WHEN 'official_policy' THEN '官方政策' WHEN 'official_law' THEN '官方法规'
 WHEN 'official_guidance' THEN '官方指南' WHEN 'official_api_docs' THEN '官方接口文档'
 WHEN 'official_data_methodology' THEN '官方数据方法'
 WHEN 'official_software_docs' THEN '官方软件文档'
 WHEN 'official_locator_unread' THEN '官方入口_正文未读'
 WHEN 'industry_reference' THEN '行业参考' WHEN 'internal_method' THEN '内部方法与假设'
 WHEN 'third_party_sdk' THEN '第三方开发包' WHEN 'third_party_software' THEN '第三方软件'
 WHEN 'vendor_integration_doc' THEN '服务商对接文档'
 WHEN 'vendor_product_page' THEN '服务商产品页面'
 ELSE CONCAT('待识别：',COALESCE(s.source_level,'未填写')) END AS `来源类别`,
 CASE s.verification
 WHEN 'public_body_reviewed' THEN '已核对公开页面_不证明销量'
 WHEN 'public_body_read_no_live_sales_verification' THEN '已读公开页面_销量未验证'
 WHEN 'official_body_read' THEN '已阅读官方正文'
 WHEN 'official_index_checked_direct_access_limited' THEN '已查官方目录_正文访问受限'
 WHEN 'official_readme_read' THEN '已读官方项目说明'
 WHEN 'link_from_sdk_only' THEN '仅第三方包提供入口_正文待核对'
 WHEN 'body_read' THEN '已读正文' WHEN 'vendor_body_read' THEN '已读服务商正文'
 WHEN 'official_vendor_page_read' THEN '已读服务商官网'
 WHEN 'source_code_read' THEN '已阅读源码'
 WHEN 'release_metadata_download_and_hash_checked' THEN '已查版本及下载摘要_未验证业务功能'
 WHEN 'company_confirmation_pending' THEN '待公司确认'
 WHEN 'internal_assumptions_explicit' THEN '内部测算假设_非平台标准'
 WHEN 'internal_contract_tested' THEN '内部数据约定已测试'
 WHEN 'needs_review' THEN '待核对' WHEN 'pending' THEN '待核对'
 WHEN 'draft' THEN '草稿_未核实'
 ELSE CONCAT('待识别：',COALESCE(s.verification,'未填写')) END AS `核验说明`,
 s.locator AS `原文定位`,s.observed_on AS `观察日期`,s.retrieved_on AS `查阅日期`,
 CAST(ROUND(s.display_price,2) AS DECIMAL(30,2)) AS `页面价格`,
 CASE s.currency WHEN 'CNY' THEN '人民币' WHEN 'EUR' THEN '欧元'
 WHEN 'USD' THEN '美元' ELSE COALESCE(s.currency,'未填写') END AS `币种`,
 s.pieces AS `商品件数`,s.note AS `补充说明`,s.source_id AS `来源编号`
FROM sources s;

CREATE OR REPLACE ALGORITHM=TEMPTABLE SQL SECURITY INVOKER VIEW `面试01_选品证据` AS
SELECT p.title AS `商品名称`,
 CASE p.research_market WHEN 'DE' THEN '德国' ELSE COALESCE(p.research_market,'未填写') END AS `研究市场`,
 z.`来源名称`,z.`原始网址`,COALESCE(z.`来源类别`,'未关联来源') AS `来源类别`,
 COALESCE(z.`核验说明`,'待补齐来源') AS `核验说明`,z.`原文定位`,z.`观察日期`,
 CASE WHEN e.source_ref IS NULL THEN '尚无证据'
 WHEN e.source_id IS NULL THEN '引用未解析' ELSE '已关联来源' END AS `关联情况`,
 CASE WHEN x.source_ref IS NULL THEN '未登记网页快照'
 WHEN x.file_exists=0 THEN '核验时文件缺失'
 WHEN x.hash_verified=0 THEN '摘要校验未通过'
 WHEN x.file_exists=1 AND x.hash_verified=1 THEN '核验时文件存在且摘要一致'
 ELSE '文件或摘要待核验' END AS `网页存档状态`,
 x.file_path AS `网页文件位置`,p.product_id AS `商品编号`,e.source_ref AS `来源编号`
FROM products p LEFT JOIN product_evidence e ON e.product_id=p.product_id
LEFT JOIN `明细_来源网址` z ON z.`来源编号`=e.source_id
LEFT JOIN source_snapshots x ON x.source_ref=e.source_ref;

CREATE OR REPLACE ALGORITHM=TEMPTABLE SQL SECURITY INVOKER VIEW `明细_费用组成` AS
SELECT p.title AS `商品名称`,c.merchant_sku AS `商家SKU`,
 CASE c.cost_key WHEN 'purchase' THEN '商品采购' WHEN 'packaging' THEN '包装耗材'
 WHEN 'logistics' THEN '国内运费' WHEN 'expected_after_sales' THEN '售后准备_五项口径'
 WHEN 'other_variable' THEN '其他变动费用'
 ELSE CONCAT('待识别：',c.cost_key) END AS `费用名称`,
 CAST(ROUND(c.amount,2) AS DECIMAL(30,2)) AS `金额`,
 CASE c.currency WHEN 'CNY' THEN '人民币' WHEN 'EUR' THEN '欧元'
 WHEN 'USD' THEN '美元' ELSE COALESCE(c.currency,'未填写') END AS `币种`,
 CASE c.sales_unit WHEN 'set' THEN '每套' WHEN 'piece' THEN '每件'
 ELSE CONCAT('待核对：',COALESCE(c.sales_unit,'未填写')) END AS `计价单位`,
 CASE WHEN c.amount IS NULL THEN '金额待填写' WHEN c.confirmed=1 THEN '人工已确认输入'
 ELSE '估值或待核对' END AS `输入状态`,
 c.source_ref AS `凭证或依据`,c.product_id AS `商品编号`,c.position AS `显示顺序`
FROM sku_costs c JOIN products p ON p.product_id=c.product_id;

CREATE OR REPLACE ALGORITHM=TEMPTABLE SQL SECURITY INVOKER VIEW `面试02_商品成本` AS
SELECT v.title AS `商品名称`,v.merchant_sku AS `商家SKU`,v.pieces AS `每销售单位件数`,
 CASE v.sales_unit WHEN 'set' THEN '每套' WHEN 'piece' THEN '每件'
 ELSE CONCAT('待核对：',COALESCE(v.sales_unit,'未填写')) END AS `计价单位`,
 CAST(ROUND(v.supply_amount,2) AS DECIMAL(30,2)) AS `原供货报价`,
 CAST(ROUND(v.five_cost_total,2) AS DECIMAL(30,2)) AS `五项基础成本合计`,
 CASE v.supply_currency WHEN 'CNY' THEN '人民币' WHEN 'EUR' THEN '欧元'
 WHEN 'USD' THEN '美元' ELSE COALESCE(v.supply_currency,'未填写') END AS `报价币种`,
 CASE WHEN v.five_cost_total IS NULL THEN '金额或币种单位不齐_不可合计'
 WHEN c.confirmed_rows=5 THEN '五项输入已确认_完整净收益请看工作台'
 ELSE '含估值或待核对项_完整净收益请看工作台' END AS `核算提示`,
 v.product_id AS `商品编号`
FROM v_sku_cost_summary v LEFT JOIN (
 SELECT product_id,merchant_sku,
 SUM(confirmed=1) AS confirmed_rows
 FROM sku_costs GROUP BY product_id,merchant_sku
) c ON c.product_id=v.product_id AND c.merchant_sku=v.merchant_sku;

CREATE OR REPLACE ALGORITHM=TEMPTABLE SQL SECURITY INVOKER VIEW `面试03_买手核价` AS
SELECT p.title AS `商品名称`,COALESCE(f.sku_ref,'未指定SKU_商品整体') AS `关联商家SKU`,
 CASE f.platform_stage WHEN 'unsubmitted' THEN '尚未提报'
 WHEN 'selection' THEN '选品中' WHEN 'sample' THEN '寄样中'
 WHEN 'review' THEN '审核中' WHEN 'pricing' THEN '核价中'
 WHEN 'first' THEN '首单阶段' WHEN 'stock' THEN '备货阶段'
 WHEN 'sale' THEN '销售阶段' WHEN 'returned' THEN '退回处理'
 ELSE CONCAT('待识别：',COALESCE(f.platform_stage,'未填写')) END AS `平台阶段`,
 f.feedback_on AS `反馈日期`,CAST(ROUND(f.quote_amount,2) AS DECIMAL(30,2)) AS `买手建议供货价`,
 CASE f.quote_currency WHEN 'CNY' THEN '人民币' WHEN 'EUR' THEN '欧元'
 WHEN 'USD' THEN '美元' ELSE COALESCE(f.quote_currency,'未填写') END AS `币种`,
 CASE f.quote_unit WHEN 'set' THEN '每套' WHEN 'piece' THEN '每件'
 ELSE CONCAT('待核对：',COALESCE(f.quote_unit,'未填写')) END AS `计价单位`,
 CASE f.verification WHEN 'human_confirmed' THEN '人工已核对记录'
 WHEN 'draft' THEN '草稿_未核实' WHEN 'needs_review' THEN '待核对'
 ELSE CONCAT('待识别：',COALESCE(f.verification,'未填写')) END AS `记录核验状态`,
 CASE WHEN f.quote_amount IS NULL THEN '未填写核价' WHEN f.quote_confirmed=1 THEN '核价输入已确认'
 ELSE '核价估值或待核对' END AS `核价输入状态`,
 f.feedback_text AS `反馈原话`,f.evidence_ref AS `任务或截图依据`,
 f.product_id AS `商品编号`,f.feedback_id AS `反馈编号`,f.created_at AS `记录时间_UTC`
FROM buyer_feedback f JOIN products p ON p.product_id=f.product_id;
