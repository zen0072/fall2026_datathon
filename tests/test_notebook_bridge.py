"""The actual synthetic notebook export must import into the app unchanged."""

import importlib.util
import unittest

from access_app.database import Store
import test_notebook


@unittest.skipUnless(all(importlib.util.find_spec(p) for p in ("pandas", "sklearn", "datasketch", "folium", "ipywidgets")), "Install requirements.txt for notebook integration")
class NotebookBridge(unittest.TestCase):
    def test_export_import_and_location_evidence(self):
        payload = test_notebook.NotebookIntegration().run_pipeline(prediction_model="tfidf_word")
        store = Store(":memory:")
        try:
            metadata = store.import_bundle(payload)
            self.assertEqual(metadata["dataset"]["mode"], "synthetic")
            self.assertEqual(metadata["dataset"]["model"], "tfidf_word")
            self.assertEqual(metadata["dataset"]["selection"]["prediction_model"], "tfidf_word")
            self.assertTrue(any(0 < e["score"] < 1 for e in payload["evidence"]))
            self.assertEqual(metadata["dataset"]["label_mode"], "synthetic_known_states")
            self.assertEqual(metadata["coverage"]["locations"], len(payload["places"]))
            first = payload["places"][0]
            detail = store.place_detail(first["place_id"], "physical")
            self.assertEqual(detail["place"]["sampled_reviews"], first["sampled_reviews"])
            self.assertEqual(len(detail["aspects"]), 5)
            self.assertTrue(all(e["text"] for e in detail["evidence"]))
        finally:
            store.close()
