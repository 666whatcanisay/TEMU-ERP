import copy
from decimal import Decimal
import importlib.util
from pathlib import Path
import unittest
import tempfile
from app.backend.domain import profit_model as model

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('profit_case',ROOT/'scripts/prepare-business-case.py')
case=importlib.util.module_from_spec(spec);spec.loader.exec_module(case)

class FullProfitTests(unittest.TestCase):
    def setUp(self):
        self.sku=case.case_records()[1]['skus'][0]
        self.sku['profit_plan']={'version':model.VERSION,'currency':'CNY','inputs':{}}
        self.price={'amount':'21.00','currency':'CNY','sales_unit':'set'}

    def base(self,sku=None,price=None):
        result=model.evaluate_full(price or self.price,sku or self.sku)
        self.assertEqual(result['status'],'ESTIMATE',result)
        return result['scenarios']['baseline']

    def test_full_cost_reconciles_exactly_to_displayed_ledger(self):
        b=self.base()
        total=sum(Decimal(r['amount']) for r in b['rows'])
        self.assertEqual(total,Decimal(b['total_cost']))
        self.assertEqual(Decimal(b['price'])-total,Decimal(b['net_profit']))
        self.assertLess(Decimal(b['net_profit']),Decimal('8.50'))
        self.assertEqual(b['net_profit'],'4.4816')

    def test_refund_and_aggregate_after_sales_not_counted_twice(self):
        before=self.base()
        self.sku['costs'][3]['money']['amount']='999.00'
        after=self.base()
        self.assertEqual(before['net_profit'],after['net_profit'])
        refunds=next(r for r in before['rows'] if r['key']=='refunds')
        self.assertEqual(refunds['amount'],'0.4200')

    def test_actual_refund_replaces_reserve(self):
        self.sku['profit_plan']['actual_costs']={'refunds':{'amount':'1.00','source_ref':'invoice:refund','currency':'CNY','sales_unit':'set'}}
        rows=self.base()['rows']
        matched=[r for r in rows if r['key']=='refunds']
        self.assertEqual(len(matched),1)
        self.assertEqual(matched[0]['amount'],'1.0000')
        self.assertEqual(matched[0]['kind'],'actual')

    def test_deposit_principal_is_not_expensed(self):
        a=self.base()
        self.sku['profit_plan']['inputs']['deposit']='2000'
        b=self.base()
        self.assertEqual(Decimal(b['initial_cash_required'])-Decimal(a['initial_cash_required']),Decimal('1000'))
        self.assertLess(Decimal(b['total_cost'])-Decimal(a['total_cost']),Decimal('0.10'))

    def test_company_denominator_allocates_overhead_once(self):
        a=self.base()
        self.sku['profit_plan']['inputs']['company_weighted_units']='15000'
        b=self.base()
        salary=lambda s:Decimal(next(r for r in s['rows'] if r['key']=='salary_monthly')['amount'])
        self.assertEqual(salary(b),salary(a)*2)

    def test_negative_earnings_do_not_receive_negative_income_tax(self):
        b=self.base(price={**self.price,'amount':'5.00'})
        self.assertEqual(b['income_tax'],'0.0000')
        self.assertEqual(b['status'],'LOSS')

    def test_small_enterprise_rate_does_not_apply_automatically(self):
        b=self.base()
        tax=next(r for r in b['rows'] if r['key']=='income_tax')
        self.assertIn('25%',tax['formula'])
        self.sku['profit_plan']['inputs']['income_tax_percent']='5'
        reduced=self.base()
        self.assertGreater(Decimal(reduced['net_profit']),Decimal(b['net_profit']))

    def test_target_floor_passes_and_previous_cent_fails(self):
        b=self.base();floor=Decimal(b['target_price'])
        at=self.base(price={**self.price,'amount':str(floor)})
        below=self.base(price={**self.price,'amount':str(floor-Decimal('.01'))})
        self.assertTrue(at['meets_target'])
        self.assertFalse(below['meets_target'])

    def test_stress_is_parameter_scenario_and_worse_here(self):
        r=model.evaluate_full(self.price,self.sku)['scenarios']
        self.assertLess(Decimal(r['conservative']['net_profit']),Decimal(r['baseline']['net_profit']))
        self.assertEqual(r['conservative']['status'],'BELOW_TARGET')

    def test_unknown_not_zero_and_zero_denominator_rejected(self):
        self.sku['profit_plan']['inputs']['return_freight']=''
        self.assertTrue(model.validate_plan(self.sku['profit_plan']))
        self.sku['profit_plan']['inputs']={'company_weighted_units':'0'}
        self.assertTrue(model.validate_plan(self.sku['profit_plan']))

    def test_currency_mismatch_blocks_budget(self):
        r=model.evaluate_full({**self.price,'currency':'USD'},self.sku)
        self.assertEqual(r['status'],'INVALID_INPUT')

    def test_never_treat_official_fee_categories_as_default_numeric_authority(self):
        default=next(f for f in model.SCHEMA if f['key']=='quality_charge')
        self.assertEqual(default['source_id'],'MIAO-FULL-FINANCE')
        self.assertEqual(default['value_source_id'],'PROFIT-ASSUMPTIONS')

    def test_combined_quote_floor_keeps_both_governed_metrics(self):
        from app.backend.adapters.storage_sqlite import SQLiteStore
        from app.backend.application.services import WorkbenchService
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            store=SQLiteStore(Path(folder)/'svc.db');svc=WorkbenchService(store)
            src,candidate,policy=case.case_records()
            candidate['skus'][0]=self.sku
            svc.save_source(src);svc.save_policy(policy);svc.save_candidate(candidate)
            svc.add_feedback(case.feedback('21.00',1))
            b=svc.get_candidate(case.CASE_ID)['skus'][0]['full_profit']['scenarios']['baseline']
            self.assertEqual(b['target_price'],'18.68')
            self.assertEqual(b['combined_target_price'],'20.84')
            store.close()

    def test_csv_roundtrip_preserves_full_profit_parameters(self):
        from app.backend.adapters.storage_sqlite import SQLiteStore
        from app.backend.application.services import WorkbenchService
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            stores=[SQLiteStore(Path(folder)/(k+'.db')) for k in ('src','dst')]
            src,dst=[WorkbenchService(s) for s in stores]
            candidate=case.case_records()[1];candidate['skus'][0]=self.sku
            self.sku['profit_plan']['inputs']['return_percent']='6'
            src.save_candidate(candidate)
            report=dst.import_bundle('csv',src.export_bundle('csv')['content'])
            self.assertFalse(report['errors'],report)
            self.assertEqual(dst.store.get_record('candidate',case.CASE_ID),candidate)
            for s in stores:s.close()

    def test_unknown_cost_parameters_are_not_silently_ignored(self):
        self.sku['profit_plan']['inputs']['return_pecent']='30'
        self.assertTrue(model.validate_plan(self.sku['profit_plan']))
        self.sku['profit_plan']['inputs']={}
        self.sku['profit_plan']['actual_costs']={'hidden_new_charge':{'amount':'3','source_ref':'invoice:test'}}
        self.assertTrue(model.validate_plan(self.sku['profit_plan']))

    def test_rebates_are_credits_not_second_expenses(self):
        a=self.base()
        self.sku['profit_plan']['inputs'].update(shipping_subsidy='0.20',epr_refund='0.10',other_income='0.30')
        b=self.base()
        self.assertEqual(Decimal(b['net_profit'])-Decimal(a['net_profit']),Decimal('.4500'))
        self.assertEqual(next(r for r in b['rows'] if r['key']=='shipping_subsidy')['amount'],'-0.2000')
