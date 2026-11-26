-- Navicat 演示用，只读。选择 temu_workbench 后逐条执行。

-- 面试先看这三个中文视图，每行含商品名称，金额按分显示。
SELECT * FROM `面试01_选品证据` ORDER BY `商品编号`;
SELECT * FROM `面试02_商品成本` ORDER BY `商品编号`;
SELECT * FROM `面试03_买手核价` ORDER BY `记录时间_UTC` DESC;

-- sku_costs 的中文明细：每笔费用及依据。
SELECT * FROM `明细_费用组成`
WHERE `商品编号`='DE-DRAWER-006' ORDER BY `显示顺序`;

-- 全部来源网址，包括尚未关联商品的规则依据。
SELECT * FROM `明细_来源网址` ORDER BY `来源编号`;

-- 以下为深入追问时使用的原字段查询。

-- 1 商品主档：不需要解析JSON才能看名字。
SELECT product_id,title,research_market,material,internal_decision,created_at
FROM products ORDER BY updated_at DESC;

-- 2 商品、SKU和基础成本。five_cost_total是原五项成本，不是完整成本或净利润。
SELECT product_id,title,merchant_sku,pieces,sales_unit,supply_amount,supply_currency,
       cost_rows,unknown_cost_rows,five_cost_total
FROM v_sku_cost_summary;

-- 3 证据网址与本地网页文件，未知来源会显式显示unresolved。
SELECT product_id,product_title,source_ref,source_title,url,source_level,
       verification,observed_on,link_status,snapshot_file,hash_verified
FROM v_product_evidence ORDER BY product_id;

-- 4 某个SKU每项成本及凭证。
SELECT cost_key,amount,currency,sales_unit,confirmed,source_ref
FROM sku_costs
WHERE product_id='DE-DRAWER-006' AND merchant_sku='ORG-HONEY-BRN-06'
ORDER BY position;

-- 5 完整利润参数的生效值、默认/覆盖状态和依据。
SELECT parameter_key,label,effective_value,unit,value_origin,category_source_ref,value_source_ref
FROM v_effective_profit_parameters
WHERE product_id='DE-DRAWER-006' AND merchant_sku='ORG-HONEY-BRN-06';

-- 6 买手核价历史。草稿与已核验保留不同状态。
SELECT product_id,sku_ref,feedback_on,quote_amount,quote_currency,verification,feedback_text,evidence_ref
FROM v_buyer_quote_history ORDER BY created_at DESC;

-- 7 修改审计，直接看变更前后。
SELECT product_id,sku_ref,field_key,before_json,after_json,reviewer,created_at
FROM field_revisions ORDER BY created_at DESC;

-- 8 数据库约束和迁移版本。
SELECT version,checksum,applied_at,note FROM schema_migrations;
SELECT table_name,constraint_name,referenced_table_name
FROM information_schema.referential_constraints
WHERE constraint_schema=DATABASE() ORDER BY table_name;

-- 9 网页原文件是否在核验时存在、是否匹配原摘要。
SELECT source_ref,file_path,sha256,file_exists,hash_verified,status,captured_at
FROM source_snapshots;
