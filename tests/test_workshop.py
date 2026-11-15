"""Independent input, training isolation, checkpoint and export guarantees."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import pandas as pd

from access_app import workshop
from access_app.schema import ASPECTS, validate_bundle


class WorkshopTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = workshop.write_demo_csv(self.root / "input.csv")
        self.frame, self.audit = workshop.load_reviews(self.path)
        self.frame = workshop.split_reviews(self.frame)

    def labels(self, frame):
        template = workshop.annotation_template(frame)
        # Construct a user-supplied fixture, not a research evaluation dataset.
        template["state"] = "no_mention"
        template["evidence"] = ""
        template["annotator_id"] = "fixture-annotator"
        template["provenance"] = "human"
        template["adjudicated"] = "true"
        path = self.root / "labels.csv"
        template.to_csv(path, index=False)
        return path

    def fake_api(self, review, model, api_key):
        return dict(classification={aspect: dict(state="no_mention", evidence="") for aspect in ASPECTS},
                    requested_model=model, returned_model=model, response_id="mock-response", usage={"input_tokens": 12},
                    classified_at="2026-11-15T00:00:00+00:00")

    def test_streamed_sampling_deduplicates_and_is_repeatable(self):
        original = pd.read_csv(self.path)
        duplicate = original.iloc[[0]].copy()
        duplicate["review"] = duplicate.review.str.upper()
        pd.concat([original, duplicate, pd.DataFrame([dict(place_id="empty", review="")])]).to_csv(self.path, index=False)
        a, audit = workshop.load_reviews(self.path, max_reviews=17, seed=123)
        b, _ = workshop.load_reviews(self.path, max_reviews=17, seed=123)
        pd.testing.assert_frame_equal(a, b)
        self.assertEqual(len(a), 17)
        self.assertEqual(audit["duplicate_rows"], 1)
        self.assertEqual(audit["empty_rows"], 1)
        self.assertEqual(audit["source_sha256"], workshop.sha256(self.path))
        self.assertFalse(set(a) & {"reviewer_name", "response_of_owner"})

    def test_locations_and_vocabulary_are_held_out(self):
        train = self.frame[self.frame.split.eq("train")]
        test = self.frame[self.frame.split.eq("test")]
        self.assertFalse(set(train.place_id) & set(test.place_id))
        original_fit = workshop.TfidfVectorizer.fit_transform
        fitted = []
        def fit(vectorizer, texts, *args, **kwargs):
            fitted.extend(texts)
            return original_fit(vectorizer, texts, *args, **kwargs)
        with patch.object(workshop.TfidfVectorizer, "fit_transform", autospec=True, side_effect=fit):
            predictions, info = workshop.classify_reviews(self.frame, method="tfidf_logreg")
        self.assertEqual(set(fitted), set(train.review))
        self.assertFalse(set(fitted) & set(test.review))
        self.assertEqual(len(predictions), len(self.frame) * 5)
        self.assertEqual(info["training_label_source"], "keyword_rules")
        self.assertEqual(workshop.evaluate(predictions, pd.DataFrame())["aspects"], {})

    def test_human_training_only_uses_training_labels_and_reports_constant_models(self):
        path = self.labels(self.frame)
        labels = workshop.load_human_labels(path, self.frame)
        heldout_ids = set(self.frame.loc[self.frame.split.eq("test"), "record_id"])
        labels.loc[labels.record_id.isin(heldout_ids), list(ASPECTS)] = "positive_access"
        predictions, info = workshop.classify_reviews(self.frame, method="tfidf_logreg", label_source="human", human_labels=labels)
        self.assertTrue(predictions.state.eq("no_mention").all())
        self.assertTrue(all(s["estimator"] == "DummyClassifier" for s in info["training_support"].values()))
        report = workshop.evaluate(predictions, labels)
        self.assertEqual(report["complete_test_reviews"], len(heldout_ids))
        training_labels = labels[~labels.record_id.isin(heldout_ids)]
        self.assertEqual(workshop.evaluate(predictions, training_labels)["aspects"], {})

    def test_labels_reject_invented_evidence(self):
        path = self.labels(self.frame)
        rows = pd.read_csv(path, keep_default_na=False)
        rows.loc[0, ["state", "evidence"]] = ["barrier_reported", "This quotation is invented."]
        rows.to_csv(path, index=False)
        with self.assertRaisesRegex(ValueError, "exact, nonempty"):
            workshop.load_human_labels(path, self.frame)

    def test_small_location_set_can_use_keywords_but_cannot_claim_test_metrics(self):
        frame = workshop.split_reviews(self.frame[self.frame.place_id.eq(self.frame.place_id.iloc[0])])
        predictions, _ = workshop.classify_reviews(frame)
        self.assertEqual(len(predictions), len(frame) * 5)
        with self.assertRaisesRegex(ValueError, "five retained locations"):
            workshop.classify_reviews(frame, method="tfidf_logreg")

    def test_exports_are_fresh_schema_valid_and_source_faithful(self):
        predictions, info = workshop.classify_reviews(self.frame)
        texts = self.frame.set_index("record_id").review.to_dict()
        for row in predictions.itertuples():
            self.assertIn(row.evidence, texts[row.record_id])
        metadata, archive = workshop.export_run(self.frame, predictions, self.audit, info, pd.DataFrame(), self.root / "results", synthetic=True)
        self.assertEqual(metadata["evaluation"]["aspects"], {})
        with zipfile.ZipFile(archive) as output:
            bundle = json.loads(output.read("frontend_results.json"))
            validate_bundle(bundle)
            self.assertEqual(len(bundle["places"]), 20)
            self.assertEqual(bundle["dataset"]["mode"], "synthetic")
            self.assertEqual(sum(p["sampled_reviews"] for p in bundle["places"]), 120)
            self.assertTrue(all(p["lat"] is None for p in bundle["places"]))

    def test_budget_and_explicit_paid_gate_precede_key_prompt(self):
        with patch("access_app.classification.classify") as api, patch("access_app.workshop.getpass.getpass") as prompt:
            with self.assertRaisesRegex(ValueError, "limit exceeded"):
                workshop.prompt_llm_classification(self.frame, model="test-model", cache_dir=self.root / "cache", max_requests=1, allow_paid_calls=True)
            with self.assertRaisesRegex(ValueError, "ALLOW_PAID_API_CALLS"):
                workshop.prompt_llm_classification(self.frame.head(1), model="test-model", cache_dir=self.root / "cache")
            api.assert_not_called()
            prompt.assert_not_called()

    def test_llm_uses_own_key_and_checkpoints_resume_without_key_or_calls(self):
        frame = self.frame.head(2)
        destination = self.root / "llm"
        secret = "sk-test-not-a-real-secret"
        with patch("access_app.classification.classify", side_effect=self.fake_api) as api:
            with patch("access_app.workshop.getpass.getpass", return_value=secret):
                predictions, info = workshop.prompt_llm_classification(frame, model="test-model", cache_dir=destination / "cache", max_requests=2, allow_paid_calls=True)
            self.assertEqual(api.call_count, 2)
            self.assertTrue(all(call.args[2] == secret for call in api.call_args_list))
            api.reset_mock()
            replay, replay_info = workshop.prompt_llm_classification(frame, model="test-model", cache_dir=destination / "cache", max_requests=0)
            api.assert_not_called()
            pd.testing.assert_frame_equal(predictions, replay)
            self.assertEqual(replay_info["cached_reviews"], 2)
            changed = workshop.llm_preflight(frame, model="another-model", cache_dir=destination / "cache")
            self.assertEqual(changed["new_requests"], 2)
        _, archive = workshop.export_run(frame, predictions, self.audit, info, pd.DataFrame(), destination)
        with zipfile.ZipFile(archive) as output:
            self.assertEqual(len([p for p in output.namelist() if p.startswith("cache/")]), 2)
            for name in output.namelist():
                self.assertNotIn(secret.encode(), output.read(name))

    def test_api_failure_preserves_successful_checkpoints_and_never_invents_labels(self):
        frame = self.frame.head(2)
        calls = [self.fake_api(frame.iloc[0].review, "test-model", "unused"), RuntimeError("OpenAI HTTP 429")]
        with patch("access_app.classification.classify", side_effect=calls):
            with self.assertRaisesRegex(RuntimeError, "429"):
                workshop.classify_with_llm(frame, api_key="sk-test", model="test-model", cache_dir=self.root / "cache", max_requests=2)
        self.assertEqual(len(list((self.root / "cache").glob("*.json"))), 1)
        with patch("access_app.classification.classify", side_effect=self.fake_api) as api:
            predictions, _ = workshop.classify_with_llm(frame, api_key="sk-test", model="test-model", cache_dir=self.root / "cache", max_requests=1)
            self.assertEqual(api.call_count, 1)
            self.assertEqual(len(predictions), 10)


if __name__ == "__main__":
    unittest.main()
