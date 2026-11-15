"""Preflight or run direct LLM classification on the current map's review cohort.

Without --run, makes zero provider calls. --run uses paid OpenAI API requests;
--limit 20 provides a bounded pilot. Completed reviews are validated and cached.
Requires local raw Reviews CSV and the historical retained split manifest.
"""

import argparse
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from access_app.bundled import BUNDLED_RESULTS
from access_app.chat import DEFAULT_CHAT_MODEL
from access_app.classification import (RUBRIC, atomic_json, cache_identity, classify,
                                       digest, export_bundle, file_sha, load_cohort,
                                       validate_classification)


def load_env(path):
    """Read only literal API key/model settings; never execute or print values."""
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, sep, value = line.removeprefix("export ").partition("=")
        name, value = name.strip(), value.strip()
        if sep and name in {"OPENAI_API_KEY", "ACCESS_CLASSIFY_MODEL"}:
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            if value:
                os.environ.setdefault(name, value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviews", type=Path, default=ROOT / "data/google_maps_reviews.csv")
    parser.add_argument("--manifest", type=Path, default=ROOT / "outputs/real/split_manifest.csv")
    parser.add_argument("--baseline", type=Path, default=BUNDLED_RESULTS)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/llm")
    parser.add_argument("--env-file", type=Path, help="Ignored local .env with OPENAI_API_KEY; never executed")
    parser.add_argument("--model", help="Responses API model supporting structured outputs")
    parser.add_argument("--limit", type=int, help="Only classify this many reviews; output explicitly labeled partial")
    parser.add_argument("--run", action="store_true", help="Make paid API calls for uncached selected reviews")
    parser.add_argument("--workers", type=int, default=4, help="Concurrent requests (1–8; default 4)")
    parser.add_argument("--db", type=Path, help="Import completed output; stop any app using this database first")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    if not 1 <= args.workers <= 8:
        parser.error("--workers must be between 1 and 8")
    if args.db and not args.run:
        parser.error("--db requires --run")
    status = {"state": "preparing", "live_calls_attempted": 0, "cached_reviews": 0,
              "completed_reviews": 0, "blockers": []}
    destination = args.output_dir / "run_status.json"
    try:
        if args.env_file:
            load_env(args.env_file)
        model = args.model or os.environ.get("ACCESS_CLASSIFY_MODEL") or DEFAULT_CHAT_MODEL
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,90}", model):
            raise ValueError("Invalid model ID.")
        status.update(model=model, rubric_sha256=digest(RUBRIC))
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        all_reviews = load_cohort(args.reviews, args.manifest, baseline)
        reviews = all_reviews[:args.limit] if args.limit else all_reviews
        status.update(cohort_reviews=len(all_reviews), selected_reviews=len(reviews),
                      cohort_locations=len(baseline["places"]),
                      selected_locations=len({r["place_id"] for r in reviews}),
                      partial_review_coverage=len(reviews) != len(all_reviews),
                      review_characters=sum(len(r["review"]) for r in reviews))
        cache_dir = args.output_dir / "cache"
        results = {}
        for row in reviews:
            identity = cache_identity(row["review"], model)
            path = cache_dir / (identity + ".json")
            if path.exists():
                item = json.loads(path.read_text(encoding="utf-8"))
                if item.get("cache_identity") != identity:
                    raise ValueError("Checkpoint identity mismatch.")
                validate_classification(item["classification"], row["review"])
                results[row["record_id"]] = item
        status.update(cached_reviews=len(results), completed_reviews=len(results),
                      remaining_calls=len(reviews) - len(results))
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if status["remaining_calls"] and not api_key:
            status["blockers"].append("OPENAI_API_KEY is not configured for this process; the browser chatbot key is separate.")
        if not args.run:
            status["state"] = "blocked_missing_configuration" if status["blockers"] else "ready_for_run"
            atomic_json(destination, status)
            print(json.dumps(status, indent=2))
            return 2 if status["blockers"] else 0
        if status["blockers"]:
            status["state"] = "blocked_missing_configuration"
            atomic_json(destination, status)
            print(json.dumps(status, indent=2))
            return 2
        status["state"] = "running"
        atomic_json(destination, status)
        def classify_and_checkpoint(row):
            item = classify(row["review"], model, api_key)
            identity = cache_identity(row["review"], model)
            item["cache_identity"] = identity
            atomic_json(cache_dir / (identity + ".json"), item)
            return row["record_id"], item

        remaining = [row for row in reviews if row["record_id"] not in results]
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            # Submit only one bounded group at a time; errors stop further groups.
            # Finish/checkpoint in-flight successes before reporting an error.
            for offset in range(0, len(remaining), args.workers):
                group = remaining[offset:offset + args.workers]
                status["live_calls_attempted"] += len(group)
                atomic_json(destination, status)
                futures = [pool.submit(classify_and_checkpoint, row) for row in group]
                failure = None
                for future in as_completed(futures):
                    try:
                        rid, item = future.result()
                        results[rid] = item
                    except Exception as error:
                        failure = error
                    status.update(completed_reviews=len(results), remaining_calls=len(reviews) - len(results))
                    atomic_json(destination, status)
                    print(f"Classified {len(results)}/{len(reviews)} reviews", flush=True)
                if failure:
                    raise failure
        bundle = export_bundle(baseline, reviews, results, model, file_sha(args.manifest))
        review_output = args.output_dir / ("review_classifications_PARTIAL_PRIVATE.json" if status["partial_review_coverage"] else "review_classifications_PRIVATE.json")
        atomic_json(review_output, {
            "model": model, "rubric_sha256": digest(RUBRIC),
            "partial_review_coverage": status["partial_review_coverage"],
            "reviews": [{"record_id": row["record_id"], "place_id": row["place_id"],
                         "date": row["date"], "review": row["review"], **results[row["record_id"]]}
                        for row in reviews],
        })
        # Pilot and complete exports have separate paths; pilots never replace a full export.
        filename = "frontend_results_PARTIAL_PRIVATE.json" if status["partial_review_coverage"] else "frontend_results_PRIVATE.json"
        output = args.output_dir / filename
        atomic_json(output, bundle)
        status.update(state="complete", output_file=str(output), locations=len(bundle["places"]),
                      evidence_excerpts=len(bundle["evidence"]), review_output_file=str(review_output))
        if args.db:
            from access_app.database import Store
            store = Store(args.db)
            try:
                status["imported_snapshot_id"] = store.import_bundle(bundle)["snapshot_id"]
            finally:
                store.close()
        atomic_json(destination, status)
        print(json.dumps(status, indent=2))
        return 0
    except KeyboardInterrupt:
        status.update(state="interrupted", blockers=["Interrupted; rerun to reuse validated checkpoints."])
    except Exception as error:
        # Provider exceptions are sanitized inside classify; never expose request headers.
        status.update(state="failed", blockers=[str(error)])
    atomic_json(destination, status)
    print(json.dumps(status, indent=2))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
