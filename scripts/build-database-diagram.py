"""Build a repository-native SVG of the implemented database's core relations."""
from html import escape
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def text(x,y,value,size=18,fill='#26384b',bold=False):
    return f'<text x="{x}" y="{y}" font-family="Segoe UI,Microsoft YaHei,sans-serif" font-size="{size}" font-weight="{700 if bold else 400}" fill="{fill}">{escape(value)}</text>'


def card(x,y,title,name,lines):
    result=f'<rect x="{x}" y="{y}" width="350" height="190" rx="16" fill="white" stroke="#d9e2ec"/>'
    result+=text(x+22,y+32,title,23,bold=True)+text(x+22,y+59,name,15,'#bd4c10')
    for i,line in enumerate(lines):result+=text(x+22,y+94+i*25,line,16,'#54667a')
    return result


def edge(path,label,x,y):
    return f'<path d="{path}" fill="none" stroke="#8495a9" stroke-width="2" marker-end="url(#end)"/>'+text(x,y,label,15,'#65778c')


def build():
    items=[f'<rect width="1440" height="1120" rx="24" fill="#f6f8fc"/>',
        text(40,55,'MySQL 业务数据库',34,bold=True),text(40,92,'商品 · SKU · 成本 · 证据 · 买手核价 · 内部提报',21,'#65778c'),
        text(40,126,'21 张业务/字典表 + 1 张版本表  /  19 条外键  /  9 个查询视图（5 中文 + 4 技术）',16,'#bd4c10')]
    positions=[
        (40,160,'证据与规则来源','sources',['PK source_id','url / level / verification','观察价格、币种、日期']),
        (545,160,'商品主档','products',['PK product_id','名称 / 市场 / 内部决定','平台 ID 保留原始字符串']),
        (1050,160,'历史内部提报','internal_submissions',['PK submission_id · FK product_id','生成时刻 / 商品 / 标题','历史 snapshot_json 禁止覆盖']),
        (40,455,'商品与证据关联','product_evidence',['FK product_id + FK source_id','一条来源可供多商品复核','未解析引用保留并显式标识']),
        (545,455,'商品变体','product_skus',['PK (product_id, merchant_sku)','报价 / 件数 / 单位 / 平台 ID','移除用停用，保留历史关联']),
        (1050,455,'买手反馈与核价','buyer_feedback',['PK feedback_id · 商品/SKU外键','原话 / 凭证 / 日期 / 核价','草稿与已核验状态分别保存']),
        (40,750,'网页快照索引','source_snapshots',['FK source_id','磁盘路径 / SHA256 / 核验状态','网页文件不混入商品主档']),
        (545,750,'SKU 基础成本','sku_costs',['FK 商品 + SKU · 费用键唯一','DECIMAL 金额 / 币种 / 单位','未知 NULL；预算与确认分开']),
        (1050,750,'完整利润方案','sku_profit_plans',['FK 商品 + SKU','预算参数覆盖 / 实际账单替换','默认参数有版本、单位与出处']),
    ]
    # Draw relations behind cards. Parent-to-child arrows are marked 1:N.
    items += [edge('M215 350 V447','1 : N',230,403),edge('M545 260 H465 V550 H398','1 : N',475,405),
        edge('M720 350 V447','1 : N',734,404),edge('M895 255 H1042','1 : N',944,241),
        edge('M895 550 H1042','1 : N',944,536),edge('M720 645 V742','1 : N',734,705),
        edge('M895 598 H975 V845 H1042','1 : 1',984,708),edge('M55 350 H18 V845 H32','1 : 0..1',25,716)]
    for args in positions:items.append(card(*args))
    items += [text(40,1000,'其余关联表',20,bold=True),
        text(40,1032,'供货条件 / 材料 / 决定历史 / 尺寸 / 销售属性 / 套装组成 / 参数字典与覆盖 / 实际费用 / 公司政策 / 审计 / 集成状态',16,'#65778c'),
        text(40,1076,'核心字段从关系表读取；扩展 JSON 保留未知字段，历史提报快照保留当时依据。完整外键以建表 SQL 为准。',16,'#65778c')]
    svg='<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="1120" viewBox="0 0 1440 1120" role="img" aria-labelledby="title desc"><title id="title">Temu全托管选品工作台数据库核心关系图</title><desc id="desc">商品与SKU一对多，商品和来源多对多，费用和反馈按SKU关联。图中显示核心关系，完整定义见数据库建表SQL。</desc><defs><marker id="end" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8" fill="none" stroke="#8495a9" stroke-width="1.5"/></marker></defs>'+''.join(items)+'</svg>'
    (ROOT/'docs/assets/database-er.svg').write_text(svg,encoding='utf-8')
    print('Built docs/assets/database-er.svg')


if __name__=='__main__':build()
