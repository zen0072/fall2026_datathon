"""The versioned, precomputed real results shipped for clone-and-run testing."""

import json
from pathlib import Path

BUNDLED_RESULTS = Path(__file__).parent / "data" / "classified_locations.json"


def seed_bundled_results(store):
    """Initialize an empty database; never replace a user's imported snapshot."""
    if store.metadata()["snapshot_id"]:
        return False
    store.import_bundle(json.loads(BUNDLED_RESULTS.read_text(encoding="utf-8")))
    return True
