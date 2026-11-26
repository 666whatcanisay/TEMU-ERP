"""Real MySQL contracts. Never run destructive test resets against the app schema."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.backend import config
from app.backend.adapters import storage_state
from app.backend.adapters.storage_mysql import MySQLStore
from app.backend.adapters.storage_sqlite import SQLiteStore
from app.backend.application.services import WorkbenchService
from app.tests import test_storage as contract

@unittest.skipUnless(os.environ.get('WORKBENCH_TEST_MYSQL')=='1','real MySQL integration explicitly disabled')
class MySQLStorageTests(contract.StorageTests):
    def setUp(self):
        database=os.environ.get('WORKBENCH_TEST_MYSQL_DATABASE','temu_workbench_test')
        if database==config.MYSQL_DATABASE or not database.endswith(('_test','_ci')):
            raise RuntimeError('Refusing test reset outside an explicitly separate test schema')
        self.tmp=tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.store=MySQLStore(**{**config.mysql_settings(),'database':database})
        self.store.replace_state(storage_state.envelope({t:[] for t in storage_state.TABLES}))

    def test_case_sensitive_ids_chinese_and_emoji(self):
        for key in ['Case-A','case-a']:
            row=contract.candidate_record(key);row['title']='收纳盒📦'
            self.assertEqual(self.store.upsert_record(row),[])
        self.assertEqual(len(self.store.list_records('candidate')),2)
        self.assertEqual(self.store.get_record('candidate','Case-A')['title'],'收纳盒📦')

    def test_all_five_tables_migrate_losslessly_and_do_not_overwrite(self):
        source=SQLiteStore(Path(self.tmp.name)/'source.db')
        try:
            source.upsert_record(contract.candidate_record())
            source.add_revision('TEST-001','TEST-SKU-1','price','10','12','tester','manual')
            source.save_submission({'id':'SUB-1','candidate_id':'TEST-001','created_at':'2026-11-24T12:00:00+08:00'})
            source.set_adapter_status('test','succeeded',{'count':1})
            source.save_snapshot('SRC-1','snapshot','a'*64,'path','succeeded',{'field':'原文'})
            state=source.export_state()
            self.store.replace_state(state,require_empty=True)
            self.assertEqual(self.store.export_state()['sha256'],state['sha256'])
            with self.assertRaises(ValueError):self.store.replace_state(state,require_empty=True)
            path=Path(self.tmp.name)/'all.mysql.json';self.store.backup(path)
            self.store.upsert_record(contract.candidate_record('ADDED'))
            self.assertEqual(self.store.restore(path),[])
            self.assertEqual(self.store.export_state()['sha256'],state['sha256'])
        finally:source.close()

    def test_mid_restore_database_error_rolls_back_deleted_and_inserted_rows(self):
        self.store.upsert_record(contract.candidate_record('KEEP'))
        before=self.store.export_state()
        bad=copy.deepcopy(before)
        bad['tables']['records'][0]['id']='NEW'
        bad['tables']['revisions']=[dict(id='REV-X',candidate_id='NEW',sku_ref=None,
            field_key='x'*500,payload='{}',created_at='2026-11-24')]
        bad=storage_state.envelope(bad['tables'])
        self.assertTrue(self.store.restore(self._write_backup(bad)))
        self.assertEqual(self.store.export_state()['sha256'],before['sha256'])

    def _write_backup(self,state):
        path=Path(self.tmp.name)/'test.mysql.json'
        path.write_text(json.dumps(state),encoding='utf-8')
        return path

    def test_corrupted_backup_preserves_live_records(self):
        self.store.upsert_record(contract.candidate_record('KEEP'))
        state=self.store.export_state();state['sha256']='wrong'
        self.assertTrue(self.store.restore(self._write_backup(state)))
        self.assertIsNotNone(self.store.get_record('candidate','KEEP'))

    def test_idle_connection_reopens_before_a_new_operation(self):
        self.store.upsert_record(contract.candidate_record())
        self.store._conn.close()
        self.assertIsNotNone(self.store.get_record('candidate','TEST-001'))

    def test_full_workflow_and_csv_json_keep_sku_profit_inputs(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('mysql_demo',Path(__file__).resolve().parents[2]/'scripts/seed-demo.py')
        demo=importlib.util.module_from_spec(spec);spec.loader.exec_module(demo)
        demo.seed(self.store)
        service=WorkbenchService(self.store)
        detail=service.get_candidate('DE-DRAWER-006')
        self.assertEqual(detail['skus'][0]['full_profit']['scenarios']['baseline']['net_profit'],'4.4816')
        self.assertEqual(service.build_submission('DE-DRAWER-006')['status'],'succeeded')
        for fmt in ['json','csv']:
            output=service.export_bundle(fmt)['content']
            target=SQLiteStore(Path(self.tmp.name)/(fmt+'.db'))
            try:
                report=WorkbenchService(target).import_bundle(fmt,json.dumps(output,ensure_ascii=False) if fmt=='json' else output)
                self.assertEqual(report['errors'],[])
                self.assertEqual(target.get_record('candidate','DE-DRAWER-006')['skus'],detail['candidate']['skus'])
            finally:target.close()

    def test_typed_sql_columns_are_the_application_source_of_truth(self):
        row=contract.candidate_record();row['title']='原标题'
        row['skus'][0]['supply_income']['amount']='28.00'
        self.store.upsert_record(row)
        self.store._execute('UPDATE products SET title=? WHERE product_id=?',('SQL更新标题','TEST-001'))
        self.store._execute('UPDATE product_skus SET supply_amount=? WHERE product_id=? AND merchant_sku=?',('31.50','TEST-001','TEST-SKU-1'))
        loaded=self.store.get_record('candidate','TEST-001')
        self.assertEqual(loaded['title'],'SQL更新标题')
        self.assertEqual(loaded['skus'][0]['supply_income']['amount'],'31.50')
        extension=json.loads(self.store._row('products',{'product_id':'TEST-001'})['extension_json'])['data']
        self.assertNotIn('title',extension);self.assertNotIn('skus',extension)

    def test_many_to_many_evidence_and_unresolved_refs_have_visible_status(self):
        row=contract.candidate_record();row['evidence_refs']=['SRC-REAL','SRC-MISSING']
        self.store.upsert_record(row)
        source={'record_type':'source','id':'SRC-REAL','url':'https://example.com/evidence','title':'出处','locator':'product details','verification':'needs_review'}
        self.store.upsert_record(source)
        rows=self.store._execute('SELECT source_ref,url,link_status FROM v_product_evidence ORDER BY source_ref').fetchall()
        self.assertEqual(rows[0]['link_status'],'unresolved')
        self.assertEqual(rows[1]['url'],source['url'])
        other=contract.candidate_record('TEST-002');other['evidence_refs']=['SRC-REAL'];self.store.upsert_record(other)
        self.assertEqual(len(self.store._execute('SELECT * FROM product_evidence WHERE source_id=?',('SRC-REAL',)).fetchall()),2)

    def test_foreign_keys_reject_orphans_and_cost_keys_are_unique(self):
        import pymysql
        with self.assertRaises(pymysql.IntegrityError):
            self.store._execute('INSERT INTO product_evidence(product_id,position,source_ref) VALUES(?,?,?)',('NO-PRODUCT',0,'X'))
        self.store.upsert_record(contract.candidate_record())
        with self.assertRaises(pymysql.IntegrityError):
            self.store._execute('INSERT INTO sku_costs(product_id,merchant_sku,cost_key,position,extension_json) VALUES(?,?,?,?,?)',('TEST-001','TEST-SKU-1','purchase',0,'{}'))
        self.assertIsNone(self.store._execute('SELECT five_cost_total FROM v_sku_cost_summary').fetchone()['five_cost_total'])

    def test_mid_child_write_failure_rolls_back_product_sku_cost_and_audit(self):
        import pymysql
        service=WorkbenchService(self.store);service.save_candidate(contract.candidate_record())
        before=self.store.export_relational_state()
        changed=self.store.get_record('candidate','TEST-001');changed['title']='Should roll back'
        changed['skus'][0]['costs'][1]['money']['amount']='3.50'
        original=self.store._execute
        def interrupt(sql,params=()):
            if sql.startswith('INSERT INTO `sku_costs`') and 'packaging' in params:
                raise pymysql.OperationalError(9999,'injected child write failure')
            return original(sql,params)
        with patch.object(self.store,'_execute',side_effect=interrupt):
            with self.assertRaises(pymysql.OperationalError):service.save_candidate(changed,'tester')
        self.assertEqual(self.store.export_relational_state()['sha256'],before['sha256'])

    def test_removed_sku_is_inactive_and_pricing_history_keeps_its_foreign_key(self):
        row=contract.candidate_record();second=copy.deepcopy(row['skus'][0]);second['merchant_sku']='TEST-SKU-2';row['skus'].append(second)
        self.store.upsert_record(row)
        feedback={'record_type':'feedback','id':'FB-KEEP','candidate_id':row['id'],'sku_ref':'TEST-SKU-2',
                  'platform_stage':'pricing','verification':'draft','feedback_text':'history'}
        self.assertEqual(self.store.upsert_record(feedback),[])
        row['skus'].pop();self.store.upsert_record(row)
        self.assertEqual(len(self.store.get_record('candidate',row['id'])['skus']),1)
        self.assertFalse(self.store._row('product_skus',{'product_id':row['id'],'merchant_sku':'TEST-SKU-2'})['is_active'])
        self.assertEqual(self.store._row('buyer_feedback',{'feedback_id':'FB-KEEP'})['linked_sku'],'TEST-SKU-2')

    def test_reference_sources_and_inactive_rows_survive_complete_v2_backup(self):
        self.store.upsert_record(contract.candidate_record())
        self.store.ensure_reference_sources([dict(id='RULE-1',url='https://example.com/rule',title='规则',level='official_policy',locator='section',verification='needs_review')])
        before=self.store.export_relational_state()
        backup=Path(self.tmp.name)/'relational.mysql.json';self.store.backup(backup)
        state=json.loads(backup.read_text());self.assertEqual(state['format'],'temu-workbench-relational/v2')
        self.store.upsert_record(contract.candidate_record('NEW'))
        self.assertEqual(self.store.restore(backup),[])
        self.assertEqual(self.store.export_relational_state()['sha256'],before['sha256'])
        self.assertEqual(self.store.reference_sources()[0]['id'],'RULE-1')

    def test_corrupt_v2_backup_and_fk_failure_preserve_every_entity(self):
        from app.backend.adapters.storage_mysql import relational_digest
        self.store.upsert_record(contract.candidate_record())
        before=self.store.export_relational_state();bad=copy.deepcopy(before)
        bad['tables']['product_evidence']=[dict(product_id='MISSING',position=0,source_ref='REF',source_id=None)]
        bad['sha256']=relational_digest(bad['tables'])
        self.assertTrue(self.store.restore(self._write_backup(bad)))
        self.assertEqual(self.store.export_relational_state()['sha256'],before['sha256'])

    def test_registry_bootstrap_does_not_overwrite_business_observations(self):
        source=dict(record_type='source',id='SAME',url='https://example.com/product',title='商品证据',locator='details',verification='needs_review')
        self.store.upsert_record(source)
        self.store.ensure_reference_sources([dict(id='SAME',url='https://example.com/policy',title='规则登记')])
        self.assertEqual(self.store.get_record('source','SAME'),source)
        self.assertEqual(self.store.reference_sources()[0]['title'],'规则登记')
        self.store.ensure_reference_sources([dict(id='SAME',title='不应覆盖')])
        self.assertEqual(self.store.reference_sources()[0]['title'],'规则登记')

    def test_historical_submission_cannot_be_overwritten(self):
        self.store.upsert_record(contract.candidate_record())
        submission=dict(id='SUB-KEEP',candidate_id='TEST-001',title='旧评审',created_at='2026-11-26T10:00:00+08:00')
        self.store.save_submission(submission)
        with self.assertRaisesRegex(ValueError,'cannot be overwritten'):
            self.store.save_submission({**submission,'title':'新内容'})
        self.assertEqual(self.store.list_submissions()[0],submission)

    def test_model_dictionary_drift_is_rejected_instead_of_silently_used(self):
        self.store._execute('UPDATE profit_parameter_definitions SET default_value=? WHERE parameter_key=?',('99','refund_percent'))
        with self.assertRaisesRegex(RuntimeError,'参数字典'):
            self.store.validate_parameter_definitions()
        self.store.ensure_parameter_definitions()
        self.store.validate_parameter_definitions()

    def test_incompatible_model_dictionary_backup_is_rolled_back(self):
        from app.backend.adapters.storage_mysql import relational_digest
        before=self.store.export_relational_state();bad=copy.deepcopy(before)
        bad['tables']['profit_parameter_definitions'][0]['default_value']='999.000000000000'
        bad['sha256']=relational_digest(bad['tables'])
        self.assertTrue(self.store.restore(self._write_backup(bad)))
        self.assertEqual(self.store.export_relational_state()['sha256'],before['sha256'])
