"""Repeatable, read-only Chinese presentation. Never rewrites business rows.

The immutable core migration checksum is independent of these comments/views.
DDL commits implicitly. Mark completion only after all statements succeed, so an
interrupted installation is safely repeatable on the next start.
"""
from datetime import datetime, timezone
import hashlib
import json
import re

from . import mysql_schema as schema

VERSION='presentation-zh/v1'
SQL_PATH=schema.ROOT/'database/repeatable/R__chinese_views.sql'
VIEWS=('面试01_选品证据','面试02_商品成本','面试03_买手核价','明细_费用组成','明细_来源网址')

TABLE_COMMENTS={
 'products':'候选商品主档：一个商品可有多个商家SKU',
 'product_skus':'商品规格与供货报价：停用保留核价历史',
 'sku_costs':'五项基础成本：采购、包装、国内运费、售后准备、其他费用；不是完整净收益',
 'sources':'来源登记：原始网址、原文定位、核验状态集中保存',
 'product_evidence':'商品与证据的多对多关联：未解析引用保留原编号',
 'buyer_feedback':'买手与平台反馈：原文、核价及凭证按SKU关联',
}

# Complete coverage is checked before any DDL. Shared names retain one meaning.
COLUMNS={
 'version':'数据库迁移版本','checksum':'结构定义摘要SHA256','applied_at':'迁移完成时间，UTC',
 'note':'补充说明','source_id':'已关联的来源主键','title':'中文名称或标题',
 'publisher':'发布机构或网站','url':'原始网页网址，可直接打开','source_level':'来源类别编码，中文见明细_来源网址',
 'locator':'原文位置或段落','verification':'核验状态编码，中文见展示视图',
 'observed_on':'商品或资料观察日期','retrieved_on':'网页查阅日期','display_price':'页面展示价格，需结合币种与件数',
 'currency':'币种编码，CNY人民币、EUR欧元、USD美元','pieces':'每销售单位包含的件数',
 'is_business_record':'是否为业务来源记录，1是、0仅参考资料',
 'registry_json':'参考资料原始登记，不替换业务观察','snapshot_ref':'网页快照引用',
 'sha256':'网页文件内容摘要SHA256','extension_json':'未建模字段及兼容格式信息，非业务主字段',
 'record_meta_json':'旧格式记录元信息','created_at':'记录建立时间，UTC','updated_at':'最近修改时间，UTC',
 'product_id':'候选商品编号，关联products商品主档','listing_title':'提报英文标题草稿',
 'market_title':'市场检索标题','material':'商品材质','research_market':'研究市场编码，DE德国',
 'market_currency':'研究市场币种，EUR欧元','mode_assumption':'经营模式假设，fully_managed全托管',
 'mode_confirmed':'模式是否确认，1是、0否、NULL未知','platform_product_id':'平台返回的商品ID，未知留空',
 'internal_decision':'内部选品判断编码，与平台审核分开','synthetic':'是否合成示例记录，1是、0否',
 'rationale':'候选判断理由','advantage':'供货或产品优势','supplier_url':'供货依据网址',
 'moq':'供应商起订量','lead_days':'备货交期，天','source_ref':'原始依据编号或凭证引用',
 'reference_text':'供货依据原文','confirmed':'输入是否经人工确认，1是、0否、NULL未知',
 'material_key':'资料项目编码','registered':'资料是否已登记，1是、0否','value_json':'资料登记内容',
 'position':'列表显示顺序，从0开始','decision':'当次内部决策编码','reason':'决策原因',
 'reviewer':'核对或修改人员','decided_at':'决策时间，UTC','merchant_sku':'商家SKU，区分颜色规格套装',
 'is_active':'SKU是否在用，1在用、0停用保留历史','merchant_group_code':'商家商品分组货号',
 'platform_sku_id':'平台返回的SKU ID，未知留空','platform_skc_id':'平台返回的SKC ID，未知留空',
 'sales_unit':'计价单位编码，set每套、piece每件','supply_amount':'商家原供货报价，非买手最新核价',
 'supply_currency':'原供货报价币种','supply_unit':'原供货报价单位，set每套、piece每件',
 'supply_confirmed':'原供货报价输入是否人工确认','supply_source_ref':'原供货报价依据',
 'scope':'尺寸范围，set整套、item单件、package包装','length_cm':'长度，厘米','width_cm':'宽度，厘米',
 'height_cm':'高度，厘米','net_weight_g':'净重，克','gross_weight_g':'毛重，克',
 'attribute_name':'销售属性名称，如颜色','attribute_value':'销售属性值，如灰色',
 'parent_spec_id':'平台父属性ID，未知留空','spec_id':'平台属性值ID，未知留空',
 'component_name':'套装内组件名称','quantity':'组件数量','classification':'组件分类',
 'cost_key':'费用项目编码，中文见明细_费用组成','amount':'费用金额，须结合币种及计价单位，NULL未知',
 'model_version':'完整利润模型版本','parameter_key':'利润参数编码','label':'参数中文名称',
 'cost_group':'费用分组','unit':'参数单位，比例与金额分开','default_value':'版本化默认估值，不等于平台标准',
 'category_source_ref':'费用类别依据引用','value_source_ref':'具体参数数值依据引用',
 'value_basis':'计价与税费口径','parameter_value':'该SKU显式覆盖的参数值',
 'feedback_id':'反馈记录编号','sku_ref':'原反馈指定的商家SKU，空为商品整体',
 'linked_sku':'已解析关联的商家SKU','platform_stage':'平台任务阶段编码，中文见面试03_买手核价',
 'feedback_on':'反馈业务日期','feedback_text':'买手或平台反馈原话','evidence_ref':'平台任务编号或截图凭证',
 'quote_amount':'本条反馈中的买手建议供货价','quote_currency':'买手核价币种',
 'quote_unit':'买手核价计价单位，set每套、piece每件','quote_confirmed':'核价输入是否经人工确认',
 'quote_source_ref':'买手核价输入依据','policy_id':'公司经营政策编号',
 'metric':'利润门槛指标，收入贡献率与加价率分开','threshold_percent':'公司目标门槛，百分数',
 'confirmed_by':'政策确认人员','confirmed_on':'政策确认日期','policy_version':'政策版本',
 'file_path':'本地网页快照文件路径','status':'运行状态编码','captured_at':'快照抓取时间，UTC',
 'original_at':'原记录带时区的时间文本','payload_json':'历史记录原始内容',
 'file_exists':'最近核验时文件是否存在，1是、0否、NULL未知',
 'hash_verified':'最近核验时文件摘要是否一致，1是、0否、NULL未知',
 'revision_id':'字段修订流水编号','field_key':'被修改的字段路径','before_json':'修改前的值',
 'after_json':'修改后的值','method':'修改来源或方法','submission_id':'内部提报快照编号',
 'snapshot_json':'生成当时的完整内部提报快照，后续改价不覆盖',
 'port_key':'集成能力编码','detail_json':'接口运行详情或未配置原因',
}


def fingerprint():
    body=SQL_PATH.read_text(encoding='utf-8')+json.dumps([TABLE_COMMENTS,COLUMNS],ensure_ascii=False,sort_keys=True)
    return hashlib.sha256(body.encode('utf-8')).hexdigest()


def ensure_chinese_presentation(store):
    if store._in_transaction:
        raise RuntimeError('中文展示DDL不得在业务事务内执行')
    digest=fingerprint()
    marker=store._execute('SELECT checksum FROM schema_migrations WHERE version=?',(VERSION,)).fetchone()
    if marker and marker['checksum']==digest:return False
    names=(*schema.TABLES,'schema_migrations')
    marks=','.join('?' for _ in names)
    rows=store._execute('SELECT TABLE_NAME,COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,COLUMN_DEFAULT,EXTRA,'
        'CHARACTER_SET_NAME,COLLATION_NAME,COLUMN_COMMENT FROM information_schema.columns '
        f'WHERE table_schema=DATABASE() AND table_name IN ({marks}) ORDER BY TABLE_NAME,ORDINAL_POSITION',names).fetchall()
    missing={r['COLUMN_NAME'] for r in rows}-COLUMNS.keys()
    if missing:raise RuntimeError('请先补齐字段中文说明：'+','.join(sorted(missing)))
    if {r['TABLE_NAME'] for r in rows}!=set(names):raise RuntimeError('业务表不完整，不能安装中文展示')
    # Never accidentally remove generated columns, auto-increment or ON UPDATE.
    if any(r['EXTRA'] for r in rows):raise RuntimeError('遇到未支持的列属性，请创建显式迁移')
    quote=store._conn.escape
    changes={}
    for row in rows:
        name=row['COLUMN_NAME'];table=row['TABLE_NAME']
        assert re.fullmatch(r'[a-z0-9_]+',name)
        comment=COLUMNS[name]
        if table=='sources' and name=='source_id':comment='来源主键编号，不以网址作为主键'
        if row['COLUMN_COMMENT']==comment:continue
        definition=f'`{name}` {row["COLUMN_TYPE"]}'
        if row['CHARACTER_SET_NAME']:
            definition+=f' CHARACTER SET {row["CHARACTER_SET_NAME"]} COLLATE {row["COLLATION_NAME"]}'
        definition+=' NULL' if row['IS_NULLABLE']=='YES' else ' NOT NULL'
        if row['COLUMN_DEFAULT'] is not None:definition+=' DEFAULT '+quote(row['COLUMN_DEFAULT'])
        elif row['IS_NULLABLE']=='YES':definition+=' DEFAULT NULL'
        changes.setdefault(table,[]).append('MODIFY COLUMN '+definition+' COMMENT '+quote(comment))
    for table in names:
        parts=changes.get(table,[])
        if table in TABLE_COMMENTS:parts=parts+['COMMENT='+quote(TABLE_COMMENTS[table])]
        if parts:store._execute(f'ALTER TABLE `{table}` '+','.join(parts))
    for statement in SQL_PATH.read_text(encoding='utf-8').split(';'):
        if statement.strip():store._execute(statement.strip())
    store._put('schema_migrations',dict(version=VERSION,checksum=digest,
        applied_at=datetime.now(timezone.utc).replace(tzinfo=None),note='可重复安装的中文只读视图及字段注释，业务行未改写'),['version'])
    return True
