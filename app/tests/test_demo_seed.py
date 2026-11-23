import importlib.util
from pathlib import Path
import tempfile
import unittest

from app.backend.adapters.storage_sqlite import SQLiteStore
from app.backend.application.services import WorkbenchService

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('seed_demo', ROOT / 'scripts/seed-demo.py')
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


class DemoSeedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.store = SQLiteStore(Path(self.tmp.name) / 'demo.db')

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_offline_demo_reproduces_five_products_and_latest_sku_quote(self):
        demo.seed(self.store)
        service = WorkbenchService(self.store)
        self.assertEqual(len(service.list_candidates()), 5)
        view = service.get_candidate('DE-DRAWER-006')['skus'][0]
        self.assertEqual(view['active_evaluation']['values']['supply_income'], '21.00')
        self.assertEqual(view['full_profit']['scenarios']['baseline']['net_profit'], '4.4816')
        self.assertEqual(view['full_profit']['scenarios']['conservative']['net_profit'], '2.1295')
        for candidate in self.store.list_records('candidate'):
            self.assertIsNone(candidate.get('platform_product_id'))
        for source in self.store.list_records('source'):
            self.assertIsNone(source['facts']['sales'])

    def test_reseeding_preserves_user_edits_and_existing_policy(self):
        demo.seed(self.store)
        candidate = self.store.get_record('candidate', 'DE-DRAWER-006')
        candidate['title'] = '用户已经修改的商品'
        self.assertEqual(self.store.upsert_record(candidate), [])
        policy = WorkbenchService(self.store).get_policy()
        policy['threshold_percent'] = '55'
        self.assertEqual(self.store.upsert_record(policy), [])
        result = demo.seed(self.store)
        self.assertEqual(result['added'], [])
        self.assertEqual(self.store.get_record('candidate', 'DE-DRAWER-006')['title'], candidate['title'])
        self.assertEqual(WorkbenchService(self.store).get_policy()['threshold_percent'], '55')
        self.assertEqual(len(self.store.list_records('feedback')), 3)
