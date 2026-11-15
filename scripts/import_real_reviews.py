"""Build and optionally import an explicitly partial, untrained real-review run."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from access_app.database import Store
from access_app.reviews import build_reviews_bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "data/google_maps_reviews.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/reviews_only/frontend_results_PRIVATE.json")
    parser.add_argument("--db", type=Path, help="Import into this database; stop the app first")
    args = parser.parse_args()
    bundle = build_reviews_bundle(args.source, ROOT / "Access_Beyond_the_Map.ipynb")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(bundle, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "locations": len(bundle["places"]),
        "retained_reviews": sum(p["sampled_reviews"] for p in bundle["places"]),
        "evidence_excerpts": len(bundle["evidence"]), "selection": bundle["dataset"]["selection"]}, indent=2))
    if args.db:
        store = Store(args.db)
        try:
            metadata = store.import_bundle(bundle)
            print("Imported snapshot:", metadata["snapshot_id"])
        finally:
            store.close()


if __name__ == "__main__":
    main()
