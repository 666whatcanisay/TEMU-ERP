-- MySQL 8.0.42+, InnoDB, UTC DATETIME(6), opaque IDs use case-sensitive strings.
-- Entity creation is separate from transactional data import.
CREATE TABLE IF NOT EXISTS schema_migrations (
 version VARCHAR(80) PRIMARY KEY COMMENT '迁移版本',
 checksum CHAR(64) NOT NULL COMMENT 'DDL文件SHA256',
 applied_at DATETIME(6) NOT NULL COMMENT 'UTC完成时间',
 note VARCHAR(255) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='数据库版本与迁移记录';

CREATE TABLE IF NOT EXISTS sources (
 source_id VARCHAR(191) PRIMARY KEY COMMENT '来源ID，不使用网址作为主键',
 title TEXT, publisher VARCHAR(255), url TEXT COMMENT '原始网址，直接可查',
 source_level VARCHAR(64), locator TEXT COMMENT '原文定位',
 verification VARCHAR(96), observed_on DATE, retrieved_on DATE,
 display_price DECIMAL(30,12), currency VARCHAR(16), pieces INT,
 is_business_record BOOLEAN NOT NULL DEFAULT 1 COMMENT '商品证据或参考资料登记',
 registry_json LONGTEXT COMMENT '参考来源原始登记，不替换商品观察',
 snapshot_ref TEXT, sha256 VARCHAR(64), note TEXT,
 extension_json LONGTEXT NOT NULL COMMENT '未建模字段及DTO格式元数据',
 record_meta_json LONGTEXT NOT NULL,
 created_at DATETIME(6) NOT NULL, updated_at DATETIME(6) NOT NULL,
 KEY source_lookup(source_level,verification,observed_on),
 CHECK(JSON_VALID(extension_json)), CHECK(registry_json IS NULL OR JSON_VALID(registry_json))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='商品证据与规则研究来源，网址集中保存';

CREATE TABLE IF NOT EXISTS products (
 product_id VARCHAR(191) PRIMARY KEY, title TEXT, listing_title TEXT, market_title TEXT,
 material VARCHAR(255), research_market VARCHAR(32), market_currency VARCHAR(16),
 mode_assumption VARCHAR(32), mode_confirmed BOOLEAN, platform_product_id VARCHAR(191),
 internal_decision VARCHAR(32), synthetic BOOLEAN,
 rationale TEXT, advantage TEXT,
 extension_json LONGTEXT NOT NULL, record_meta_json LONGTEXT NOT NULL,
 created_at DATETIME(6) NOT NULL, updated_at DATETIME(6) NOT NULL,
 KEY product_worklist(research_market,internal_decision,updated_at),
 KEY platform_product_lookup(platform_product_id),
 CHECK(JSON_VALID(extension_json))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='候选商品主档，核心字段不藏在JSON';

CREATE TABLE IF NOT EXISTS product_suppliers (
 product_id VARCHAR(191) PRIMARY KEY, supplier_url TEXT, moq BIGINT, lead_days INT,
 source_ref TEXT, reference_text TEXT, confirmed BOOLEAN, extension_json LONGTEXT NOT NULL,
 CONSTRAINT supplier_product_fk FOREIGN KEY(product_id) REFERENCES products(product_id) ON DELETE CASCADE,
 CHECK(moq IS NULL OR moq>=1), CHECK(lead_days IS NULL OR lead_days>=0), CHECK(JSON_VALID(extension_json))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='商品供货条件，未取得供应商身份不伪造供应商主档';

CREATE TABLE IF NOT EXISTS product_materials (
 product_id VARCHAR(191) NOT NULL, material_key VARCHAR(64) NOT NULL,
 registered BOOLEAN NOT NULL, value_json LONGTEXT NOT NULL,
 PRIMARY KEY(product_id,material_key),
 CONSTRAINT material_product_fk FOREIGN KEY(product_id) REFERENCES products(product_id) ON DELETE CASCADE,
 CHECK(JSON_VALID(value_json))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='样品、照片、合规等材料登记';

CREATE TABLE IF NOT EXISTS product_decisions (
 product_id VARCHAR(191) NOT NULL, position INT NOT NULL,
 decision VARCHAR(32), reason TEXT, reviewer VARCHAR(255), decided_at DATETIME(6),
 extension_json LONGTEXT NOT NULL,
 PRIMARY KEY(product_id,position),
 CONSTRAINT decision_product_fk FOREIGN KEY(product_id) REFERENCES products(product_id) ON DELETE CASCADE,
 CHECK(JSON_VALID(extension_json))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='内部判断历史，与平台状态分离';

CREATE TABLE IF NOT EXISTS product_skus (
 product_id VARCHAR(191) NOT NULL, merchant_sku VARCHAR(191) NOT NULL,
 position INT NOT NULL, is_active BOOLEAN NOT NULL DEFAULT 1,
 merchant_group_code VARCHAR(191), platform_sku_id VARCHAR(191), platform_skc_id VARCHAR(191),
 sales_unit VARCHAR(32), pieces INT NOT NULL,
 supply_amount DECIMAL(30,12), supply_currency VARCHAR(16), supply_unit VARCHAR(32),
 supply_confirmed BOOLEAN, supply_source_ref TEXT,
 extension_json LONGTEXT NOT NULL,
 PRIMARY KEY(product_id,merchant_sku), KEY sku_platform_lookup(platform_sku_id),
 KEY sku_worklist(product_id,is_active,position),
 CONSTRAINT sku_product_fk FOREIGN KEY(product_id) REFERENCES products(product_id) ON DELETE RESTRICT,
 CHECK(pieces>0), CHECK(supply_amount IS NULL OR supply_amount>=0), CHECK(JSON_VALID(extension_json))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='商品一对多SKU，移除SKU停用保留核价历史';

CREATE TABLE IF NOT EXISTS sku_measurements (
 product_id VARCHAR(191) NOT NULL, merchant_sku VARCHAR(191) NOT NULL,
 scope VARCHAR(16) NOT NULL COMMENT 'set/item/package',
 length_cm DECIMAL(30,12), width_cm DECIMAL(30,12), height_cm DECIMAL(30,12),
 net_weight_g DECIMAL(30,12), gross_weight_g DECIMAL(30,12),
 extension_json LONGTEXT NOT NULL,
 PRIMARY KEY(product_id,merchant_sku,scope),
 CONSTRAINT measure_sku_fk FOREIGN KEY(product_id,merchant_sku) REFERENCES product_skus(product_id,merchant_sku) ON DELETE CASCADE,
 CHECK(gross_weight_g IS NULL OR net_weight_g IS NULL OR gross_weight_g>=net_weight_g),
 CHECK(JSON_VALID(extension_json))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='销售单位、单件和包装尺寸重量分别保存';

CREATE TABLE IF NOT EXISTS sku_attributes (
 product_id VARCHAR(191) NOT NULL, merchant_sku VARCHAR(191) NOT NULL, position INT NOT NULL,
 attribute_name VARCHAR(191), attribute_value TEXT, parent_spec_id VARCHAR(191), spec_id VARCHAR(191), source_ref TEXT,
 extension_json LONGTEXT NOT NULL,
 PRIMARY KEY(product_id,merchant_sku,position),
 CONSTRAINT attribute_sku_fk FOREIGN KEY(product_id,merchant_sku) REFERENCES product_skus(product_id,merchant_sku) ON DELETE CASCADE,
 CHECK(JSON_VALID(extension_json))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='销售属性，平台ID未知则NULL';

CREATE TABLE IF NOT EXISTS sku_components (
 product_id VARCHAR(191) NOT NULL, merchant_sku VARCHAR(191) NOT NULL, position INT NOT NULL,
 component_name VARCHAR(255), quantity INT NOT NULL, classification VARCHAR(191), extension_json LONGTEXT NOT NULL,
 PRIMARY KEY(product_id,merchant_sku,position),
 CONSTRAINT component_sku_fk FOREIGN KEY(product_id,merchant_sku) REFERENCES product_skus(product_id,merchant_sku) ON DELETE CASCADE,
 CHECK(quantity>0), CHECK(JSON_VALID(extension_json))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='套装组成，不从标题猜件数';

CREATE TABLE IF NOT EXISTS sku_costs (
 product_id VARCHAR(191) NOT NULL, merchant_sku VARCHAR(191) NOT NULL,
 cost_key VARCHAR(64) NOT NULL, position INT NOT NULL,
 amount DECIMAL(30,12), currency VARCHAR(16), sales_unit VARCHAR(32),
 confirmed BOOLEAN, source_ref TEXT, extension_json LONGTEXT NOT NULL,
 PRIMARY KEY(product_id,merchant_sku,cost_key),
 CONSTRAINT cost_sku_fk FOREIGN KEY(product_id,merchant_sku) REFERENCES product_skus(product_id,merchant_sku) ON DELETE CASCADE,
 CHECK(amount IS NULL OR amount>=0), CHECK(JSON_VALID(extension_json))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='五项基础成本明细，不等同完整净利润成本';

CREATE TABLE IF NOT EXISTS profit_parameter_definitions (
 model_version VARCHAR(64) NOT NULL, parameter_key VARCHAR(96) NOT NULL,
 label VARCHAR(255) NOT NULL, cost_group VARCHAR(64) NOT NULL, unit VARCHAR(64) NOT NULL,
 default_value DECIMAL(30,12) NOT NULL, category_source_ref VARCHAR(191), value_source_ref VARCHAR(191), note TEXT,
 PRIMARY KEY(model_version,parameter_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='版本化利润参数字典，默认值与费用类别来源分开';

CREATE TABLE IF NOT EXISTS sku_profit_plans (
 product_id VARCHAR(191) NOT NULL, merchant_sku VARCHAR(191) NOT NULL,
 model_version VARCHAR(64), currency VARCHAR(16), value_basis VARCHAR(64), extension_json LONGTEXT NOT NULL,
 PRIMARY KEY(product_id,merchant_sku),
 CONSTRAINT plan_sku_fk FOREIGN KEY(product_id,merchant_sku) REFERENCES product_skus(product_id,merchant_sku) ON DELETE CASCADE,
 CHECK(JSON_VALID(extension_json))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='SKU完整利润方案';

CREATE TABLE IF NOT EXISTS sku_profit_parameters (
 product_id VARCHAR(191) NOT NULL, merchant_sku VARCHAR(191) NOT NULL,
 model_version VARCHAR(64) NOT NULL, parameter_key VARCHAR(96) NOT NULL,
 parameter_value DECIMAL(30,12) NOT NULL, extension_json LONGTEXT NOT NULL,
 PRIMARY KEY(product_id,merchant_sku,parameter_key),
 CONSTRAINT parameter_plan_fk FOREIGN KEY(product_id,merchant_sku) REFERENCES sku_profit_plans(product_id,merchant_sku) ON DELETE CASCADE,
 CONSTRAINT parameter_definition_fk FOREIGN KEY(model_version,parameter_key) REFERENCES profit_parameter_definitions(model_version,parameter_key) ON DELETE RESTRICT,
 CHECK(parameter_value>=0), CHECK(JSON_VALID(extension_json))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='显式覆盖的预算参数，默认值由字典和模型版本确定';

CREATE TABLE IF NOT EXISTS sku_actual_costs (
 product_id VARCHAR(191) NOT NULL, merchant_sku VARCHAR(191) NOT NULL, cost_key VARCHAR(96) NOT NULL,
 amount DECIMAL(30,12) NOT NULL, source_ref TEXT NOT NULL, extension_json LONGTEXT NOT NULL,
 PRIMARY KEY(product_id,merchant_sku,cost_key),
 CONSTRAINT actual_plan_fk FOREIGN KEY(product_id,merchant_sku) REFERENCES sku_profit_plans(product_id,merchant_sku) ON DELETE CASCADE,
 CHECK(amount>=0), CHECK(JSON_VALID(extension_json))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='有凭证的实际费用替换，避免和预算重复计费';

CREATE TABLE IF NOT EXISTS product_evidence (
 product_id VARCHAR(191) NOT NULL, position INT NOT NULL,
 source_ref VARCHAR(191) NOT NULL, source_id VARCHAR(191),
 PRIMARY KEY(product_id,position), KEY evidence_reverse(source_id,product_id),
 CONSTRAINT evidence_product_fk FOREIGN KEY(product_id) REFERENCES products(product_id) ON DELETE CASCADE,
 CONSTRAINT evidence_source_fk FOREIGN KEY(source_id) REFERENCES sources(source_id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='商品与来源多对多，未解析引用保留原ID且外键为NULL';

CREATE TABLE IF NOT EXISTS buyer_feedback (
 feedback_id VARCHAR(191) PRIMARY KEY, product_id VARCHAR(191) NOT NULL,
 sku_ref VARCHAR(191), linked_sku VARCHAR(191), platform_stage VARCHAR(32), verification VARCHAR(64),
 feedback_on DATE, feedback_text TEXT, evidence_ref TEXT,
 quote_amount DECIMAL(30,12), quote_currency VARCHAR(16), quote_unit VARCHAR(32), quote_confirmed BOOLEAN, quote_source_ref TEXT,
 extension_json LONGTEXT NOT NULL, record_meta_json LONGTEXT NOT NULL,
 created_at DATETIME(6) NOT NULL, updated_at DATETIME(6) NOT NULL,
 KEY feedback_pricing(product_id,verification,created_at),
 CONSTRAINT feedback_product_fk FOREIGN KEY(product_id) REFERENCES products(product_id) ON DELETE RESTRICT,
 CONSTRAINT feedback_sku_fk FOREIGN KEY(product_id,linked_sku) REFERENCES product_skus(product_id,merchant_sku) ON DELETE RESTRICT,
 CHECK(quote_amount IS NULL OR quote_amount>=0), CHECK(JSON_VALID(extension_json))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='买手核价与任务反馈，SKU关联且保留原文';

CREATE TABLE IF NOT EXISTS business_policies (
 policy_id VARCHAR(191) PRIMARY KEY, metric VARCHAR(64), threshold_percent DECIMAL(30,12),
 confirmed BOOLEAN, confirmed_by VARCHAR(255), confirmed_on DATE, source_ref TEXT, policy_version VARCHAR(96),
 extension_json LONGTEXT NOT NULL, record_meta_json LONGTEXT NOT NULL,
 created_at DATETIME(6) NOT NULL, updated_at DATETIME(6) NOT NULL,
 CHECK(threshold_percent IS NULL OR threshold_percent>=0), CHECK(JSON_VALID(extension_json))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='公司经营政策，不伪装成平台规则';

CREATE TABLE IF NOT EXISTS source_snapshots (
 source_ref VARCHAR(191) PRIMARY KEY, source_id VARCHAR(191), snapshot_ref TEXT, sha256 VARCHAR(64), file_path TEXT,
 status VARCHAR(64) NOT NULL, captured_at DATETIME(6) NOT NULL, original_at VARCHAR(40) NOT NULL,
 payload_json LONGTEXT NOT NULL, file_exists BOOLEAN, hash_verified BOOLEAN,
 CONSTRAINT snapshot_source_fk FOREIGN KEY(source_id) REFERENCES sources(source_id) ON DELETE RESTRICT,
 CHECK(JSON_VALID(payload_json))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='网页快照索引，原文件留磁盘并校验哈希';

CREATE TABLE IF NOT EXISTS field_revisions (
 revision_id VARCHAR(191) PRIMARY KEY, product_id VARCHAR(191) NOT NULL, sku_ref VARCHAR(191),
 field_key VARCHAR(191) NOT NULL, before_json LONGTEXT, after_json LONGTEXT, reviewer VARCHAR(255), method VARCHAR(64),
 payload_json LONGTEXT NOT NULL, created_at DATETIME(6) NOT NULL, original_at VARCHAR(40) NOT NULL,
 KEY revision_product(product_id,created_at),
 CONSTRAINT revision_product_fk FOREIGN KEY(product_id) REFERENCES products(product_id) ON DELETE RESTRICT,
 CHECK(JSON_VALID(payload_json)), CHECK(before_json IS NULL OR JSON_VALID(before_json)), CHECK(after_json IS NULL OR JSON_VALID(after_json))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='字段修改审计，before/after单独可查，与商品同事务';

CREATE TABLE IF NOT EXISTS internal_submissions (
 submission_id VARCHAR(191) PRIMARY KEY, product_id VARCHAR(191) NOT NULL,
 title TEXT, research_market VARCHAR(32), created_at DATETIME(6) NOT NULL, original_at VARCHAR(40) NOT NULL,
 snapshot_json LONGTEXT NOT NULL COMMENT '不可随当前商品变化的历史提报快照',
 KEY submission_product(product_id,created_at),
 CONSTRAINT submission_product_fk FOREIGN KEY(product_id) REFERENCES products(product_id) ON DELETE RESTRICT,
 CHECK(JSON_VALID(snapshot_json))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='内部评审历史，JSON是历史快照而非商品主档';

CREATE TABLE IF NOT EXISTS integration_status (
 port_key VARCHAR(191) PRIMARY KEY, status VARCHAR(64) NOT NULL, detail_json LONGTEXT NOT NULL,
 updated_at DATETIME(6) NOT NULL, original_at VARCHAR(40) NOT NULL,
 CHECK(JSON_VALID(detail_json))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='集成运行状态，未实现接口不伪成功';

CREATE OR REPLACE VIEW v_product_evidence AS
SELECT p.product_id,p.title AS product_title,e.source_ref,s.title AS source_title,s.url,s.source_level,s.verification,s.observed_on,
 CASE WHEN e.source_id IS NULL THEN 'unresolved' ELSE 'linked' END AS link_status,
 x.file_path AS snapshot_file,x.sha256,x.file_exists,x.hash_verified
FROM product_evidence e JOIN products p ON p.product_id=e.product_id
LEFT JOIN sources s ON s.source_id=e.source_id LEFT JOIN source_snapshots x ON x.source_ref=e.source_ref;

CREATE OR REPLACE VIEW v_sku_cost_summary AS
SELECT s.product_id,p.title,s.merchant_sku,s.pieces,s.sales_unit,s.supply_amount,s.supply_currency,
 COUNT(c.cost_key) AS cost_rows,SUM(c.amount IS NULL) AS unknown_cost_rows,
 CASE WHEN COUNT(c.cost_key)=5 AND COUNT(c.amount)=5 AND MIN(c.currency)=MAX(c.currency)
 AND MIN(c.currency)=s.supply_currency AND MIN(c.sales_unit)=MAX(c.sales_unit) AND MIN(c.sales_unit)=s.sales_unit
 THEN SUM(c.amount) ELSE NULL END AS five_cost_total
FROM product_skus s JOIN products p ON p.product_id=s.product_id
LEFT JOIN sku_costs c ON c.product_id=s.product_id AND c.merchant_sku=s.merchant_sku
WHERE s.is_active=1 GROUP BY s.product_id,p.title,s.merchant_sku,s.pieces,s.sales_unit,s.supply_amount,s.supply_currency;

CREATE OR REPLACE VIEW v_buyer_quote_history AS
SELECT f.product_id,p.title,f.sku_ref,f.platform_stage,f.feedback_on,f.quote_amount,f.quote_currency,f.quote_unit,
 f.verification,f.feedback_text,f.evidence_ref,f.created_at
FROM buyer_feedback f JOIN products p ON p.product_id=f.product_id;

CREATE OR REPLACE VIEW v_effective_profit_parameters AS
SELECT p.product_id,p.merchant_sku,d.parameter_key,d.label,d.cost_group,d.unit,
 COALESCE(v.parameter_value,d.default_value) AS effective_value,
 CASE WHEN v.parameter_key IS NULL THEN 'model_default' ELSE 'sku_override' END AS value_origin,
 d.category_source_ref,d.value_source_ref,d.model_version
FROM sku_profit_plans p JOIN profit_parameter_definitions d ON d.model_version=COALESCE(p.model_version,'full-cost/2.0')
LEFT JOIN sku_profit_parameters v ON v.product_id=p.product_id AND v.merchant_sku=p.merchant_sku AND v.parameter_key=d.parameter_key;
