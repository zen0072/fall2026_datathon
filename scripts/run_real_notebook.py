"""Execute the actual notebook on cached real CSVs and optionally import results.

The explorer uses a requested trained candidate, with the validation comparison
winner retained separately. Notebook installation magics are skipped locally.
"""

import argparse
import contextlib
import hashlib
import json
import os
import re
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prediction-model", choices=("tfidf_word", "tfidf_word_char", "validation_winner"), default="tfidf_word")
    parser.add_argument("--db", type=Path, help="Import only after a successful run; stop the app first")
    args = parser.parse_args()
    os.chdir(ROOT)
    os.environ.setdefault("MPLBACKEND", "Agg")
    os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "outputs/.mpl-cache"))
    output = ROOT / "outputs/real"
    output.mkdir(parents=True, exist_ok=True)
    path = ROOT / "Access_Beyond_the_Map.ipynb"
    notebook_bytes = path.read_bytes()
    notebook = json.loads(notebook_bytes)
    (output / "notebook_source.ipynb").write_bytes(notebook_bytes)
    status = {"mode": "real", "requested_prediction_model": args.prediction_model,
              "notebook_sha256": hashlib.sha256(notebook_bytes).hexdigest(), "state": "running"}
    status_path = output / "run_status.json"
    namespace = {"__name__": "__main__"}
    started = time.monotonic()
    try:
        with (output / "run_PRIVATE.log").open("w", encoding="utf-8") as log:
            for index, cell in enumerate(notebook["cells"]):
                source = "".join(cell["source"])
                if cell["cell_type"] != "code" or source.lstrip().startswith("%pip"):
                    continue
                if index == 4:
                    source = re.sub(r'^FRONTEND_MODEL = "[^"]*"', f'FRONTEND_MODEL = "{args.prediction_model}"', source, count=1, flags=re.M)
                    source = source.replace('DATA_DIR = Path("/content/data" if Path("/content").exists() else "data")', 'DATA_DIR = Path("data")')
                status.update(cell_index=index, elapsed_seconds=round(time.monotonic() - started, 2))
                status_path.write_text(json.dumps(status, indent=2))
                print(f"Running notebook cell {index} ({status['elapsed_seconds']}s elapsed)", flush=True)
                with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                    exec(compile(source, f"{path.name}:cell_{index}", "exec"), namespace)
                log.flush()
        from access_app.schema import validate_bundle
        payload = json.loads((output / "frontend_results_PRIVATE.json").read_text(encoding="utf-8"))
        validate_bundle(payload)
        status.update(state="complete", elapsed_seconds=round(time.monotonic() - started, 2),
            model=payload["dataset"]["model"], label_mode=payload["dataset"]["label_mode"],
            comparison_winner=payload["dataset"]["selection"]["winner"],
            locations=len(payload["places"]), reviews=sum(p["sampled_reviews"] for p in payload["places"]),
            mapped_locations=sum(p["lat"] is not None and p["lon"] is not None for p in payload["places"]),
            evidence_excerpts=len(payload["evidence"]))
        if args.db:
            from access_app.database import Store
            store = Store(args.db)
            try:
                status["imported_snapshot_id"] = store.import_bundle(payload)["snapshot_id"]
            finally:
                store.close()
        status_path.write_text(json.dumps(status, indent=2))
        print(json.dumps(status, indent=2), flush=True)
    except Exception as error:
        status.update(state="failed", error_type=type(error).__name__, error=str(error))
        status_path.write_text(json.dumps(status, indent=2))
        with (output / "run_PRIVATE.log").open("a", encoding="utf-8") as log:
            traceback.print_exc(file=log)
        print(f"Notebook stopped: {type(error).__name__}: {error}. See {status_path}.", flush=True)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
