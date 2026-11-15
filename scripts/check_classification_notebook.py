"""Execute the Binder notebook in isolation, without the app's saved results."""

import argparse
import json
import shutil
import tempfile
from pathlib import Path

import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = "Classify_Your_Own_Data.ipynb"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method", choices=["keywords", "tfidf_logreg", "llm"], default="keywords",
                        help="The llm check uses mocked responses and a fake key; never makes API calls.")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        (work / "access_app").mkdir()
        for name in ["__init__.py", "workshop.py", "schema.py", "reviews.py", "classification.py", "chat.py"]:
            shutil.copyfile(ROOT / "access_app" / name, work / "access_app" / name)
        shutil.copyfile(ROOT / "Access_Beyond_the_Map.ipynb", work / "Access_Beyond_the_Map.ipynb")
        notebook = nbformat.read(ROOT / NOTEBOOK, as_version=4)
        nbformat.validate(notebook)
        for cell in notebook.cells:
            if "parameters" in cell.metadata.get("tags", []):
                cell.source = cell.source.replace('METHOD = "keywords"', f'METHOD = "{args.method}"')
                if args.method == "llm":
                    cell.source = cell.source.replace("MAX_REVIEWS = 2000", "MAX_REVIEWS = 6")
                    cell.source = cell.source.replace("ALLOW_PAID_API_CALLS = False", "ALLOW_PAID_API_CALLS = True")
                    cell.source += '''
# Verification-only fake responses: no real key, network, or billing.
from access_app import classification as checked_api
from access_app import workshop as checked_workshop
def fake_response(review, model, api_key):
    return dict(
        classification={a: dict(state="no_mention", evidence="") for a in checked_api.ASPECTS},
        requested_model=model, returned_model=model, response_id="mock-notebook-response",
        usage={"input_tokens": 1}, classified_at="2026-11-15T00:00:00+00:00",
    )
checked_api.classify = fake_response
'''
            elif args.method == "llm" and "predictions, classification = prompt_llm_classification(" in cell.source:
                # IPython reinstalls its password handler between cells, so replace
                # it in the same cell that exercises the masked-prompt helper.
                cell.source = 'checked_workshop.getpass.getpass = lambda prompt: "sk-fake-notebook-verification-only"\n' + cell.source
        NotebookClient(notebook, timeout=120, kernel_name="python3", resources={"metadata": {"path": str(work)}}).execute()
        metadata = json.loads((work / "outputs/workshop" / args.method / "run_metadata.json").read_text())
        assert metadata["synthetic_input"] is True
        assert metadata["input"]["retained_reviews"] == (6 if args.method == "llm" else 120)
        assert metadata["classification"]["method"] == args.method
        assert not metadata["evaluation"]["aspects"]
        assert (work / "outputs/workshop" / args.method / "classification_results.zip").is_file()
        assert not (work / "access_app/data/classified_locations.json").exists()
    print(f"Notebook verified: {args.method}; invented reviews; no saved predictions or real API calls.")


if __name__ == "__main__":
    main()
