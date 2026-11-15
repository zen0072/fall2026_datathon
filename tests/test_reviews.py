"""Reviews-only ingestion must not invent place metadata or evaluation results."""

import csv
import tempfile
import unittest
from pathlib import Path

from access_app.database import Store
from access_app.reviews import build_reviews_bundle
from access_app.schema import AppError

NOTEBOOK = Path(__file__).resolve().parents[1] / "Access_Beyond_the_Map.ipynb"


class ReviewsOnly(unittest.TestCase):
    def test_sparse_categories_deduplication_and_unverified_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "reviews.csv"
            with source.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=["place_id", "place_name", "address", "category", "review", "review_date", "reviewer_name"])
                writer.writeheader()
                for row in [
                    ["p1", "Example clinic", "Example address", "", "The entrance has steps and no ramp.", "2025-04-01", "PRIVATE NAME"],
                    ["p1", "Example clinic", "Example address", "Medical clinic", "The ramp provided easy wheelchair access.", "2025-05-01", "PRIVATE NAME"],
                    ["p1", "Example clinic", "Example address", "", "THE ENTRANCE HAS STEPS AND NO RAMP!", "2025-06-01", "PRIVATE NAME"],
                    ["p2", "Unscoped business", "", "", "No interpreter was available.", "2025-06-01", "PRIVATE NAME"],
                    ["p3", "Example pharmacy", "", "Pharmacy", "Staff were friendly.", "not a date", "PRIVATE NAME"],
                ]:
                    writer.writerow(dict(zip(writer.fieldnames, row)))
            bundle = build_reviews_bundle(source, NOTEBOOK)
            self.assertEqual(len(bundle["places"]), 2)
            self.assertEqual(bundle["dataset"]["selection"]["raw_review_rows"], 5)
            self.assertEqual(bundle["dataset"]["selection"]["places_with_category"], 2)
            self.assertEqual(bundle["dataset"]["selection"]["normalized_duplicates_removed"], 1)
            self.assertEqual(bundle["dataset"]["selection"]["unknown_review_dates"], 1)
            self.assertTrue(all(p["lat"] is None and p["lon"] is None for p in bundle["places"]))
            self.assertTrue(all(p["closure_status"] == "not_verified_open" for p in bundle["places"]))
            self.assertEqual(bundle["dataset"]["metrics"]["models"], {})
            self.assertNotIn("PRIVATE NAME", str(bundle))
            store = Store(":memory:")
            try:
                store.import_bundle(bundle)
                detail = store.place_detail("p1", "physical")
                aspect = next(a for a in detail["aspects"] if a["aspect"] == "physical")
                self.assertEqual(aspect["status"], "conflicting_or_unclear")
                self.assertEqual(aspect["sampled_reviews"], 2)
                self.assertEqual(len(detail["evidence"]), 2)
                self.assertFalse(detail["place"]["valid_coordinates"])
            finally:
                store.close()

    def test_wrong_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "wrong.csv"
            source.write_text("name,review\nTest,Example\n")
            with self.assertRaises(AppError):
                build_reviews_bundle(source, NOTEBOOK)
