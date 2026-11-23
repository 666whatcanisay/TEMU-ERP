"""Create a traceable product case and exercise the full LOCAL business flow.

Public competitor facts and assumed procurement/buyer inputs remain separate in
provenance. No platform request is made. Existing records are not overwritten.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import urllib.request
from app.backend.application.services import WorkbenchService
from app.backend.adapters.storage_sqlite import SQLiteStore
from app.backend.adapters.extraction_rules import RuleExtractor
from app.backend.domain.ports import ExtractRequest
from app.backend.domain.models import empty_sku

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/business-flow-20261123'
OUT.mkdir(parents=True,exist_ok=True)
URL='https://relaxdays.de/produkte/haushaltsprodukte/verstauen-sortieren/schubladen-organizer/6-teiliges-schubladen-ordnungssystem-10048750.html'
CASE_ID='DE-DRAWER-006'

def case_records():
    source={'record_type':'source','id':'RELAXDAYS-DE-10048750','level':'market_observation',
        'title':'Relaxdays 六件套抽屉分隔盒 · 德国市场观察','publisher':'Relaxdays GmbH','url':URL,
        'locator':'商品 10048750；产品详情 H×B×T 5.5×12×7 cm、每件约60g、6件套；价格区13.99 EUR',
        'scope':{'country':'DE','pieces':6,'product_dimensions_cm':['12','7','5.5'],'material':'plastic','display_unit':'6 piece set'},
        'observed_at':'2026-11-23','verification':'public_body_reviewed',
        'facts':{'display_price':'13.99','currency':'EUR','tax_included':True,'shipping_condition':'DE free shipping per page',
            'material':'plastic','color':'brown','item_weight_g':'60','retailer_item_id':'10048750','sales':None},
        'note':'公开商品用于规格与市场背景研究；没有销量证据，不代表本公司货源或可复制其品牌/素材。'}
    capture_file=OUT/'public-capture.json'
    if capture_file.is_file():
        capture=json.loads(capture_file.read_text(encoding='utf-8'))
        if capture.get('status')=='succeeded':
            payload=capture['payload']
            source.update(snapshot_ref=str((ROOT/payload['file_path']).resolve()),sha256=payload['sha256'],retrieved_at='2026-11-23')
            source['facts']['extracted_candidates']=capture['extraction'].get('fields',{})
    sku=empty_sku('ORG-HONEY-BRN-06','ORG-HONEY')
    sku.update(pieces=6,material='plastic',sale_spec_bindings=[{'name':'颜色','value':'棕色','parent_spec_id':None,'spec_id':None,'source_ref':source['id']},
        {'name':'件数','value':'6','parent_spec_id':None,'spec_id':None,'source_ref':source['id']}],
        pack_composition=[{'name':'蜂巢式分隔盒','count':6,'product_dimensions_cm':['12','7','5.5'],'classification':None}])
    sku['specs']={'dimensions':{'length_cm':None,'width_cm':None,'height_cm':None,'unit':'cm'},
        'weight':{'net_weight_g':'360','gross_weight_g':'420','unit':'g'},
        'item':{'dimensions':{'length_cm':'12','width_cm':'7','height_cm':'5.5','unit':'cm'},'weight':{'net_weight_g':'60','gross_weight_g':None,'unit':'g'}},
        'package':{'dimensions':{'length_cm':'25','width_cm':'16','height_cm':'8','unit':'cm'},'weight':{'net_weight_g':'360','gross_weight_g':'420','unit':'g'}}}
    sku['supply_income'].update(amount='24.00',confirmed=True,source_ref='casebook:OFFER-001')
    for item,amount in zip(sku['costs'],['8.40','1.20','1.80','0.60','0.50']):
        item['money'].update(amount=amount,confirmed=True,source_ref='casebook:COST-001/'+item['key'])
    candidate={'record_type':'candidate','id':CASE_ID,'title':'蜂巢式抽屉分隔收纳盒 · 棕色 6 件套',
        'listing_title':'6-Pack Honeycomb Drawer Organizer, Brown Plastic Interlocking Storage Boxes',
        'market_title':'Schubladen-Organizer im 6er-Set, braune Kunststoffboxen',
        'mode_assumption':'fully_managed','mode_confirmed':False,'research_market':'DE','market_currency':'EUR','material':'plastic',
        'platform_product_id':None,'category_path_ids':[], 'template_binding':{'status':'unverified','category_id':None,'source_ref':None},
        'evidence_refs':[source['id']],'internal_decision':'research','decision_history':[], 'synthetic':True,
        'rationale':'德国零售商已有同规格六件套商品，可用于规格与价格背景对账；先评估供货成本与核价空间，销量与实际转化待店铺验证。',
        'advantage':'拟评估棕色六件套、包装紧凑与交期；供货能力和材料报告待供应商确认。',
        'supplier':{'url':None,'moq':500,'lead_days':14,'reference':'casebook:SUPPLIER-001'},
        'materials':{'supplier':False,'photos':False,'measure':False,'compliance':False,'template':False,'sample':False},
        'provenance':{'public_product':{'source_id':source['id'],'url':URL,'fields':['dimensions','pieces','material','item_weight']},
            'costs':{'origin':'scenario_assumption','reference':'casebook:COST-001','scope':'按每套人民币，采购8.40/包装1.20/国内物流1.80/售后准备0.60/其他0.50'},
            'packaging':{'origin':'scenario_assumption','reference':'casebook:PACK-001'},
            'feedback':{'origin':'scenario_assumption','reference':'casebook:PRICING-001..003'},
            'policy':{'origin':'scenario_assumption','reference':'casebook:POLICY-001','scope':'收入贡献率40%，用于内部测算'}},
        'skus':[sku]}
    policy={'record_type':'policy','id':'POLICY-CURRENT','metric':'contribution_margin','threshold_percent':'40','confirmed':True,
        'confirmed_by':'案例测算口径','confirmed_at':'2026-11-23','source_ref':'casebook:POLICY-001','version':'case-policy-40-v1',
        'data_origin':'scenario_assumption'}
    return source,candidate,policy

def feedback(price, seq):
    return {'record_type':'feedback','id':f'FB-CASE-{seq:03d}','candidate_id':CASE_ID,'sku_ref':'ORG-HONEY-BRN-06',
        'platform_stage':'pricing','feedback_date':'2026-11-23','created_at':f'2026-11-23T10:{seq:02d}:00+08:00',
        'feedback_text':f'按每套 {price} 元重新评估供货条件，核对可变成本与可接受底价。',
        'verification':'human_confirmed','evidence_ref':f'casebook:PRICING-{seq:03d}', 'data_origin':'scenario_assumption',
        'buyer_supply_income':{'amount':price,'currency':'CNY','sales_unit':'set','confirmed':True,'source_ref':f'casebook:PRICING-{seq:03d}'}}

def run_flow():
    source,candidate,policy=case_records()
    with tempfile.TemporaryDirectory(dir=OUT,ignore_cleanup_errors=True) as folder:
        store=SQLiteStore(Path(folder)/'flow.db')
        svc=WorkbenchService(store)
        assert svc.save_source(source)==[]
        assert svc.save_policy(policy)==[]
        assert svc.save_candidate(candidate)==[]
        checkpoints=[]
        def check(label, expected):
            detail=svc.get_candidate(CASE_ID)
            view=detail['skus'][0]
            assert view['active_evaluation']['status']==expected, view
            checkpoints.append({'step':label,'evaluation':view['active_evaluation'],
                'next_action':svc.next_action(detail['candidate'],detail['skus']),
                'decision':detail['candidate']['internal_decision']})
        check('录入公开竞品与成本，拟报价24', 'MEETS_THRESHOLD')
        before=svc.build_submission(CASE_ID)
        assert before['status']=='succeeded'
        assert svc.add_feedback(feedback('20.00',1))['status']=='succeeded'
        check('买手价20，低于40%贡献率门槛','BELOW_THRESHOLD')
        assert svc.set_decision(CASE_ID,'paused','核价20低于底价20.84，先议价','case-runner')==[]
        assert svc.add_feedback(feedback('12.00',2))['status']=='succeeded'
        check('压力场景12，贡献为负','BELOW_THRESHOLD')
        assert svc.add_feedback(feedback('21.00',3))['status']=='succeeded'
        assert svc.restore_decision(CASE_ID,'case-runner')==[]
        assert svc.set_decision(CASE_ID,'internal_review','核价21满足经营门槛，转内部评审补资料','case-runner')==[]
        check('重新议价21，恢复内部评审','MEETS_THRESHOLD')
        package=svc.build_submission(CASE_ID)['package']
        assert package['skus'][0]['specs']['package']['weight']['gross_weight_g']=='420'
        for fmt in ('csv','json'):
            destination=SQLiteStore(Path(folder)/(fmt+'.db'))
            imported=WorkbenchService(destination)
            content=svc.export_bundle(fmt)['content']
            report=imported.import_bundle(fmt,json.dumps(content,ensure_ascii=False) if fmt=='json' else content)
            assert report['errors']==[], report
            assert destination.get_record('candidate',CASE_ID)==store.get_record('candidate',CASE_ID)
            destination.close()
        store.backup(OUT/'verified-flow.db')
        final=store.get_record('candidate',CASE_ID)
        store.close()
        reopened=SQLiteStore(OUT/'verified-flow.db')
        assert reopened.get_record('candidate',CASE_ID)==final
        reopened.close()
        (OUT/'checkpoints.json').write_text(json.dumps(checkpoints,ensure_ascii=False,indent=2),encoding='utf-8')
        (OUT/'submission-package.json').write_text(json.dumps(package,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'flow':'passed','checkpoints':len(checkpoints),'csv_and_json':'lossless candidate','backup_reopen':'passed'},ensure_ascii=False))

def install(target:Path, ui_start=False):
    source,candidate,policy=case_records()
    store=SQLiteStore(target)
    svc=WorkbenchService(store)
    if store.get_record('candidate',CASE_ID):
        print('Case already exists; preserved existing record')
        store.close(); return
    if ui_start:
        policy['confirmed']=False
        candidate['skus'][0]['supply_income']['confirmed']=False
        for cost in candidate['skus'][0]['costs']:
            cost['money']['confirmed']=False
    assert svc.save_source(source)==[]
    # Preserve user's existing company policy; case assumptions are only the initial policy.
    current=svc.get_policy()
    if not current or not current.get('confirmed'):
        assert svc.save_policy(policy)==[]
    assert svc.save_candidate(candidate)==[]
    store.close()
    print('Installed case:',CASE_ID)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--install',type=Path)
    parser.add_argument('--ui-start',action='store_true')
    args=parser.parse_args()
    run_flow()
    if args.install:
        install(args.install,args.ui_start)
