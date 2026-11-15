"""Explicit fictional fixture for demonstrating the app, never model findings."""

from collections import Counter

from .schema import ASPECTS, QUESTIONS, aggregate_status, utc_now


def demo_bundle():
    locations = [
        ("demo_harbor", "Harbor Community Clinic", "clinic", 37.770, -122.428, "Fictional central-area location"),
        ("demo_meadow", "Meadow Pharmacy", "pharmacy", 37.783, -122.460, "Fictional northwest-area location"),
        ("demo_olive", "Olive Neighborhood Market", "grocery", 37.741, -122.456, "Fictional southwest-area location"),
        ("demo_cedar", "Cedar Family Clinic", "clinic", 37.730, -122.405, "Fictional southeast-area location"),
    ]
    reports = {
        "demo_harbor": [
            ("The entrance has steps and there was no ramp available.", {"physical": "barrier_reported"}),
            ("The entrance ramp was blocked. No hearing loop was available when I asked.", {"physical": "barrier_reported", "sensory": "barrier_reported"}),
            ("Staff helped us use the step-free side entrance.", {"physical": "positive_access"}),
            ("An interpreter helped me understand the appointment.", {"language": "positive_access"}),
            ("An interpreter was available and my appointment was prompt.", {"language": "positive_access", "time": "positive_access"}),
            ("I waited three hours and could not get an appointment.", {"time": "barrier_reported"}),
        ],
        "demo_meadow": [
            ("The wide entrance and ramp made it easy to enter.", {"physical": "positive_access"}),
            ("There was enough space for my wheelchair at the counter.", {"physical": "positive_access"}),
            ("I could not afford the unexpected fee and left without the service.", {"financial": "barrier_reported"}),
            ("My appointment was prompt with almost no waiting.", {"time": "positive_access"}),
            ("The staff were friendly.", {}),
        ],
        "demo_olive": [
            ("There is a ramp, but deliveries sometimes block it.", {"physical": "unclear_or_mixed"}),
            ("The ramp was clear and easy to use on my visit.", {"physical": "positive_access"}),
            ("Boxes blocked the aisle and I could not reach the service counter.", {"physical": "barrier_reported"}),
            ("No language assistance was available when I needed help.", {"language": "barrier_reported"}),
            ("The store closed early and I could not get groceries.", {"time": "barrier_reported"}),
            ("The produce was fresh.", {}), ("A pleasant visit.", {}),
        ],
        "demo_cedar": [("An interpreter was available during my visit.", {"language": "positive_access"}), ("The staff were friendly.", {}), ("The lobby was tidy.", {})],
    }
    places, aspects, evidence = [], [], []
    for pid, name, service, lat, lon, address in locations:
        reviews = reports[pid]
        places.append(dict(place_id=pid, name=name, service=service, lat=lat, lon=lon, address=address, closure_status="not_verified_open", sampled_reviews=len(reviews)))
        for aspect in ASPECTS:
            counts = Counter(states.get(aspect) for _, states in reviews)
            barrier, positive, mixed = (counts[s] for s in ("barrier_reported", "positive_access", "unclear_or_mixed"))
            aspects.append(dict(place_id=pid, aspect=aspect, sampled_reviews=len(reviews), barrier_reports=barrier, positive_reports=positive, uncertain_reports=mixed, status=aggregate_status(barrier, positive, mixed), first_date="2026-11-01T00:00:00+00:00", last_date=f"2026-11-{len(reviews):02d}T00:00:00+00:00", verification_question=QUESTIONS[aspect]))
        for i, (excerpt, states) in enumerate(reviews, 1):
            for aspect, state in states.items():
                evidence.append(dict(record_id=f"{pid}_{i}", place_id=pid, aspect=aspect, state=state, text=excerpt, date=f"2026-11-{i:02d}T00:00:00+00:00", score=None, barrier_score=None))
    return {"schema_version": 1, "dataset": {"mode": "synthetic", "generated_at": utc_now(), "model": "illustrative_ui_examples", "label_mode": "fictional_demo_labels", "evaluation_status": "NOT EVALUATED — fictional interface demo", "source_manifest": {"source": "Invented locations and review examples"}, "metrics": {}, "selection": {}, "coverage_note": "Four fictional locations used to demonstrate the organization workflow. No real-world findings."}, "places": places, "aspects": aspects, "evidence": evidence}
