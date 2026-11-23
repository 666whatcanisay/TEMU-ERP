"""Add four public-reference products and explicit full-cost budgets locally."""
from pathlib import Path
import copy
import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from html import escape
from app.backend.adapters.storage_sqlite import SQLiteStore
from app.backend.application.services import WorkbenchService
from app.backend.adapters.collector_http import HttpEvidenceCollector
from app.backend.adapters.extraction_rules import RuleExtractor
from app.backend.domain.ports import CollectRequest,ExtractRequest
from app.backend.domain import profit_model

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/full-profit-20261123'; OUT.mkdir(parents=True,exist_ok=True)
spec=importlib.util.spec_from_file_location('case',ROOT/'scripts/prepare-business-case.py')
case=importlib.util.module_from_spec(spec);spec.loader.exec_module(case)
BASE='https://relaxdays.de/produkte/haushaltsprodukte/verstauen-sortieren/'
PRODUCTS=[
 {'id':'DE-CUBE-004','sku':'ORG-CUBE-GRY-04','title':'折叠布艺收纳箱 · 灰色4件套','english':'4-Pack Foldable Fabric Storage Cubes, Grey, 30 cm',
  'url':BASE+'aufbewahrungsboxen/graue-aufbewahrungsbox-im-4er-set-10047015.html','retailer_id':'10047015','retail':'17.99',
  'dims':['30','30','30'],'pieces':4,'weight':'500','gross':'2200','pack':['32','32','12'],'material':'nonwoven/cardboard/iron','color':'灰色',
  'costs':['29.00','2.40','4.20','1.00','0.90'],'quote':'52.00','weight_factor':'1.6'},
 {'id':'DE-LINEN-004','sku':'ORG-LINEN-GRY-04','title':'内衣袜子分格收纳盒 · 4件套','english':'4-Pack Fabric Drawer Organizers, Grey, 16 Compartments Each',
  'url':BASE+'schubladen-organizer/unterwasche-organizer-4er-set-10048051.html','retailer_id':'10048051','retail':'20.99',
  'dims':['29','29','9'],'pieces':4,'weight':'200','gross':'950','pack':['31','31','10'],'material':'polyester/plastic/cardboard','color':'灰色',
  'costs':['19.00','1.40','2.50','0.80','0.70'],'quote':'42.00','weight_factor':'1.0'},
 {'id':'DE-BAMBOO-001','sku':'ORG-BAMBOO-NAT-01','title':'竹制桌面抽屉整理盒 · 四格','english':'Bamboo Drawer Organizer, Four Compartments, Natural',
  'url':BASE+'schubladen-organizer/schubladenorganizer-mit-4-fachern-10039317.html','retailer_id':'10039317','retail':'12.99',
  'dims':['28','16','4'],'pieces':1,'weight':'350','gross':'450','pack':['30','18','6'],'material':'bamboo/fibreboard','color':'原木色',
  'costs':['11.00','1.30','2.00','0.70','0.60'],'quote':'22.00','weight_factor':'1.1'},
 {'id':'DE-TRAY-001','sku':'ORG-TRAY-BGE-01','title':'小号PP抽屉收纳盒 · 单件','english':'Small Plastic Drawer Storage Tray, Beige, 10 x 20 x 5 cm',
  'url':'https://www.ikea.com/de/de/p/nojig-sortierbox-kunststoff-beige-70457487/','retailer_id':'70457487','retail':'0.50',
  'dims':['10','20','5'],'pieces':1,'weight':None,'gross':'50','pack':['21','11','6'],'material':'polypropylene','color':'米色',
  'costs':['0.80','0.25','0.45','0.10','0.10'],'quote':'2.80','weight_factor':'0.3'},
]

def references():
    return [
      {'id':'MIAO-FULL-FINANCE','level':'vendor_integration_doc','publisher':'妙手ERP','title':'利润明细—Temu全托管',
       'url':'https://erp.91miaoshou.com/help_center/article_8772.html','locator':'三、数据列说明：平台收入/支出/订单成本；售后、扣款、退回、贴标及EPR',
       'reviewed_at':'2026-11-23','verification':'vendor_body_read','scope':'全托管财务字段类型','limit':'费用类别依据；不提供本案例默认事件率和扣款金额；实际以当前店铺账单为准'},
      {'id':'DXM-FINANCE','level':'vendor_integration_doc','publisher':'店小秘','title':'Temu全/半托管财务结算数据采集范围',
       'url':'https://help.dianxiaomi.com/article/financialManagement/3438','locator':'全托管采集范围：账务中心、EPR、仓储综合服务费、销量和申报价格',
       'reviewed_at':'2026-11-23','verification':'vendor_body_read','scope':'明确区分全托管与半托管财务范围','limit':'字段范围参考，不是统一费率，也不证明已接入真实账号'},
      {'id':'CN-CIT','level':'official_law','publisher':'国家法律/政府公开文本','title':'中华人民共和国企业所得税法',
       'url':'https://www.szns.gov.cn/ztzl/nsrdzt/2025ggpyfwzq/zczq/content/post_12229917.html','locator':'第四条一般税率25%；应纳税所得额与扣除规则',
       'reviewed_at':'2026-11-23','verification':'official_body_read','scope':'一般企业所得税情景','limit':'企业资质/税基未知，本工具不进行年度税务申报或自动判定优惠资格'},
      {'id':'CN-SMALL-CIT','level':'official_guidance','publisher':'国家税务总局','title':'小型微利企业条件与2023—2027年所得税优惠',
       'url':'https://www.chinatax.gov.cn/chinatax/n810356/n3255681/c5240479/content.html','locator':'资质条件、优惠期限及不符合条件需补缴',
       'reviewed_at':'2026-11-23','verification':'official_body_read','scope':'符合条件的企业','limit':'本案例未核实年度所得额/人数/资产等全部条件，不自动使用5%'},
      {'id':'SF-DOMESTIC-QUOTE','level':'official_guidance','publisher':'顺丰','title':'国内运费查询及体积重量说明',
       'url':'https://www.sf-express.com/mobile/cn/sc/dynamic_functions/price','locator':'重量、体积、流向共同影响收费，实际下单界面计费详情',
       'reviewed_at':'2026-11-23','verification':'official_body_read','scope':'国内运费估算方法','limit':'不是本案例物流报价；不把国际进口/出口价表套到国内入仓，也不假定平台补贴一半'},
      {'id':'PROFIT-ASSUMPTIONS','level':'internal_method','publisher':'内部预算与测算契约','title':'完整利润模型、默认估值及防重复规则',
       'url':'http://127.0.0.1:8765/static/profit-method.html','locator':'费用类别、默认值、税费与分摊过程，full-cost/2.0',
       'reviewed_at':'2026-11-23','verification':'internal_assumptions_explicit','scope':'本机可调整预算情景','limit':'默认概率、金额、计划数量为估值；有规则出处不等于其规定了这些数值'},
    ]

def capture(p):
    host='www.ikea.com' if 'ikea.com' in p['url'] else 'relaxdays.de'
    result=HttpEvidenceCollector(ROOT/'.cache/profit-evidence').collect(CollectRequest(p['retailer_id'],p['url'],(host,),timeout_seconds=10))
    info={'status':result.status,'payload':result.payload,'error_code':result.error_code}
    if result.status=='succeeded':
        extraction=RuleExtractor().extract(ExtractRequest('catalog',result.payload['file_path'],('title','display_price')))
        info['extraction']=extraction.payload
    return p['id'],info

def build_records(p,info):
    source={'record_type':'source','id':'REF-'+p['retailer_id'],'level':'market_observation','publisher':'IKEA' if 'ikea' in p['url'] else 'Relaxdays GmbH',
      'title':p['title']+' · 德国公开参照','url':p['url'],'locator':f"零售商货号 {p['retailer_id']}，商品详情尺寸/件数/材质；零售标价区域",
      'scope':{'country':'DE','pieces':p['pieces'],'product_dimensions_cm':p['dims'],'material':p['material']},
      'observed_at':'2026-11-23','verification':'public_body_reviewed','facts':{'display_price':p['retail'],'currency':'EUR','tax_included':True,'retailer_item_id':p['retailer_id'],'sales':None},
      'note':'公开商品仅作规格与市场参考；本公司采购成本、包装尺寸及核价由内部预算输入；无销量证明。'}
    if info['status']=='succeeded':
        raw=info['payload'];source.update(snapshot_ref=raw['file_path'],sha256=raw['sha256'],retrieved_at='2026-11-23')
        source['facts']['extracted_candidates']=info.get('extraction',{}).get('fields',{})
        price=source['facts']['extracted_candidates'].get('display_price')
        if price and price.get('currency')=='EUR':source['facts']['display_price']=price['value']
        else:source['note']+=' 本次未唯一提取价格，标价保留已读取的公开观察值。'
    _,candidate,_=case.case_records()
    candidate=copy.deepcopy(candidate)
    candidate.update(id=p['id'],title=p['title'],listing_title=p['english'],market_title=None,material=p['material'],
                     evidence_refs=[source['id']],internal_decision='research',decision_history=[],supplier={'url':None,'moq':None,'lead_days':None})
    candidate['provenance']={'public_product':{'source_id':source['id'],'url':p['url'],'scope':'公开规格参照，不证明本公司货源或销量'},
      'costs':{'origin':'scenario_assumption','reference':'PROFIT-ASSUMPTIONS','scope':'采购、包材与物流为预算，单位人民币；国内运费按首批线路预算/备货数量分摊，无平台补贴假定'},
      'packaging':{'origin':'scenario_assumption','reference':'PROFIT-ASSUMPTIONS','scope':'运输包装尺寸/毛重为测算输入，待实物称量'},
      'profit':{'origin':'scenario_assumption','reference':'PROFIT-ASSUMPTIONS','scope':'完整利润参数可在编辑SKU调整；不把零售欧元价当供货收入'}}
    sku=candidate['skus'][0]
    sku.update(merchant_sku=p['sku'],merchant_group_code=p['sku'].rsplit('-',1)[0],pieces=p['pieces'],sales_unit='set' if p['pieces']>1 else 'piece',material=p['material'],
      sale_spec_bindings=[{'name':'颜色','value':p['color'],'parent_spec_id':None,'spec_id':None,'source_ref':source['id']}],
      pack_composition=[{'name':p['title'].split(' · ')[0],'count':p['pieces'],'product_dimensions_cm':p['dims'],'classification':None}],
      profit_plan={'version':profit_model.VERSION,'currency':'CNY','inputs':{'sku_weight':p['weight_factor']},'value_basis':'budget_assumptions'})
    net=str(float(p['weight'])*p['pieces']).removesuffix('.0') if p['weight'] else None
    dims=lambda a:{'length_cm':a[0],'width_cm':a[1],'height_cm':a[2],'unit':'cm'}
    sku['specs']={'dimensions':dims(p['dims']) if p['pieces']==1 else dims([None,None,None]),'weight':{'net_weight_g':net,'gross_weight_g':p['gross'],'unit':'g'},
      'item':{'dimensions':dims(p['dims']),'weight':{'net_weight_g':p['weight'],'gross_weight_g':None,'unit':'g'}},
      'package':{'dimensions':dims(p['pack']),'weight':{'net_weight_g':net,'gross_weight_g':p['gross'],'unit':'g'}}}
    sku['supply_income'].update(amount=p['quote'],sales_unit=sku['sales_unit'],confirmed=True,source_ref='budget:'+p['id']+'/offer')
    for cost,value in zip(sku['costs'],p['costs']):
        cost['money'].update(amount=value,sales_unit=sku['sales_unit'],confirmed=True,source_ref='budget:'+p['id']+'/'+cost['key'])
    return source,candidate

def method_page():
    items=''.join(f'<tr><td>{escape(f["label"])}</td><td>{f["default"]} {escape(f["unit"])}</td><td>{escape(f["note"])}</td></tr>' for f in profit_model.SCHEMA)
    refs=''.join(f'<p><a href="{escape(r["url"])}">{escape(r["title"])}</a>：{escape(r["limit"])}</p>' for r in references() if r['id']!='PROFIT-ASSUMPTIONS')
    html=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>完整利润模型与估值依据</title><link rel="stylesheet" href="/static/styles.css"><main id="view-root"><h2>完整利润模型与估值依据</h2><p class="meta">2026-11-23 · full-cost/2.0 · Temu全托管商家视角</p><section class="panel"><h3>计算口径</h3><p>单位为一个初次形成供货结算的销售单位（件或套）。报价与现金成本采用同一币种；本轮为人民币。税后净收益估算 = 供货价 − 商品及正向履约 − 商家责任退款及退回 − 售前未结算损耗分摊 − 扣款/赔付准备 − 平台服务 − 固定/开发费用分摊 − 资金占用 − 间接税净负担 − 所得税测算 + 已设定补贴或残值冲回。</p><p>这是含税现金收支与成本分摊结合的经营测算；不是已结算财务报表利润。间接税参数是抵扣/退税后现金净负担预留，不是法定增值税率。所得税按情景比例计入，税基与年度纳税调整需实际账务核实。净收益率分母为名义供货价，不是德国零售价格。</p><h3>避免重复计算</h3><p>旧版售后汇总不再叠加；退款已冲减收入，原货物采购成本不再扣一次。售前未形成结算的损耗，按损耗率/(1−损耗率)另分摊未回收成本。退回物流只计新增运费/分拣/重包。已列在国内正向运费的揽收费不重复加，日常自贴标签与平台额外贴标分开。保证金本金不计费用，只计其资金占用。运营工资不含另列的逐件打包人工。全店费用以全店加权结算单位分摊，再乘SKU权重。</p><p>国际物流和海外尾程由谁承担须查当前合同，不因研究德国市场就自动计入商家成本；有实际转嫁费用时需补录。补贴、赔付或EPR退费未证实时不自动增加利润。实际每单位账单可替换对应准备，不与准备叠加。</p><h3>基准与保守情景</h3><p>保守情景：采购+10%，其余正向成本及操作人工+20%；退款/退回/扣款事件率和售前损耗率×2（上限95%）；分摊数量下降30%；资金周期×1.5。它是压力测试，不是行业均值、统计置信区间或销量预测。</p><h3>所有默认输入可调整</h3><p>下表除25%一般企业所得税情景有法定一般税率参考外，数值均是内部预算估值。费用类别有文档出处不代表文档公布了这些默认数值。小微税率条件未知，不自动套用5%。无发票抵扣资料时默认1%的间接税净负担仅为估值。</p><div class="table-wrap"><table><thead><tr><th>参数</th><th>默认预算</th><th>口径</th></tr></thead><tbody>{items}</tbody></table></div><h3>规则来源</h3>{refs}</section><p><a href="/">返回工作台</a></p></main></html>'''
    (ROOT/'app/frontend/static/profit-method.html').write_text(html,encoding='utf-8')

def main():
    registry=ROOT/'research/sources.json'
    data=json.loads(registry.read_text(encoding='utf-8')); ids={r['id'] for r in data['sources']}
    data['sources'].extend(r for r in references() if r['id'] not in ids)
    registry.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    method_page()
    with ThreadPoolExecutor(max_workers=4) as executor:captured=dict(executor.map(capture,PRODUCTS))
    (OUT/'public-captures.json').write_text(json.dumps(captured,ensure_ascii=False,indent=2),encoding='utf-8')
    store=SQLiteStore(ROOT/'data/workbench.db');store.backup(ROOT/'data/backups/before-profit-catalog-20261123.db')
    svc=WorkbenchService(store)
    created=[]
    for p in PRODUCTS:
        src,cand=build_records(p,captured[p['id']])
        if not store.get_record('source',src['id']): assert svc.save_source(src)==[]
        if not store.get_record('candidate',cand['id']):
            errors=svc.save_candidate(cand,reviewer='profit-catalog');assert errors==[],errors
            created.append(cand['id'])
    first=store.get_record('candidate',case.CASE_ID)
    for sku in first['skus']:
        sku.setdefault('profit_plan',{'version':profit_model.VERSION,'currency':'CNY','inputs':{},'value_basis':'budget_assumptions'})
    first.setdefault('provenance',{})['profit']={'reference':'PROFIT-ASSUMPTIONS','origin':'scenario_assumption','scope':'完整利润新增费用预算；旧售后汇总0.60不再重复加入'}
    assert svc.save_candidate(first,reviewer='profit-model-upgrade')==[]
    summary=[{'id':c['id'],'title':c['title'],'items':[{k:x[k] for k in ('sku','baseline','conservative')} for x in c['profit_summaries']]} for c in svc.list_candidates() if c['profit_summaries']]
    (OUT/'catalog-results.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'created':created,'products':len(summary),'results':[{'title':c['title'],'base_net':c['items'][0]['baseline']['net_profit'],'stress_net':c['items'][0]['conservative']['net_profit'],'full_cost':c['items'][0]['baseline']['total_cost']} for c in summary]},ensure_ascii=False))
    store.close()

if __name__=='__main__':main()
