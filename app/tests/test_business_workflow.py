"""Regressions from the independent audit, including price shocks and data loss."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from app.backend.adapters.storage_sqlite import SQLiteStore
from app.backend.adapters.extraction_rules import RuleExtractor
from app.backend.application.services import WorkbenchService
from app.backend.domain import models, evidence
from app.backend.domain.ports import ExtractRequest
from app.backend.domain.ports import AdapterResult
import importlib.util
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('business_case',ROOT/'scripts/prepare-business-case.py')
case=importlib.util.module_from_spec(spec)
spec.loader.exec_module(case)


class BusinessWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.stores=[]
        self.svc=self.service('main')
        self.source,self.candidate,self.policy=case.case_records()
        self.assertEqual(self.svc.save_source(self.source),[])
        self.assertEqual(self.svc.save_policy(self.policy),[])
        self.assertEqual(self.svc.save_candidate(self.candidate),[])

    def service(self,name):
        store=SQLiteStore(Path(self.tmp.name)/(name+'.db'))
        self.stores.append(store)
        return WorkbenchService(store)

    def tearDown(self):
        for s in self.stores: s.close()
        self.tmp.cleanup()

    def test_buyer_price_drives_summary_without_overwriting_offer(self):
        self.assertEqual(self.svc.add_feedback(case.feedback('20.00',1))['status'],'succeeded')
        detail=self.svc.get_candidate(case.CASE_ID)
        view=detail['skus'][0]
        self.assertEqual(view['sku']['supply_income']['amount'],'24.00')
        self.assertEqual(view['active_evaluation']['status'],'BELOW_THRESHOLD')
        self.assertEqual(view['active_evaluation']['values']['minimum_supply_income'],'20.84')
        self.assertIn('低于',self.svc.list_candidates()[0]['next_action'])
        self.assertEqual(self.svc.list_candidates()[0]['finance_statuses'],['BELOW_THRESHOLD'])

    def test_loss_is_visible_even_before_price_verification(self):
        fb=case.feedback('12.00',1)
        fb['verification']='draft'
        self.svc.add_feedback(fb)
        detail=self.svc.get_candidate(case.CASE_ID)
        self.assertEqual(detail['skus'][0]['active_evaluation']['status'],'NEEDS_DATA_CONFIRMATION')
        self.assertIn('亏损',self.svc.next_action(detail['candidate'],detail['skus']))

    def test_missing_specs_are_unknown_not_comparable(self):
        result=evidence.assess_comparability(self.candidate,{'id':'EMPTY'})
        self.assertFalse(result['comparable'])
        self.assertEqual(result['status'],'insufficient')

    def test_comparability_checks_every_sku(self):
        second=copy.deepcopy(self.candidate['skus'][0])
        second['merchant_sku']='OTHER'
        second['pack_composition'][0]['product_dimensions_cm']=['99','7','5.5']
        self.candidate['skus'].append(second)
        self.assertEqual(self.svc.save_candidate(self.candidate),[])
        detail=self.svc.get_candidate(case.CASE_ID)
        self.assertEqual([c['comparable'] for c in detail['evidence'][0]['sku_comparisons']],[True,False])
        self.assertFalse(next(r for r in detail['readiness'] if r['key']=='market_evidence')['ok'])

    def test_gross_less_than_net_rejected(self):
        self.candidate['skus'][0]['specs']['weight']['gross_weight_g']='300'
        self.assertTrue(self.svc.save_candidate(self.candidate))

    def test_composition_total_must_match_sales_pieces(self):
        self.candidate['skus'][0]['pack_composition'][0]['count']=5
        self.assertTrue(self.svc.save_candidate(self.candidate))

    def test_duplicate_merchant_skus_rejected(self):
        self.candidate['skus'].append(copy.deepcopy(self.candidate['skus'][0]))
        self.assertTrue(self.svc.save_candidate(self.candidate))

    def test_foreign_json_bundle_does_not_write_any_record(self):
        dst=self.service('foreign')
        report=dst.import_bundle('json',json.dumps({'schema_version':'other','records':{'candidates':[self.candidate]}}))
        self.assertTrue(report['errors'])
        self.assertEqual(report['imported'],[])
        self.assertEqual(dst.list_candidates(),[])

    def test_csv_preserves_all_product_and_sku_fields(self):
        self.candidate['skus'][0]['sale_spec_bindings'][0].update(parent_spec_id='90071992547409931234',spec_id='90071992547409939876')
        self.svc.save_candidate(self.candidate)
        dst=self.service('csv')
        report=dst.import_bundle('csv',self.svc.export_bundle('csv')['content'])
        self.assertEqual(report['errors'],[])
        self.assertEqual(dst.store.get_record('candidate',case.CASE_ID),self.candidate)

    def test_invalid_pieces_does_not_silently_become_one(self):
        from app.backend.adapters import exporter_internal as ex
        rows=ex.candidates_to_csv_rows([self.candidate])
        rows[0]['pieces']='invalid'
        dst=self.service('badpieces')
        report=dst.import_bundle('csv',ex.write_csv(rows))
        self.assertTrue(report['errors'])
        self.assertEqual(report['imported'],[])

    def test_multi_sku_buyer_price_requires_specific_sku(self):
        second=copy.deepcopy(self.candidate['skus'][0]); second['merchant_sku']='OTHER'
        self.candidate['skus'].append(second); self.svc.save_candidate(self.candidate)
        fb=case.feedback('20.00',1); fb.pop('sku_ref')
        self.assertEqual(self.svc.add_feedback(fb)['status'],'failed')

    def test_only_explicit_product_metadata_is_used_for_prices(self):
        path=Path(self.tmp.name)/'product.html'
        path.write_text('<title>Box</title><script>var noise="EUR 500";</script><script type="application/ld+json">'+
            json.dumps({'@type':'Product','offers':{'@type':'Offer','price':'13.99','priceCurrency':'EUR'}})+'</script>',encoding='utf-8')
        result=RuleExtractor().extract(ExtractRequest('test',str(path),('title','display_price')))
        self.assertEqual(result.payload['fields']['display_price']['value'],'13.99')

    def test_noise_price_does_not_become_product_price(self):
        path=Path(self.tmp.name)/'noise.html'
        path.write_text('<title>Box</title><script>var noise="EUR 500";</script>',encoding='utf-8')
        result=RuleExtractor().extract(ExtractRequest('test',str(path),('title','display_price')))
        self.assertNotIn('display_price',result.payload['fields'])

    def test_invalid_backup_does_not_replace_current_data(self):
        path=Path(self.tmp.name)/'invalid.db'; path.write_text('not a database')
        self.assertTrue(self.svc.restore(str(path)))
        self.assertIsNotNone(self.svc.get_candidate(case.CASE_ID))

    def test_submission_contains_costs_layers_and_buyer_price(self):
        self.svc.add_feedback(case.feedback('20.00',1))
        package=self.svc.build_submission(case.CASE_ID)['package']
        sku=package['skus'][0]
        self.assertEqual(sku['specs']['item']['weight']['net_weight_g'],'60')
        self.assertEqual(sku['specs']['package']['weight']['gross_weight_g'],'420')
        self.assertEqual(len(sku['costs']),5)
        self.assertEqual(sku['buyer_supply_income']['amount'],'20.00')
        self.assertEqual(sku['active_evaluation']['status'],'BELOW_THRESHOLD')

    def test_collected_page_links_to_candidate_but_price_stays_unconfirmed(self):
        path=Path(self.tmp.name)/'collected.html'
        path.write_text('<title>Drawer box</title><script type="application/ld+json">'+json.dumps({
            '@type':'Product','offers':{'price':'13.99','priceCurrency':'EUR'}})+'</script>',encoding='utf-8')
        class Collector:
            def collect(self,request):
                return AdapterResult('succeeded',payload={'file_path':str(path),'snapshot_ref':'test-snapshot','sha256':'test-sha','title':'Drawer box'})
        self.svc.collector=Collector()
        self.svc.rule_extractor=RuleExtractor()
        result=self.svc.collect_page('linked','https://example.com/item',('example.com',),case.CASE_ID)
        self.assertEqual(result.status,'succeeded')
        stored=self.svc.store.get_record('source','WEB-linked')
        self.assertEqual(stored['facts']['extracted_candidates']['display_price']['value'],'13.99')
        self.assertNotIn('display_price',stored['facts'])
        self.assertIn('WEB-linked',self.svc.store.get_record('candidate',case.CASE_ID)['evidence_refs'])
        self.assertEqual(evidence.assess_comparability(self.candidate,stored)['status'],'insufficient')

    def test_inconsistent_template_id_does_not_mark_template_ready(self):
        self.candidate['template_binding']['category_id']='provided-but-unverified'
        self.svc.save_candidate(self.candidate)
        detail=self.svc.get_candidate(case.CASE_ID)
        self.assertFalse(next(r for r in detail['readiness'] if r['key']=='template')['ok'])
        self.assertTrue(self.svc.build_fill_plan(case.CASE_ID)['plan']['blocking'])

    def test_material_readiness_uses_sourced_task_requirements(self):
        self.candidate['materials']={k:True for k in ('supplier','photos','measure','compliance','template','sample')}
        self.svc.save_candidate(self.candidate)
        detail=self.svc.get_candidate(case.CASE_ID)
        self.assertFalse(next(r for r in detail['readiness'] if r['key']=='materials')['ok'])
        self.candidate['material_requirements']={'required':['photos','measure'],'source_ref':'casebook:TASK-001','confirmed':True}
        self.svc.save_candidate(self.candidate)
        detail=self.svc.get_candidate(case.CASE_ID)
        self.assertTrue(next(r for r in detail['readiness'] if r['key']=='materials')['ok'])

    def test_supplier_numbers_alone_do_not_mark_supply_verified(self):
        self.candidate['supplier']={'url':'https://example.com/supplier','moq':100,'lead_days':0}
        self.svc.save_candidate(self.candidate)
        detail=self.svc.get_candidate(case.CASE_ID)
        self.assertFalse(next(r for r in detail['readiness'] if r['key']=='supplier')['ok'])
        self.candidate['supplier'].update(confirmed=True,source_ref='casebook:QUOTE-001')
        self.svc.save_candidate(self.candidate)
        detail=self.svc.get_candidate(case.CASE_ID)
        self.assertTrue(next(r for r in detail['readiness'] if r['key']=='supplier')['ok'])
