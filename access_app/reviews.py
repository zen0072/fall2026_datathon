"""Explicit reviews-only screening while the organizer Places file is unavailable.

Uses the notebook's existing keyword baseline. It does not fit a model, create
coordinates, substitute for the Places join, or report independent accuracy.
"""

import ast
import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from .schema import ASPECTS, QUESTIONS, AppError, timestamp, utc_now, validate_bundle


def notebook_baseline(path):
    notebook = json.loads(Path(path).read_text(encoding="utf-8"))
    wanted = {"service_group", "rule_state", "evidence_for"}
    constants = {"TERMS", "NEG", "POS", "MIX"}
    nodes = []
    found = set()
    for cell in notebook["cells"]:
        if cell["cell_type"] != "code" or "".join(cell["source"]).lstrip().startswith("%"):
            continue
        for node in ast.parse("".join(cell["source"])).body:
            if isinstance(node, ast.FunctionDef) and node.name in wanted:
                nodes.append(node)
                found.add(node.name)
            elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id in constants:
                ast.literal_eval(node.value)
                nodes.append(node)
                found.add(node.targets[0].id)
    if found != wanted | constants:
        raise AppError("The notebook's keyword baseline has changed; review the reviews-only adapter.")
    namespace = {"re": re}
    tree = ast.Module(body=nodes, type_ignores=[])
    exec(compile(tree, str(path), "exec"), namespace)
    baseline_hash = hashlib.sha256(ast.dump(tree).encode()).hexdigest()
    return namespace, baseline_hash


def build_reviews_bundle(source, notebook):
    source = Path(source)
    baseline, baseline_hash = notebook_baseline(notebook)
    places = {}
    categories = defaultdict(set)
    raw_rows = 0
    required = {"place_id", "place_name", "category", "review", "review_date"}
    csv.field_size_limit(16 * 1024 * 1024)
    # Parse whitelisted fields only into the analysis state; no reviewer identity fields.
    with source.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not required <= set(reader.fieldnames or []):
            raise AppError("The reviews CSV lacks the required business, category, or review fields.")
        for row in reader:
            raw_rows += 1
            pid = row["place_id"].strip()
            if not pid:
                continue
            p = places.setdefault(pid, {"place_id": pid, "name": "", "address": ""})
            # Preserve the first available business metadata; never use reviewer fields.
            for field, column in (("name", "place_name"), ("address", "address")):
                if not p[field] and row.get(column, "").strip():
                    p[field] = row[column].strip()
            if row["category"].strip():
                categories[pid].add(row["category"].strip())
    eligible = {}
    for pid, p in places.items():
        service = baseline["service_group"](" | ".join(sorted(categories[pid])))
        if service != "other" and p["name"]:
            eligible[pid] = {**p, "service": service, "lat": None, "lon": None,
                             "closure_status": "not_verified_open", "sampled_reviews": 0}
    aggregates = {}
    evidence = []
    seen = set()
    unknown_dates = 0
    duplicate_rows = 0
    raw_target_rows = 0
    with source.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            pid = row["place_id"].strip()
            review = row["review"].strip()
            if pid not in eligible or not review:
                continue
            raw_target_rows += 1
            # Normalize case/punctuation for exact duplicate screening across the file,
            # as in the notebook. No approximate deduplication or holdout claims here.
            normalized = " ".join(re.sub(r"[^\w\s]", " ", review.casefold()).split())
            if normalized in seen:
                duplicate_rows += 1
                continue
            seen.add(normalized)
            rid = hashlib.sha256((pid + "|" + review).encode()).hexdigest()[:24]
            try:
                review_date = timestamp(row["review_date"].strip(), "review date")
            except AppError:
                review_date = None
            unknown_dates += int(review_date is None)
            eligible[pid]["sampled_reviews"] += 1
            for aspect in ASPECTS:
                key = (pid, aspect)
                a = aggregates.setdefault(key, {"place_id": pid, "aspect": aspect, "sampled_reviews": 0,
                    "barrier_reports": 0, "positive_reports": 0, "uncertain_reports": 0,
                    "first_date": None, "last_date": None, "verification_question": QUESTIONS[aspect]})
                a["sampled_reviews"] += 1
                if review_date:
                    a["first_date"] = min(a["first_date"] or review_date, review_date)
                    a["last_date"] = max(a["last_date"] or review_date, review_date)
                state = baseline["rule_state"](review, aspect)
                field = {"barrier_reported": "barrier_reports", "positive_access": "positive_reports", "unclear_or_mixed": "uncertain_reports"}.get(state)
                if field:
                    a[field] += 1
                    evidence.append({"record_id": rid, "place_id": pid, "aspect": aspect, "state": state,
                        "text": baseline["evidence_for"](review, aspect), "date": review_date,
                        "score": None, "barrier_score": None})
    retained_places = [p for p in eligible.values() if p["sampled_reviews"]]
    source_hash = hashlib.sha256()
    with source.open("rb") as stream:
        for block in iter(lambda: stream.read(2**20), b""):
            source_hash.update(block)
    selection = {"source_mode": "reviews_only", "baseline_sha256": baseline_hash,
        "raw_review_rows": raw_rows, "raw_unique_places": len(places),
        "places_with_category": sum(bool(values) for values in categories.values()), "target_review_rows_before_deduplication": raw_target_rows,
        "normalized_duplicates_removed": duplicate_rows, "unknown_review_dates": unknown_dates,
        "retained_review_counts_by_service": {service: sum(p["sampled_reviews"] for p in retained_places if p["service"] == service) for service in ("clinic", "pharmacy", "grocery")},
        "training": "No model fitting or train/validation/test split. Notebook keyword baseline only.",
        "geographic_scope": "Unfiltered source businesses, including addresses outside the Bay Area; no regional membership inferred.",
        "deduplication": "Normalized exact text only; approximate duplicate removal not run.",
        "missing_places": "Organizer Places download blocked by Google Drive quota; no two-dataset join.",
    }
    payload = {"schema_version": 1, "dataset": {"mode": "real", "generated_at": utc_now(),
        "model": "notebook_keyword_baseline", "label_mode": "provisional_rule_labels",
        "evaluation_status": "NOT EVALUATED: reviews-only keyword screening; independent human labels unavailable.",
        "coverage_note": "Reviews-only subset identified using available review categories. Many businesses lack categories and cannot be scoped. Business names/addresses come from Reviews; coordinates and closure status are unknown. Region is unfiltered and includes businesses outside the Bay Area. The full Places dataset and two-dataset join are still pending. Reports are historical and unverified.",
        "source_manifest": {source.name: {"sha256": source_hash.hexdigest(), "bytes": source.stat().st_size,
            "drive_file_id": "1Ov_U0PP9i7DYmrtvnbPBLtboDSOo1SwB",
            "source_url": "https://drive.google.com/file/d/1Ov_U0PP9i7DYmrtvnbPBLtboDSOo1SwB/view"}},
        "metrics": {"n_labeled_test": 0, "models": {}}, "selection": selection},
        "places": retained_places, "aspects": list(aggregates.values()), "evidence": evidence}
    validate_bundle(payload)
    return payload
