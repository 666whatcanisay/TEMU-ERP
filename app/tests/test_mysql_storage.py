"""Real MySQL contracts. Never run destructive test resets against the app schema."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

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
