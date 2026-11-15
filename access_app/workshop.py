"""Fresh review-classification experiments for the Binder notebook.

Never reads bundled predictions or private manifests. Optional API classification
uses a user's masked, in-memory key and explicit request-count limit.
"""

import csv
import getpass
import hashlib
import importlib.metadata
import json
import platform
import random
import re
import subprocess
import zipfile
from pathlib import Path

import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.model_selection import GroupShuffleSplit

from .reviews import notebook_baseline
from .schema import ASPECTS, SERVICES, STATES, aggregate_status, utc_now, validate_bundle

ROOT = Path(__file__).resolve().parents[1]
ALL_STATES = ("no_mention",) + STATES
LABEL_COLUMNS = ["record_id", "aspect", "state", "evidence", "annotator_id", "provenance", "adjudicated"]


def sha256(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def record_id(place_id, review):
    return hashlib.sha256((place_id + "|" + review).encode()).hexdigest()[:24]


def keyword_rubric():
    return notebook_baseline(ROOT / "Access_Beyond_the_Map.ipynb")


def load_reviews(path, *, max_reviews=2000, seed=42):
    """Stream and sample a CSV without loading reviewer profiles or owner replies."""
    if type(max_reviews) is not int or not 1 <= max_reviews <= 10000:
        raise ValueError("max_reviews must be between 1 and 10000; use the full analysis notebook for larger jobs.")
    baseline, _ = keyword_rubric()
    path = Path(path)
    rng, selected, seen = random.Random(seed), [], set()
    audit = dict(raw_rows=0, empty_rows=0, duplicate_rows=0, oversized_rows=0, eligible_rows=0)
    csv.field_size_limit(20_000_000)
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not {"place_id", "review"} <= set(reader.fieldnames or []):
            raise ValueError("Reviews CSV must have place_id and review columns.")
        for row in reader:
            audit["raw_rows"] += 1
            pid, review = (row.get("place_id") or "").strip(), (row.get("review") or "").strip()
            if not pid or not review:
                audit["empty_rows"] += 1
                continue
            if len(review) > 65536:
                audit["oversized_rows"] += 1
                continue
            normalized = " ".join(re.sub(r"[^\w\s]", " ", review.casefold()).split())
            key = hashlib.sha256(normalized.encode()).digest()
            if key in seen:
                audit["duplicate_rows"] += 1
                continue
            seen.add(key)
            service = (row.get("service") or "").strip().lower()
            if service not in SERVICES:
                service = baseline["service_group"](row.get("category") or "")
            item = dict(record_id=record_id(pid, review), place_id=pid, review=review,
                        name=(row.get("place_name") or row.get("name") or pid).strip(),
                        address=(row.get("address") or "").strip(), service=service,
                        date=(row.get("review_date") or "").strip())
            audit["eligible_rows"] += 1
            if len(selected) < max_reviews:
                selected.append(item)
            else:
                position = rng.randrange(audit["eligible_rows"])
                if position < max_reviews:
                    selected[position] = item
    if not selected:
        raise ValueError("No nonempty, eligible reviews found.")
    frame = pd.DataFrame(selected).sort_values("record_id").reset_index(drop=True)
    conflicting_services = 0
    for pid, rows in frame.groupby("place_id", sort=True):
        known = sorted(set(rows.service) & set(SERVICES))
        conflicting_services += int(len(known) > 1)
        # Inconsistent service metadata remains classifiable, but is not exported
        # as a made-up service type in the app's narrower interchange format.
        frame.loc[rows.index, "service"] = known[0] if len(known) == 1 else "other"
    audit.update(retained_reviews=len(frame), locations=int(frame.place_id.nunique()),
                 source_sha256=sha256(path), source_bytes=path.stat().st_size,
                 source_file=path.name, max_reviews=max_reviews, seed=seed, conflicting_service_locations=conflicting_services,
                 deduplication="Global normalized exact text; no near-duplicate detection.",
                 sampling="Seeded reservoir sample after deduplication; CSV row order matters.")
    return frame, audit


def write_demo_csv(path):
    """Invented input text, not the app's reviews or saved classifications."""
    examples = [
        "The wheelchair entrance was blocked. The interpreter was unavailable.",
        "The ramp helped entry. A hearing loop was available. Translation helped.",
        "The appointment was easy. The fee waiver helped us afford the visit.",
        "The hearing loop was broken. We waited for hours and could not afford the unexpected fee.",
        "The ramp worked but was sometimes blocked. The interpreter was sometimes unavailable.",
        "The staff wore blue uniforms. We discussed the weather.",
    ]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["place_id", "place_name", "service", "review"])
        writer.writeheader()
        for place in range(20):
            for index, review in enumerate(examples):
                writer.writerow(dict(place_id=f"invented_{place:02}", place_name=f"Invented clinic {place}",
                                     service="clinic", review=f"{review} Reference {place}/{index}."))
    return path


def split_reviews(frame, *, seed=42):
    result = frame.copy()
    result["split"] = "train"
    if result.place_id.nunique() >= 5:
        _, heldout = next(GroupShuffleSplit(n_splits=1, test_size=.2, random_state=seed)
                          .split(result, groups=result.place_id))
        result.loc[result.index[heldout], "split"] = "test"
    return result


def annotation_template(frame):
    rows = frame[["record_id", "place_id", "review", "split"]].merge(pd.DataFrame({"aspect": ASPECTS}), how="cross")
    for field in ["state", "evidence", "annotator_id", "provenance", "adjudicated"]:
        rows[field] = ""
    return rows


def load_human_labels(path, frame):
    """Check annotation format/source spans; human provenance is self-declared."""
    if not path:
        return pd.DataFrame(columns=["record_id", *ASPECTS])
    rows = pd.read_csv(path, dtype=str, keep_default_na=False)
    if not set(LABEL_COLUMNS) <= set(rows):
        raise ValueError(f"Labels CSV requires {LABEL_COLUMNS}.")
    rows = rows[rows.provenance.eq("human") & rows.adjudicated.str.lower().isin(["true", "1", "yes"])].copy()
    if rows.empty:
        raise ValueError("No adjudicated human annotations found; fill the annotation template first.")
    if rows.duplicated(["record_id", "aspect"]).any():
        raise ValueError("Duplicate annotations: adjudicate to one label per review/aspect.")
    if not rows.aspect.isin(ASPECTS).all() or not rows.state.isin(ALL_STATES).all():
        raise ValueError("Unknown accessibility aspect or classification state.")
    texts = frame.set_index("record_id").review.to_dict()
    for row in rows.itertuples():
        if row.record_id not in texts:
            raise ValueError("Labels refer to reviews outside this sample; keep input, seed and sample limit unchanged.")
        if not row.annotator_id.strip():
            raise ValueError("Human labels need an annotator_id.")
        if row.state == "no_mention":
            if row.evidence:
                raise ValueError("no_mention labels must have empty evidence.")
        elif not row.evidence.strip() or row.evidence not in texts[row.record_id]:
            raise ValueError("Label evidence must be an exact, nonempty source passage.")
    complete = rows.pivot(index="record_id", columns="aspect", values="state").reindex(columns=ASPECTS).dropna()
    if complete.empty:
        raise ValueError("Complete all five aspect labels for at least one review.")
    return complete.reset_index()


def classify_reviews(frame, *, method="keywords", label_source="keyword_rules", human_labels=None, seed=42):
    if method not in {"keywords", "tfidf_logreg"} or label_source not in {"keyword_rules", "human"}:
        raise ValueError("Choose keywords/tfidf_logreg and keyword_rules/human.")
    baseline, rubric_hash = keyword_rubric()
    support = {}
    mode = "keyword_rules" if method == "keywords" else label_source
    predicted = {}
    if method == "keywords":
        for aspect in ASPECTS:
            predicted[aspect] = [baseline["rule_state"](text, aspect) for text in frame.review]
    else:
        if not frame.split.eq("test").any():
            raise ValueError("TF-IDF requires at least five retained locations for a location-held-out split.")
        train = frame[frame.split.eq("train")].copy()
        if label_source == "human":
            if human_labels is None or human_labels.empty:
                raise ValueError("Human training requires your completed annotation CSV.")
            train = train.merge(human_labels, on="record_id", validate="one_to_one")
            if train.empty:
                raise ValueError("No complete human labels in the training partition.")
        else:
            for aspect in ASPECTS:
                train[aspect] = train.review.map(lambda text: baseline["rule_state"](text, aspect))
        vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1, max_features=20000, sublinear_tf=True)
        try:
            x_train = vectorizer.fit_transform(train.review)
        except ValueError as error:
            raise ValueError("Training text has no usable TF-IDF vocabulary.") from error
        x_all = vectorizer.transform(frame.review)
        for aspect in ASPECTS:
            counts = train[aspect].value_counts().to_dict()
            estimator = (DummyClassifier(strategy="most_frequent") if len(counts) == 1 else
                         LogisticRegression(C=1.0, class_weight="balanced", max_iter=1000, random_state=seed))
            estimator.fit(x_train, train[aspect])
            predicted[aspect] = estimator.predict(x_all)
            support[aspect] = dict(class_counts={k: int(v) for k, v in counts.items()},
                                   estimator=type(estimator).__name__, missing_states=sorted(set(ALL_STATES) - set(counts)))
    rows = []
    for index, row in enumerate(frame.itertuples()):
        for aspect in ASPECTS:
            state = str(predicted[aspect][index])
            # Preserve every relevant sentence (including potential counterevidence).
            sentences = re.split(r"(?<=[.!?])\s+", row.review)
            relevant = [s for s in sentences if re.search(baseline["TERMS"][aspect], s, re.I)]
            # A contiguous span is always copied from the source. If no rule matches a
            # statistical prediction, show the full review for manual inspection.
            quote = ""
            if state != "no_mention":
                quote = row.review[row.review.index(relevant[0]):row.review.rindex(relevant[-1]) + len(relevant[-1])] if relevant else row.review
            rows.append(dict(record_id=row.record_id, place_id=row.place_id, aspect=aspect,
                             state=state, evidence=quote, split=row.split, method=method, label_source=mode))
    return pd.DataFrame(rows), dict(method=method, training_label_source=mode,
        rubric_sha256=rubric_hash, training_support=support,
        hyperparameters=dict(ngram_range=[1, 2], max_features=20000, C=1.0, class_weight="balanced", max_iter=1000),
        evidence_method="Contiguous rule-relevant source sentences, or full review; source fidelity is not label accuracy.")


def evaluate(predictions, human_labels):
    report = dict(status="NOT EVALUATED: independent human test annotations required.", complete_test_reviews=0, aspects={})
    if human_labels.empty:
        return report
    test = predictions[predictions.split.eq("test")]
    labeled_ids = set(test.record_id) & set(human_labels.record_id)
    if not labeled_ids:
        return report
    report.update(status="Evaluated on supplied human annotations from held-out locations; annotation independence is user-declared.",
                  complete_test_reviews=len(labeled_ids))
    for aspect in ASPECTS:
        paired = test[test.aspect.eq(aspect)].merge(human_labels[["record_id", aspect]], on="record_id")
        report["aspects"][aspect] = classification_report(paired[aspect], paired.state, labels=list(ALL_STATES), output_dict=True, zero_division=0)
    return report


def _llm_checkpoints(frame, model, cache_dir):
    from .classification import cache_identity, validate_classification
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,90}", model):
        raise ValueError("Enter a valid OpenAI model ID available to your account.")
    cache_dir = Path(cache_dir)
    results, pending = {}, []
    for row in frame.itertuples():
        identity = cache_identity(row.review, model)
        path = cache_dir / (identity + ".json")
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            if saved.get("cache_identity") != identity or saved.get("requested_model") != model:
                raise ValueError("LLM checkpoint does not match the current input/model.")
            validate_classification(saved["classification"], row.review)
            results[row.record_id] = saved
        else:
            pending.append((row, identity, path))
    return results, pending


def llm_preflight(frame, *, model, cache_dir, max_requests=20):
    if type(max_requests) is not int or not 0 <= max_requests <= 10000:
        raise ValueError("max_requests must be between 0 and 10000.")
    results, pending = _llm_checkpoints(frame, model, cache_dir)
    return dict(reviews=len(frame), cached_reviews=len(results), new_requests=len(pending),
                request_limit=max_requests, within_limit=len(pending) <= max_requests,
                model=model, paid_calls_made=0)


def classify_with_llm(frame, *, api_key, model, cache_dir, max_requests=20):
    """Use the user's OpenAI key with validated per-review checkpoints; no retries."""
    from .classification import RUBRIC, atomic_json, classify, digest, validate_classification
    preflight = llm_preflight(frame, model=model, cache_dir=cache_dir, max_requests=max_requests)
    if not preflight["within_limit"]:
        raise ValueError(f"Need {preflight['new_requests']} new API requests, above your limit of {max_requests}. Lower MAX_REVIEWS or explicitly raise LLM_MAX_NEW_REQUESTS.")
    results, pending = _llm_checkpoints(frame, model, cache_dir)
    if pending and not api_key:
        raise ValueError("Enter your own OpenAI API key to classify uncached reviews.")
    for index, (row, identity, path) in enumerate(pending, start=1):
        item = classify(row.review, model, api_key)
        validate_classification(item["classification"], row.review)
        # Save only analysis/provenance fields, never request headers or credentials.
        saved = {field: item[field] for field in ["classification", "requested_model", "returned_model", "response_id", "usage", "classified_at"]}
        saved["cache_identity"] = identity
        atomic_json(path, saved)
        results[row.record_id] = saved
        print(f"Validated {index}/{len(pending)} new LLM results ({len(results)}/{len(frame)} total).", flush=True)
    records = []
    for row in frame.itertuples():
        for aspect in ASPECTS:
            label = results[row.record_id]["classification"][aspect]
            records.append(dict(record_id=row.record_id, place_id=row.place_id, aspect=aspect,
                state=label["state"], evidence=label["evidence"], split=row.split,
                method="llm", label_source="llm_direct_classification"))
    provenance = {rid: {key: item[key] for key in ["requested_model", "returned_model", "response_id", "usage", "classified_at"]}
                  for rid, item in results.items()}
    return pd.DataFrame(records), dict(method="llm", training_label_source="llm_direct_classification",
        model=model, training_support={}, rubric_sha256=digest(RUBRIC), rubric=RUBRIC,
        new_requests=len(pending), cached_reviews=preflight["cached_reviews"], request_limit=max_requests,
        response_provenance=provenance,
        evidence_method="Model selects numbered source passages; exact original text is copied and validated locally.")


def prompt_llm_classification(frame, *, model, cache_dir, max_requests=20, allow_paid_calls=False):
    """Masked input stays out of notebook source, outputs, environment and exports."""
    preflight = llm_preflight(frame, model=model, cache_dir=cache_dir, max_requests=max_requests)
    print(json.dumps(preflight, indent=2))
    if not preflight["within_limit"]:
        raise ValueError("API request limit exceeded. Lower MAX_REVIEWS or explicitly raise LLM_MAX_NEW_REQUESTS; no key requested and no calls made.")
    if preflight["new_requests"] and allow_paid_calls is not True:
        raise ValueError("Set ALLOW_PAID_API_CALLS = True to use your own API billing. No calls made.")
    api_key = ""
    try:
        if preflight["new_requests"]:
            api_key = getpass.getpass("Your OpenAI API key (hidden; kept in memory for this run): ").strip()
        return classify_with_llm(frame, api_key=api_key, model=model, cache_dir=cache_dir, max_requests=max_requests)
    finally:
        api_key = ""


def frontend_bundle(frame, predictions, metadata, *, synthetic=False):
    # Reviews-only export: no invented coordinates, closure verification or matching.
    eligible = frame[frame.service.isin(SERVICES)]
    places, aspects, evidence = [], [], []
    dates = pd.to_datetime(frame.date, errors="coerce", utc=True, format="mixed")
    date_by_id = {rid: None if pd.isna(date) else date.isoformat() for rid, date in zip(frame.record_id, dates)}
    selected = predictions[predictions.place_id.isin(eligible.place_id)]
    for pid, rows in eligible.groupby("place_id", sort=True):
        item = rows.iloc[0]
        places.append(dict(place_id=pid, name=item["name"], service=item.service, address=item.address,
                           lat=None, lon=None, closure_status="not_verified_open", sampled_reviews=len(rows)))
        for aspect in ASPECTS:
            reports = selected[selected.place_id.eq(pid) & selected.aspect.eq(aspect)]
            counts = reports.state.value_counts()
            barrier, positive, mixed = (int(counts.get(s, 0)) for s in STATES)
            aspects.append(dict(place_id=pid, aspect=aspect, sampled_reviews=len(rows), barrier_reports=barrier,
                positive_reports=positive, uncertain_reports=mixed, status=aggregate_status(barrier, positive, mixed),
                first_date=None, last_date=None))
            evidence.extend(dict(record_id=r.record_id, place_id=pid, aspect=aspect, state=r.state,
                text=r.evidence, date=date_by_id[r.record_id], score=None, barrier_score=None)
                for r in reports.itertuples() if r.state != "no_mention")
    payload = dict(schema_version=1, dataset=dict(mode="synthetic" if synthetic else "real", generated_at=utc_now(),
        model=f"workshop_{metadata['classification']['method']}", label_mode=metadata["classification"]["training_label_source"],
        evaluation_status=metadata["evaluation"]["status"], metrics=metadata["evaluation"],
        source_manifest={metadata["input"]["source_file"]: dict(sha256=metadata["input"]["source_sha256"])},
        selection=metadata["classification"],
        coverage_note=f"Reviews-only workshop sample. No Places join or coordinates. {len(eligible)} of {len(frame)} sampled reviews have a supported service category; all reviews remain in classifications.csv. Historical reports, not verified conditions."),
        places=places, aspects=aspects, evidence=evidence)
    validate_bundle(payload)
    return payload


def export_run(frame, predictions, audit, classification, human_labels, output_dir, *, seed=42, synthetic=False, labels_path=None):
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    evaluation = evaluate(predictions, human_labels)
    try:
        revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        revision = None
    metadata = dict(generated_at=utc_now(), synthetic_input=synthetic, input=audit, seed=seed,
        classification=classification, evaluation=evaluation, git_commit=revision,
        source_code_sha256={name: sha256(path) for name, path in {
            "workshop.py": Path(__file__), "classification.py": ROOT / "access_app/classification.py",
            "chat.py": ROOT / "access_app/chat.py", "Access_Beyond_the_Map.ipynb": ROOT / "Access_Beyond_the_Map.ipynb",
            "Classify_Your_Own_Data.ipynb": ROOT / "Classify_Your_Own_Data.ipynb"}.items() if path.is_file()},
        labels_sha256=sha256(labels_path) if labels_path else None,
        environment=dict(python=platform.python_version(), platform=platform.platform(),
            packages={name: importlib.metadata.version(name) for name in ["numpy", "pandas", "scipy", "scikit-learn", "joblib"]}),
        split="80/20 location-held-out with fixed seed when at least five locations; otherwise training-only keyword run.",
        limitations=["Keyword-generated training labels are provisional, not human ground truth.",
                      "No tuning on test data. TF-IDF vocabulary and classifier fit on training reviews only.",
                      "Only normalized exact duplicates are removed; near duplicates may remain.",
                      "Live LLM outputs can vary; cache files and exported classifications preserve this run.",
                      "Public Binder has limited resources and temporary storage. Download outputs before leaving."])
    files = []
    tables = {"reviews.csv": frame, "classifications.csv": predictions,
              "split_manifest.csv": frame[["record_id", "place_id", "split"]],
              "annotation_template.csv": annotation_template(frame)}
    for name, table in tables.items():
        table.to_csv(destination / name, index=False)
        files.append(name)
    baseline, _ = keyword_rubric()
    documents = {"run_metadata.json": metadata, "evaluation.json": evaluation,
                 "keyword_rubric.json": {name: baseline[name] for name in ["TERMS", "NEG", "POS", "MIX"]}}
    bundle = frontend_bundle(frame, predictions, metadata, synthetic=synthetic)
    if bundle["places"]:
        documents["frontend_results.json"] = bundle
    else:
        (destination / "frontend_results.json").unlink(missing_ok=True)
    for name, payload in documents.items():
        (destination / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
        files.append(name)
    archive = destination / "classification_results.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for name in files:
            output.write(destination / name, arcname=name)
        if classification["method"] == "llm":
            from .classification import cache_identity
            for row in frame.itertuples():
                name = cache_identity(row.review, classification["model"]) + ".json"
                output.write(destination / "cache" / name, arcname="cache/" + name)
    return metadata, archive
