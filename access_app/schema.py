"""Versioned interchange format between the Colab notebook and the application."""

import json
import math
from datetime import datetime, timezone

ASPECTS = ("physical", "sensory", "language", "financial", "time")
SERVICES = ("clinic", "pharmacy", "grocery")
STATES = ("barrier_reported", "positive_access", "unclear_or_mixed")
WORK_STATUSES = ("To verify", "In progress", "Resolved")
ACTION_TYPES = ("Unassessed", "Physical improvement", "Service change", "Information update", "No change needed")
QUESTIONS = {
    "physical": "Confirm whether entrances and relevant facilities offer step-free access.",
    "sensory": "Confirm which sensory and communication accommodations are available.",
    "language": "Confirm interpreter or language-assistance availability.",
    "financial": "Confirm fees and assistance options that affect access.",
    "time": "Confirm hours, wait times and appointment availability.",
}


class AppError(Exception):
    def __init__(self, message, status=400, **details):
        super().__init__(message)
        self.status = status
        self.details = details


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def text(value, field, maximum=500, allow_empty=False):
    if not isinstance(value, str) or len(value) > maximum or (not allow_empty and not value.strip()):
        raise AppError(f"{field} must be {'a string' if allow_empty else 'a nonempty string'} of at most {maximum} characters.")
    return value.strip()


def integer(value, field, minimum=0):
    if type(value) is not int or value < minimum:
        raise AppError(f"{field} must be an integer of at least {minimum}.")
    return value


def number(value, field, lower, upper, nullable=False):
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not lower <= value <= upper:
        raise AppError(f"{field} must be between {lower} and {upper}.")
    return float(value)


def choice(value, values, field):
    if value not in values:
        raise AppError(f"Invalid {field}; choose one of: {', '.join(values)}.")
    return value


def timestamp(value, field):
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise AppError(f"{field} must be an ISO date or null.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise AppError(f"Invalid ISO date in {field}.") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def aggregate_status(barrier, positive, mixed):
    if mixed or (barrier and positive):
        return "conflicting_or_unclear"
    if barrier:
        return "reported_barrier"
    if positive:
        return "positive_evidence"
    return "insufficient_evidence"


def validate_bundle(payload):
    """Validate and whitelist fields before starting a database transaction."""
    if not isinstance(payload, dict) or type(payload.get("schema_version")) is not int or payload["schema_version"] != 1:
        raise AppError("Expected an Access Beyond the Map results file with schema_version 1.")
    dataset = payload.get("dataset")
    if not isinstance(dataset, dict):
        raise AppError("Missing dataset metadata.")
    mode = choice(dataset.get("mode"), ("real", "synthetic"), "dataset mode")
    metadata = {
        "mode": mode,
        "generated_at": timestamp(dataset.get("generated_at"), "generated_at"),
        "model": text(dataset.get("model"), "model", 100),
        "label_mode": text(dataset.get("label_mode"), "label_mode", 100),
        "evaluation_status": text(dataset.get("evaluation_status"), "evaluation_status", 500),
        "coverage_note": text(dataset.get("coverage_note", "Locations with matched, retained target-service reviews; not a complete service inventory."), "coverage_note", 1000),
    }
    for field in ("metrics", "source_manifest", "selection"):
        value = dataset.get(field, {})
        if not isinstance(value, dict):
            raise AppError(f"dataset.{field} must be an object.")
        metadata[field] = value
    try:
        json.dumps(metadata, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise AppError("Dataset metadata must contain finite, JSON-compatible values.") from error
    collections = {}
    for key in ("places", "aspects", "evidence"):
        rows = payload.get(key)
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise AppError(f"{key} must be an array of objects.")
        collections[key] = rows
    places, aspects, evidence = [], [], []
    ids = set()
    for row in collections["places"]:
        pid = text(row.get("place_id"), "place_id", 200)
        if pid in ids:
            raise AppError(f"Duplicate place_id: {pid}")
        ids.add(pid)
        lat = number(row.get("lat"), "lat", -90, 90, True)
        lon = number(row.get("lon"), "lon", -180, 180, True)
        coordinates_valid = lat is not None and lon is not None and (lat != 0 or lon != 0)
        places.append({
            "place_id": pid, "name": text(row.get("name"), "place name", 1000),
            "service": choice(row.get("service"), SERVICES, "service"),
            "address": text(row.get("address", ""), "address", 2000, True),
            "lat": lat, "lon": lon, "valid_coordinates": coordinates_valid,
            "closure_status": choice(row.get("closure_status", "not_verified_open"), ("temporarily_closed", "not_verified_open"), "closure_status"),
            "sampled_reviews": integer(row.get("sampled_reviews"), "sampled_reviews", 1),
        })
    counts_by_place = {p["place_id"]: p["sampled_reviews"] for p in places}
    aspect_ids = set()
    for row in collections["aspects"]:
        pid = text(row.get("place_id"), "place_id", 200)
        aspect = choice(row.get("aspect"), ASPECTS, "aspect")
        if pid not in ids or (pid, aspect) in aspect_ids:
            raise AppError("Aspects must refer to existing places and be unique per place and aspect.")
        aspect_ids.add((pid, aspect))
        barrier = integer(row.get("barrier_reports"), "barrier_reports")
        positive = integer(row.get("positive_reports"), "positive_reports")
        mixed = integer(row.get("uncertain_reports"), "uncertain_reports")
        total = integer(row.get("sampled_reviews"), "sampled_reviews", 1)
        if total != counts_by_place[pid] or barrier + positive + mixed > total:
            raise AppError("Aspect report counts must agree with the place's sampled review count.")
        aspects.append({
            "place_id": pid, "aspect": aspect, "sampled_reviews": total,
            "barrier_reports": barrier, "positive_reports": positive, "uncertain_reports": mixed,
            "status": aggregate_status(barrier, positive, mixed),
            "first_date": timestamp(row.get("first_date"), "first_date"),
            "last_date": timestamp(row.get("last_date"), "last_date"),
            "verification_question": text(row.get("verification_question", QUESTIONS[aspect]), "verification_question", 2000),
        })
    if len(aspect_ids) != len(ids) * len(ASPECTS):
        raise AppError("Each place needs all five aspect summaries, including aspects with no mentions.")
    evidence_ids = set()
    evidence_counts = {}
    for row in collections["evidence"]:
        pid = text(row.get("place_id"), "place_id", 200)
        aspect = choice(row.get("aspect"), ASPECTS, "evidence aspect")
        rid = text(row.get("record_id"), "record_id", 200)
        if (pid, aspect) not in aspect_ids or (rid, aspect) in evidence_ids:
            raise AppError("Evidence must refer to an existing place/aspect and have unique record/aspect IDs.")
        evidence_ids.add((rid, aspect))
        state = choice(row.get("state"), STATES, "evidence state")
        evidence_counts[(pid, aspect, state)] = evidence_counts.get((pid, aspect, state), 0) + 1
        evidence.append({
            "record_id": rid, "place_id": pid, "aspect": aspect, "state": state,
            "text": text(row.get("text"), "evidence text", 65536),
            "review_date": timestamp(row.get("date"), "evidence date"),
            "score": number(row.get("score"), "score", 0, 1, True),
            "barrier_score": number(row.get("barrier_score"), "barrier_score", 0, 1, True),
        })
    for row in aspects:
        for field, state in (("barrier_reports", "barrier_reported"), ("positive_reports", "positive_access"), ("uncertain_reports", "unclear_or_mixed")):
            if evidence_counts.get((row["place_id"], row["aspect"], state), 0) > row[field]:
                raise AppError("Evidence counts cannot exceed their corresponding aggregate counts.")
    return {"dataset": metadata, "places": places, "aspects": aspects, "evidence": evidence}
