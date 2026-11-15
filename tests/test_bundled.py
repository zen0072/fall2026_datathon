"""Fresh clones load precomputed real classifications, without model dependencies."""

import unittest

from access_app.bundled import seed_bundled_results
from access_app.database import Store
from access_app.demo import demo_bundle


class BundledResultsTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(':memory:')

    def tearDown(self):
        self.store.close()

    def test_empty_database_gets_the_existing_real_predictions(self):
        self.assertTrue(seed_bundled_results(self.store))
        metadata = self.store.metadata()
        self.assertEqual(metadata['dataset']['mode'], 'real')
        self.assertEqual(metadata['dataset']['model'], 'openai:gpt-5.6-terra')
        self.assertEqual(metadata['dataset']['label_mode'], 'llm_direct_classification')
        self.assertEqual(metadata['coverage']['locations'], 79)
        self.assertEqual(metadata['coverage']['sampled_reviews'], 1868)
        self.assertEqual(self.store.list_places(limit=500)['total'], 79)
        self.assertEqual(self.store.connection.execute('SELECT count(*) FROM evidence').fetchone()[0], 1303)
        self.assertFalse(seed_bundled_results(self.store))
        self.assertEqual(self.store.metadata()['snapshot_id'], metadata['snapshot_id'])

    def test_existing_imports_are_never_replaced(self):
        metadata = self.store.import_bundle(demo_bundle())
        self.assertFalse(seed_bundled_results(self.store))
        self.assertEqual(self.store.metadata()['snapshot_id'], metadata['snapshot_id'])
        self.assertEqual(self.store.metadata()['coverage']['locations'], 4)


if __name__ == '__main__':
    unittest.main()
