"""Offline integration checks; generated fixture results are not research findings.

Run: python -m unittest discover -s tests -v
"""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

NOTEBOOK = Path(__file__).resolve().parents[1] / "Access_Beyond_the_Map.ipynb"


class NotebookIntegration(unittest.TestCase):
    def run_pipeline(self, provisional=False):
        notebook = json.loads(NOTEBOOK.read_text())
        ns = {}
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as work, contextlib.redirect_stdout(io.StringIO()):
            os.chdir(work)
            try:
                for index, cell in enumerate(notebook["cells"]):
                    if cell["cell_type"] != "code":
                        continue
                    source = "".join(cell["source"])
                    if source.lstrip().startswith("%pip"):
                        continue
                    if index == 4:
                        source = source.replace('MODE = "real"', 'MODE = "synthetic"')
                        source = source.replace('DATA_DIR = Path("/content/data" if Path("/content").exists() else "data")', 'DATA_DIR = Path("data")')
                    if index == 14 and provisional:
                        # Exercise the real-mode no-human-label path on generated data.
                        ns["MODE"] = "real"
                    exec(compile(source, f"cell_{index}", "exec"), ns)
                    if index == 8:
                        raw = ns["places_raw"]
                        raw["permanently_closed"] = "False"
                        raw.loc[0, "permanently_closed"] = "True"
                        raw.loc[1, "permanently_closed"] = "unknown"
                        raw["temporarily_closed"] = "False"
                        raw.loc[2, "temporarily_closed"] = "True"
                self.assertNotIn("fixture_000", set(ns["p"].place_id))
                self.assertIn("fixture_001", set(ns["p"].place_id))
                self.assertEqual(ns["p"].set_index("place_id").loc["fixture_002", "closure_status"], "temporarily_closed")
                self.assertEqual(ns["audit"]["closure"]["permanently_closed_places_excluded"], 1)
                self.assertTrue((ns["OUT"] / "map_PRIVATE.html").is_file())
                self.assertTrue((ns["OUT"] / "submission_preflight.json").is_file())
                self.assertTrue(Path(ns["bundle"]).is_file())
                # Exercise widget callbacks, including an empty filter result.
                ns["service_w"].value = "pharmacy"
                ns["aspect_w"].value = "language"
                ns["days_w"].value = 90
                ns["score_w"].value = 1.0
                if provisional:
                    self.assertEqual(ns["LABEL_MODE"], "provisional_rule_labels")
                    self.assertEqual(ns["metrics"]["n_labeled_test"], 0)
                    self.assertEqual(ns["metrics"]["models"], {})
                    self.assertIn("BLOCKED", ns["EVALUATION_STATUS"])
                else:
                    self.assertEqual(len(ns["metrics"]["models"]), 3)
                    self.assertEqual(len(ns["subgroup_rows"]), 3)
            finally:
                os.chdir(previous)

    def test_synthetic_with_closed_and_unknown_locations(self):
        self.run_pipeline()

    def test_provisional_without_human_labels(self):
        self.run_pipeline(provisional=True)


if __name__ == "__main__":
    unittest.main()
