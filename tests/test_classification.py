"""Direct classification must preserve source evidence, counts and provenance."""

import copy
import csv
import io
import json
import tempfile
import unittest
import os
import sys
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from access_app.chat import DEFAULT_CHAT_MODEL
from access_app.classification import (ASPECTS, cache_identity, classify, digest,
                                       export_bundle, file_sha, load_cohort,
                                       resolve_selection, source_passages, validate_classification)
from access_app.database import Store
from access_app.demo import demo_bundle
from scripts import classify_reviews_llm as runner


def prediction(quote="", state="no_mention"):
    result = {a: {"state": "no_mention", "evidence": ""} for a in ASPECTS}
    result["physical"] = {"state": state, "evidence": quote}
    return result


class ClassificationTests(unittest.TestCase):
    def test_fabricated_quotes_missing_aspects_and_false_no_mention_rejected(self):
        review = "There is a ramp, but it is blocked."
        self.assertEqual(validate_classification(prediction(review, "unclear_or_mixed"), review)["physical"]["state"], "unclear_or_mixed")
        invalid = [prediction("A perfect entrance", "positive_access"),
                   prediction("ramp", "no_mention"), prediction("", "barrier_reported"),
                   prediction("ramp", "accessible")]
        missing = prediction(); missing.pop("sensory"); invalid.append(missing)
        for item in invalid:
            with self.subTest(item=item), self.assertRaises(ValueError):
                validate_classification(item, review)

    def test_request_contract_and_provider_provenance(self):
        review = "There are steps."
        output = {a: {"state": "no_mention", "evidence_ids": []} for a in ASPECTS}
        output["physical"] = {"state": "barrier_reported", "evidence_ids": ["p0"]}
        response = {"status": "completed", "model": "returned-version", "id": "response-1",
                    "usage": {"input_tokens": 20},
                    "output": [{"content": [{"type": "output_text", "text": json.dumps(output)}]}]}
        with patch("access_app.classification.urlopen", return_value=io.BytesIO(json.dumps(response).encode())) as call:
            result = classify(review, DEFAULT_CHAT_MODEL, "dummy-key")
        request = call.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.get_header("Authorization"), "Bearer dummy-key")
        self.assertEqual(payload["text"]["format"]["schema"]["required"], list(ASPECTS))
        self.assertTrue(payload["text"]["format"]["strict"])
        self.assertFalse(payload["store"])
        self.assertEqual(payload["reasoning"], {"effort": "none"})
        self.assertEqual(json.loads(payload["input"]), {"passages": [{"id": "p0", "text": review}]})
        self.assertEqual(result["classification"]["physical"]["evidence"], review)
        self.assertEqual(result["returned_model"], "returned-version")
        self.assertNotIn("dummy-key", json.dumps(result))

    def test_provider_errors_never_become_classifications_or_expose_key(self):
        for response in [{"status": "incomplete"}, {"status": "completed", "output": []}]:
            with patch("access_app.classification.urlopen", return_value=io.BytesIO(json.dumps(response).encode())):
                with self.assertRaises(ValueError):
                    classify("Steps.", DEFAULT_CHAT_MODEL, "dummy-key")
        error = HTTPError("https://api.openai.com/v1/responses", 401, "dummy-key", {}, None)
        with patch("access_app.classification.urlopen", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, "HTTP 401") as raised:
                classify("Steps.", DEFAULT_CHAT_MODEL, "dummy-key")
        self.assertNotIn("dummy-key", str(raised.exception))
        with self.assertRaises(ValueError) as raised:
            classify("Steps.", DEFAULT_CHAT_MODEL, "secret\nvalue")
        self.assertNotIn("secret", str(raised.exception))

    def test_passage_ids_preserve_exact_text_and_counterevidence(self):
        review = "A ramp exists.\nBut it is often blocked.  Staff sometimes help."
        passages = source_passages(review)
        selected = {a: {"state": "no_mention", "evidence_ids": []} for a in ASPECTS}
        selected["physical"] = {"state": "unclear_or_mixed", "evidence_ids": [passages[0]["id"], passages[-1]["id"]]}
        result = resolve_selection(selected, passages, review)
        self.assertEqual(result["physical"]["evidence"], review)
        selected["physical"]["evidence_ids"] = ["invented"]
        with self.assertRaises(ValueError):
            resolve_selection(selected, passages, review)

    def test_export_denominators_counterevidence_and_duckdb_import(self):
        baseline = demo_bundle()
        baseline["dataset"]["source_manifest"] = {"google_maps_reviews.csv": {"sha256": "fixture"}}
        pid = baseline["places"][0]["place_id"]
        reviews = [{"record_id": str(i), "place_id": pid, "review": text, "date": "2026-01-02"}
                   for i, text in enumerate(["Steps block entry.", "The ramp helps.", "Nice staff."])]
        results = {"0": {"classification": prediction(reviews[0]["review"], "barrier_reported")},
                   "1": {"classification": prediction(reviews[1]["review"], "positive_access")},
                   "2": {"classification": prediction()}}
        bundle = export_bundle(baseline, reviews, results, DEFAULT_CHAT_MODEL, "manifest")
        physical = next(a for a in bundle["aspects"] if a["aspect"] == "physical")
        self.assertEqual(physical["sampled_reviews"], 3)
        self.assertEqual(physical["barrier_reports"], 1)
        self.assertEqual(physical["positive_reports"], 1)
        self.assertEqual(physical["status"], "conflicting_or_unclear")
        self.assertEqual(len(bundle["evidence"]), 2)
        self.assertTrue(all(e["score"] is None and e["barrier_score"] is None for e in bundle["evidence"]))
        self.assertEqual(bundle["dataset"]["metrics"], {})
        self.assertEqual(bundle["dataset"]["label_mode"], "llm_direct_classification")
        self.assertTrue(bundle["dataset"]["selection"]["partial_review_coverage"])
        store = Store(":memory:")
        try:
            metadata = store.import_bundle(bundle)
            self.assertEqual(metadata["coverage"]["sampled_reviews"], 3)
        finally:
            store.close()
        results.pop("2")
        with self.assertRaises(ValueError):
            export_bundle(baseline, reviews, results, DEFAULT_CHAT_MODEL, "manifest")

    def test_cache_changes_with_model_review_or_rubric(self):
        key = cache_identity("Original", "model-a")
        self.assertNotEqual(key, cache_identity("Changed", "model-a"))
        self.assertNotEqual(key, cache_identity("Original", "model-b"))
        with patch("access_app.classification.RUBRIC", "new rubric"):
            self.assertNotEqual(key, cache_identity("Original", "model-a"))

    def test_exact_cohort_recovery_and_hash_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reviews_path, manifest_path = root / "reviews.csv", root / "manifest.csv"
            baseline = copy.deepcopy(demo_bundle())
            baseline["places"] = baseline["places"][:1]
            pid = baseline["places"][0]["place_id"]
            baseline["aspects"] = [a for a in baseline["aspects"] if a["place_id"] == pid]
            baseline["evidence"] = []
            baseline["places"][0]["sampled_reviews"] = 1
            for a in baseline["aspects"]:
                a.update(sampled_reviews=1, barrier_reports=0, positive_reports=0, uncertain_reports=0)
            review = "There is a ramp."
            rid = digest(pid + "|" + review)[:24]
            with reviews_path.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=["place_id", "review", "review_date"])
                writer.writeheader(); writer.writerow({"place_id": pid, "review": review, "review_date": "2026-01-01"})
            with manifest_path.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=["record_id", "place_id"])
                writer.writeheader(); writer.writerow({"record_id": rid, "place_id": pid})
            baseline["dataset"]["source_manifest"] = {"google_maps_reviews.csv": {"sha256": file_sha(reviews_path)}}
            rows = load_cohort(reviews_path, manifest_path, baseline)
            self.assertEqual(rows[0]["review"], review)
            reviews_path.write_text("changed")
            with self.assertRaisesRegex(ValueError, "source hash"):
                load_cohort(reviews_path, manifest_path, baseline)

    def test_runner_stops_on_failure_and_resumes_without_repeating_paid_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = demo_bundle()
            baseline["places"] = baseline["places"][:1]
            pid = baseline["places"][0]["place_id"]
            baseline["places"][0]["sampled_reviews"] = 2
            baseline_path = root / "baseline.json"
            baseline_path.write_text(json.dumps(baseline))
            reviews = [{"record_id": str(i), "place_id": pid, "review": text, "date": "2026-01-01"}
                       for i, text in enumerate(["Blocked steps.", "A useful ramp."])]
            def result(text):
                return {"classification": prediction(text, "barrier_reported"), "returned_model": "test-model"}
            argv = ["classify_reviews_llm.py", "--baseline", str(baseline_path),
                    "--output-dir", str(root / "output"), "--workers", "1", "--run"]
            with patch.object(sys, "argv", argv), patch.dict(os.environ, {"OPENAI_API_KEY": "dummy"}, clear=True), \
                    patch.object(runner, "load_cohort", return_value=reviews), \
                    patch.object(runner, "file_sha", return_value="manifest"), \
                    patch("sys.stdout", new_callable=io.StringIO):
                with patch.object(runner, "classify", side_effect=[result(reviews[0]["review"]), RuntimeError("provider unavailable")]):
                    self.assertEqual(runner.main(), 1)
                self.assertFalse((root / "output/frontend_results_PRIVATE.json").exists())
                with patch.object(runner, "classify", return_value=result(reviews[1]["review"])) as call:
                    self.assertEqual(runner.main(), 0)
                    self.assertEqual(call.call_count, 1)
                status = json.loads((root / "output/run_status.json").read_text())
                self.assertEqual(status["cached_reviews"], 1)
                self.assertEqual(status["completed_reviews"], 2)
                self.assertEqual(status["state"], "complete")
                self.assertNotIn("dummy", (root / "output/run_status.json").read_text())
                with patch.dict(os.environ, {}, clear=True), patch.object(runner, "classify") as call:
                    self.assertEqual(runner.main(), 0)
                    call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
