"""Full-managed supplier unit economics, independent of UI/storage/platform APIs.

Basis: one sales unit initially eligible for supply settlement. Post-settlement
clawbacks remain an explicit risk. Estimates never become actual ledger profit.
All operations use Decimal; display rows retain four decimals for reconciliation.
"""
from __future__ import annotations
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP, localcontext

VERSION='full-cost/2.0'
INTERNAL='PROFIT-ASSUMPTIONS'
FINANCE='MIAO-FULL-FINANCE'
FIELDS=[
    ('labor','pack_labor','打包与操作人工','0.35','元/销售单位',INTERNAL,'只计操作人工；包材金额不含此项'),
    ('fulfillment','platform_warehouse','平台仓储综合服务','0.25','元/销售单位','DXM-FINANCE','按当前账单替换；不重复计揽收、退回、贴标'),
    ('risk','pre_sale_loss_percent','售前拒收/滞销核销率','2','%',INTERNAL,'互斥的未形成正常结算货物；按损耗率/(1-损耗率)摊入正常结算单位'),
    ('risk','pre_sale_recovery_percent','售前损耗货物采购成本回收比例','20','%',INTERNAL,'仅冲回损耗货物的采购价值，不冲回已花包材和正向运费'),
    ('risk','refund_percent','商家承担退款/追缴率','2','%名义供货收入',FINANCE,'并非消费者总退货率；只计最终由本商家承担的供货收入冲减'),
    ('risk','refund_subsidy_percent','退款中平台补贴覆盖比例','0','%退款额',FINANCE,'无已证实非商家责任补贴时按0；不可将总退款和商家责任退款重复计'),
    ('risk','refund_stock_recovery_percent','退款商品可回收采购价值比例','0','%采购成本',INTERNAL,'默认不确认残值；成本已计一次，不能再扣一遍货值损失'),
    ('risk','return_percent','国内退回服务触发率','3','%结算单位',FINANCE,'仅用于逆向运费/分拣/重包，不另重复扣商品成本'),
    ('risk','return_freight','每次国内退回运费','4','元/次',FINANCE,'估算的商家承担金额；真实线路/分摊以履约服务账单为准'),
    ('risk','return_handling','每次退回分拣操作','1','元/次',FINANCE,'不与退回运费或仓储综合费中的相同费用重复'),
    ('risk','return_repack','每次退回重新包装','0.50','元/次',INTERNAL,'只计退回后新增包材'),
    ('risk','delay_percent','备货时效扣款事件率','0.5','%结算单位',FINANCE,'概率和金额均为预算输入，不是平台公布的统一罚则'),
    ('risk','delay_charge','每次备货时效扣款估值','10','元/次',FINANCE,'待买手任务和本店账单替换'),
    ('risk','quality_percent','质量事故扣款事件率','0.3','%结算单位',FINANCE,'与售后退款货款冲减分开；同一笔账单不可重复归类'),
    ('risk','quality_charge','每次质量事故扣款估值','25','元/次',FINANCE,'不是官方金额；按本店历史实际损失修订'),
    ('risk','claim_percent','额外售后赔付事件率','1','%结算单位',FINANCE,'只计退款以外的额外赔付'),
    ('risk','claim_charge','每次额外售后赔付估值','3','元/次',FINANCE,'不得把已包含退款的赔付额再全额加入'),
    ('fulfillment','relabel_percent','平台补贴标触发率','2','%结算单位',FINANCE,'包材已含日常自贴标签；这里只计额外平台贴标服务'),
    ('fulfillment','relabel_charge','每次额外贴标费用','1','元/次',FINANCE,'实际收费按账单确认'),
    ('fulfillment','epr','EPR及合规代扣预留','0.15','元/销售单位',FINANCE,'欧区部分产品可能涉及；非德国统一费率，按本店责任与账单替换'),
    ('fulfillment','platform_fee_percent','其他平台扣费预留','0.5','%名义供货收入',INTERNAL,'仅未在明细中列明的费用；逐笔分配后应减少此预留'),
    ('fulfillment','fx_percent','收款换汇费用','0','%名义供货收入',INTERNAL,'本轮人民币同币种结算假定不发生；外币结算须按银行费率调整'),
    ('income','shipping_subsidy','已核实运费补贴预算','0','元/销售单位',FINANCE,'未证实先按0；仅原正向运费填全额时冲回，若运费已填商家净承担额则不重复增加'),
    ('income','epr_refund','已核实EPR退费预算','0','元/销售单位',FINANCE,'未证实先按0；EPR费用若已按扣费减退费的净额填写，则此处留0'),
    ('income','other_income','其他可核对补贴/赔付收入','0','元/销售单位',FINANCE,'只计未在退款补贴、运费补贴及EPR退费重复登记的收入'),
    ('allocation','salary_monthly','全店月运营人工（含用工附加）','18000','元/月',INTERNAL,'已含运营人员工资和用工附加；不含另列的逐件打包人工'),
    ('allocation','rent_monthly','全店自有仓库租赁及水电','5000','元/月',INTERNAL,'自有仓库费用，与平台仓储服务区分'),
    ('allocation','software_monthly','全店软件与管理费用','500','元/月',INTERNAL,'ERP/耗材管理等固定费用，不重复计入其他变动费'),
    ('allocation','company_weighted_units','全店预计月加权结算销售单位','30000','加权销售单位/月',INTERNAL,'不是销量观察；分母须覆盖全店成本承载量，不能重复把全店费用摊给每个SKU'),
    ('allocation','sku_weight','本SKU固定费用分摊权重','1','倍',INTERNAL,'可按占用工时/体积调整；全店分母也必须采用相同权重口径'),
    ('allocation','launch_cost','本SKU打样/拍摄/检测等一次性费用','400','元',INTERNAL,'样品、设计、拍摄、检测、模具等按本SKU归集一次，不计商品备货货值'),
    ('allocation','lifetime_units','一次性费用预计摊销单位','3000','销售单位',INTERNAL,'按预计可形成结算的生命周期数量，不把未售库存直接当利润'),
    ('capital','batch_units','首批备货销售单位','1000','销售单位',INTERNAL,'用于资金占用和保证金分摊，不代表真实订单或市场销量'),
    ('capital','deposit','本SKU分配的保证金本金','1000','元',INTERNAL,'不是平台统一保证金金额；可退本金不计费用，只计其资金占用'),
    ('capital','cash_days','资金占用周期','60','天',INTERNAL,'生产/入仓/售卖/妥投/售后及结算过程综合估值，不是平台固定账期'),
    ('capital','annual_finance_percent','资金年化成本','8','%/年',INTERNAL,'资金机会成本估值，非实际贷款报价；一年按365天'),
    ('tax','indirect_tax_percent','间接税抵扣后净负担预留','1','%名义供货收入',INTERNAL,'不是法定增值税税率；含税现金口径下的净税费准备，发票/抵扣/出口退税待核'),
    ('tax','income_tax_percent','企业所得税测算比例','25','%正税前收益','CN-CIT','默认一般企业情景；资质未知不自动套用小微5%优惠；非税务申报计算'),
    ('tax','tax_addback','所得税纳税调增预算','0','元/销售单位','CN-CIT','未核实的年度纳税调整；不能自动把平台合同赔付等同于行政罚款，需按实际扣除口径补入'),
    ('target','target_net_margin_percent','税后净收益率目标','15','%名义供货价',INTERNAL,'内部测算目标；与原五项收入贡献率门槛分开'),
]
SCHEMA=[dict(group=g,key=k,label=l,default=d,unit=u,source_id=s,value_source_id='CN-CIT' if k=='income_tax_percent' else INTERNAL,note=n) for g,k,l,d,u,s,n in FIELDS]
DEFAULTS={f['key']:f['default'] for f in SCHEMA}
RATE_KEYS={f['key'] for f in SCHEMA if '%' in f['unit']}
GROUPS={'direct':'商品与正向履约','risk':'退款退回与风险','fulfillment':'平台服务与收款','allocation':'运营与开发分摊','capital':'资金占用','tax':'税费准备'}
ACTUAL_KEYS={'refunds','refund_subsidy','refund_recovery','stock_loss','return_services','delay','quality','claim','platform_warehouse','relabel','epr','platform_fee','fx','indirect_tax','shipping_subsidy','epr_refund','other_income'}

def q(value, digits='0.0001'):
    return str(value.quantize(Decimal(digits),rounding=ROUND_HALF_UP))

def parse_inputs(plan):
    values={}
    for key,default in DEFAULTS.items():
        raw=(plan.get('inputs') or {}).get(key,default)
        if raw is None or raw=='': raise ValueError(f'{key}: 未知值不能自动当0')
        try: x=Decimal(str(raw))
        except InvalidOperation: raise ValueError(f'{key}: 数值无效')
        if not x.is_finite() or x<0 or len(str(raw))>24: raise ValueError(f'{key}: 需有限非负数值')
        if key in RATE_KEYS and x>100: raise ValueError(f'{key}: 百分比不能超过100')
        values[key]=x
    for key in ('company_weighted_units','lifetime_units','batch_units'):
        if values[key]<=0: raise ValueError(f'{key}: 分摊数量必须大于0')
    if values['pre_sale_loss_percent']>=100 or values['target_net_margin_percent']>=100:
        raise ValueError('核销率和净收益目标必须小于100%')
    return values

def validate_plan(plan):
    if not isinstance(plan,dict): return ['profit_plan: object required']
    try:
        if plan.get('version',VERSION)!=VERSION: raise ValueError('未知完整利润模型版本')
        if not isinstance(plan.get('inputs') or {},dict):raise ValueError('inputs 必须为对象')
        unknown=set(plan.get('inputs') or {})-set(DEFAULTS)
        if unknown:raise ValueError('未知参数：'+','.join(sorted(unknown)))
        parse_inputs(plan)
        if not isinstance(plan.get('actual_costs') or {},dict):raise ValueError('actual_costs 必须为对象')
        for key,item in (plan.get('actual_costs') or {}).items():
            if key not in ACTUAL_KEYS: raise ValueError(f'actual_costs.{key}: 不支持的账单替换项；商品成本请改原始成本输入')
            if not isinstance(item,dict) or not item.get('source_ref'):
                raise ValueError(f'actual_costs.{key}: 实际账单替换必须有来源')
            value=Decimal(str(item.get('amount')))
            if not value.is_finite() or value<0: raise ValueError(f'actual_costs.{key}: 非负金额 required')
    except (ValueError,InvalidOperation,TypeError) as exc: return [f'profit_plan: {exc}']
    return []

def stress_inputs(base):
    v=base.copy()
    for key in ('refund_percent','return_percent','delay_percent','quality_percent','claim_percent'):
        v[key]=min(v[key]*2,Decimal(95))
    v['pre_sale_loss_percent']=min(v['pre_sale_loss_percent']*2,Decimal(95))
    v['company_weighted_units']=v['company_weighted_units']*Decimal('.70')
    v['lifetime_units']=v['lifetime_units']*Decimal('.70')
    v['cash_days']=v['cash_days']*Decimal('1.5')
    return v

def scenario(price,sku,v,plan,stress=False):
    costs={c['key']:c['money'] for c in sku.get('costs') or []}
    p=Decimal(str(price['amount']))
    rows=[]
    actuals=plan.get('actual_costs') or {}
    def add(key,label,group,value,formula,source=INTERNAL,credit=False):
        kind='estimate'
        actual=actuals.get(key)
        if actual:
            if actual.get('currency',price['currency'])!=price['currency'] or actual.get('sales_unit',sku['sales_unit'])!=sku['sales_unit']:
                raise ValueError(f'{key}: 实际账单币种/销售单位不一致')
            value=Decimal(str(actual['amount']))*(-1 if credit else 1)
            formula='以实际每销售单位账单金额替换准备，不叠加'
            source=actual['source_ref'];kind='actual'
        rows.append({'key':key,'label':label,'group':group,'amount':q(value),'formula':formula,'source_id':source,
                     'value_source_id':source if actual else INTERNAL,'kind':kind})
        return value
    def rate(k): return v[k]/100
    direct={}
    for key,label in [('purchase','商品采购'),('packaging','包装耗材'),('logistics','国内正向运费/揽收'),('other_variable','入库/验货等其他变动费')]:
        m=costs.get(key) or {}
        if m.get('amount') in (None,''): raise ValueError(f'{key}: 缺少原始成本')
        if m.get('currency')!=price['currency'] or m.get('sales_unit')!=sku['sales_unit']: raise ValueError('原始成本币种/单位不一致')
        value=Decimal(str(m['amount']))
        if stress: value*=Decimal('1.10') if key=='purchase' else Decimal('1.20')
        direct[key]=value
        add(key,label,'direct',value,'录入每销售单位成本'+('；保守采购+10%/其他正向费+20%' if stress else ''),m.get('source_ref') or INTERNAL)
        rows[-1]['kind']='recorded' if m.get('confirmed') else 'estimate'
    labor=v['pack_labor']*(Decimal('1.20') if stress else 1)
    add('pack_labor','打包与仓库操作人工','direct',labor,'每销售单位操作人工；与包材分开')
    refund_charge=add('refunds','商家责任退款/货款追缴','risk',p*rate('refund_percent'),f'{q(p)} × {v["refund_percent"]}%',FINANCE)
    add('refund_subsidy','非商家责任补贴冲回','risk',-refund_charge*rate('refund_subsidy_percent'),'退款金额 × 已假定补贴覆盖比例',FINANCE,True)
    add('refund_recovery','退款商品可回收价值冲回','risk',-direct['purchase']*rate('refund_percent')*rate('refund_stock_recovery_percent'),'采购成本 × 退款率 × 可回收价值比例；商品成本不重复扣除',INTERNAL,True)
    loss=rate('pre_sale_loss_percent')
    wasted=loss/(1-loss)*(direct['purchase']*(1-rate('pre_sale_recovery_percent'))+direct['packaging']+direct['logistics']+direct['other_variable'])
    add('stock_loss','售前拒收/滞销核销分摊','risk',wasted,
        f'{v["pre_sale_loss_percent"]}%/(1-{v["pre_sale_loss_percent"]}%) × [{q(direct["purchase"])}×(1-{v["pre_sale_recovery_percent"]}%)+{q(direct["packaging"])}+{q(direct["logistics"])}+{q(direct["other_variable"])}]')
    reverse=rate('return_percent')*(v['return_freight']+v['return_handling']+v['return_repack'])
    add('return_services','退回运费/分拣/重新包装','risk',reverse,f'{v["return_percent"]}% × ({v["return_freight"]}+{v["return_handling"]}+{v["return_repack"]})',FINANCE)
    for key,label in [('delay','备货时效扣款准备'),('quality','质量事故扣款准备'),('claim','额外售后赔付准备')]:
        add(key,label,'risk',rate(key+'_percent')*v[key+'_charge'],f'{v[key+"_percent"]}% × {v[key+"_charge"]}元/次',FINANCE)
    add('platform_warehouse','平台仓储综合服务','fulfillment',v['platform_warehouse'],'每销售单位服务预算；不含重复揽收/退回/贴标','DXM-FINANCE')
    add('relabel','额外平台贴标服务','fulfillment',rate('relabel_percent')*v['relabel_charge'],f'{v["relabel_percent"]}% × {v["relabel_charge"]}元/次',FINANCE)
    add('epr','EPR及合规代扣预留','fulfillment',v['epr'],'本店/本品责任未核，按每销售单位预算；非统一费率',FINANCE)
    add('platform_fee','其他平台扣费预留','fulfillment',p*rate('platform_fee_percent'),f'{q(p)} × {v["platform_fee_percent"]}%（只计未分类部分）')
    add('fx','收款/换汇成本','fulfillment',p*rate('fx_percent'),f'{q(p)} × {v["fx_percent"]}%（本轮人民币同币种假定0）')
    for key,label in [('shipping_subsidy','运费补贴冲回'),('epr_refund','EPR退费冲回'),('other_income','其他补贴/赔付冲回')]:
        add(key,label,'fulfillment',-v[key],'每销售单位可核对收入；未证实先按0，不与净额账单重复',FINANCE,True)
    for key,label in [('salary_monthly','运营人工分摊'),('rent_monthly','自有仓库租赁水电分摊'),('software_monthly','软件管理费用分摊')]:
        add(key,label,'allocation',v[key]/v['company_weighted_units']*v['sku_weight'],f'{v[key]} / {v["company_weighted_units"]} × 权重{v["sku_weight"]}')
    add('launch','打样/拍摄/检测/开发摊销','allocation',v['launch_cost']/v['lifetime_units'],f'{v["launch_cost"]} / {v["lifetime_units"]}个预计生命周期结算单位')
    cash=sum(direct.values())+labor
    finance=(cash+v['deposit']/v['batch_units'])*rate('annual_finance_percent')*v['cash_days']/365
    add('finance','备货及保证金资金占用','capital',finance,f'({q(cash)} + {v["deposit"]}/{v["batch_units"]}) × {v["annual_finance_percent"]}% × {v["cash_days"]}/365；保证金本金不计费用')
    add('indirect_tax','间接税净负担预留','tax',p*rate('indirect_tax_percent'),f'{q(p)} × {v["indirect_tax_percent"]}%；此参数不是法定增值税税率')
    # Totals deliberately sum the same 4-decimal ledger values the reader sees.
    before_cost=sum((Decimal(r['amount']) for r in rows),Decimal(0))
    before_tax=p-before_cost
    income_tax=max(before_tax+v['tax_addback'],Decimal(0))*rate('income_tax_percent')
    add('income_tax','企业所得税测算','tax',income_tax,f'max(税前净收益{q(before_tax)}+调增{v["tax_addback"]},0) × {v["income_tax_percent"]}%；仅情景，不代替年度申报','CN-CIT')
    total=sum((Decimal(r['amount']) for r in rows),Decimal(0))
    net=p-total
    groups={key:sum((Decimal(r['amount']) for r in rows if r['group']==key),Decimal(0)) for key in GROUPS}
    target=rate('target_net_margin_percent')
    return {'price':q(p),'currency':price['currency'],'sales_unit':sku['sales_unit'],'total_cost':q(total),
        'cost_before_income_tax':q(before_cost),'profit_before_income_tax':q(before_tax),'income_tax':q(income_tax),
        'net_profit':q(net),'net_margin':str(net/p) if p else None,'target_percent':str(v['target_net_margin_percent']),
        'meets_target':net>=p*target,'groups':[{'key':k,'label':GROUPS[k],'amount':q(groups[k])} for k in GROUPS],
        'rows':rows,'initial_cash_required':q(cash*v['batch_units']+v['deposit']+v['launch_cost']),
        'allocation_inputs':{k:str(v[k]) for k in ('company_weighted_units','sku_weight','lifetime_units','batch_units','cash_days')},
        'status':'LOSS' if net<0 else ('MEETS_TARGET' if net>=p*target else 'BELOW_TARGET')}

def minimum_price(price,sku,v,plan,stress,target):
    # Monotone bisection also handles actual-cost overrides and the tax zero boundary.
    def passes(p):
        result=scenario({**price,'amount':str(p)},sku,v,plan,stress)
        return Decimal(result['net_profit'])>=p*target
    lo,hi=Decimal('.01'),max(Decimal(price['amount'])*2,Decimal(10))
    for _ in range(25):
        if passes(hi):break
        hi*=2
    else:return None
    for _ in range(70):
        mid=(lo+hi)/2
        if passes(mid):hi=mid
        else:lo=mid
    answer=hi.quantize(Decimal('.01'),rounding=ROUND_CEILING)
    while not passes(answer): answer+=Decimal('.01')
    return str(answer)

def evaluate_full(price,sku):
    plan=sku.get('profit_plan')
    if not plan:return None
    errors=validate_plan(plan)
    if errors:return {'status':'INVALID_INPUT','errors':errors,'scenarios':{}}
    try:
        if Decimal(str(price.get('amount') or 0))<=0:raise ValueError('供货价需大于0')
        if plan.get('currency','CNY') != price.get('currency'):
            raise ValueError('完整预算参数币种与供货币种不同，需核对币种并重新估值')
        with localcontext() as ctx:
            ctx.prec=40
            v=parse_inputs(plan)
            scenarios={}
            for name,stress in [('baseline',False),('conservative',True)]:
                inputs=stress_inputs(v) if stress else v
                result=scenario(price,sku,inputs,plan,stress)
                result['break_even_price']=minimum_price(price,sku,inputs,plan,stress,Decimal(0))
                result['target_price']=minimum_price(price,sku,inputs,plan,stress,inputs['target_net_margin_percent']/100)
                current=Decimal(price['amount'])
                result['sensitivity']=[{'price':str((current*Decimal(i)/10).quantize(Decimal('.01'))),
                    'net_profit':scenario({**price,'amount':str(current*Decimal(i)/10)},sku,inputs,plan,stress)['net_profit']} for i in range(6,15)]
                scenarios[name]=result
            return {'version':VERSION,'status':'ESTIMATE','scenarios':scenarios,
                'assumptions':SCHEMA,'inputs':{k:str(x) for k,x in v.items()},
                'scope':'每个初次正常形成供货结算的销售单位；含税现金收支及分摊口径；不是已实现账面净利润',
                'notes':['旧版 expected_after_sales 汇总准备由明细风险替代，不再重复加入。',
                    '退款已冲减收入，原商品成本不重复扣；只有售前未结算损耗额外分摊。',
                    '国际干线、海外仓尾程与消费者零售价不默认归入本商家；合同额外转嫁时须补入实际费用。',
                    '所得税与间接税净负担为测算，纳税主体、进项抵扣、出口及年度调整未核。',
                    '基准与保守是参数情景，不是统计置信区间；零值项有明确本轮假定，并非默认没有风险。',
                    '每行保留4位小数，合计使用同一明细；表头按分显示。']}
    except (ValueError,InvalidOperation,TypeError,KeyError) as exc:
        return {'status':'INVALID_INPUT','errors':[str(exc)],'scenarios':{}}
