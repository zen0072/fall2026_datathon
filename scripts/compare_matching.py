"""Profile real inputs and compare conservative joins; outputs contain no review text.

python scripts/compare_matching.py --reviews data/google_maps_reviews.csv
python scripts/compare_matching.py --reviews data/google_maps_reviews.csv --places data/google_maps.csv
Optional OSM enrichment requires a locally obtained Point GeoJSON and provenance.
"""
import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd
from access_app.matching import METADATA_COLUMNS, enrich_osm, match_review_places, row_keys


def load(path):
    with path.open('rb') as stream:
        if stream.read(4096).lstrip().lower().startswith((b'<html', b'<!doctype')):
            raise ValueError(f'{path.name} is HTML, not a source CSV')
    return pd.read_csv(path, usecols=lambda c: c in METADATA_COLUMNS or c in {'review', 'all_categories', 'permanently_closed'}, dtype=str)


def compare_service_filters(places, crosswalk, reviews):
    """Compare scope policies without silently expanding the notebook's scope."""
    def group(value, expanded=False):
        value = str(value).casefold()
        if re.search(r"pharmac|drugstore", value): return "pharmacy"
        if re.search(r"grocery|supermarket|food market", value): return "grocery"
        if re.search(r"clinic|medical|hospital|health center|doctor|dentist", value): return "clinic"
        if expanded and re.search(r"convenience store|food store", value): return "grocery"
        if expanded and re.search(r"urgent care|health centre|general practitioner", value): return "clinic"
        return "other"
    rows = []
    for policy in ("primary_category", "all_categories", "expanded_essential_scope"):
        eligible_ids = set()
        for pid, records in places.dropna(subset=["place_id"]).groupby("place_id"):
            # Any explicit closed record excludes the entity; missing is unknown.
            closed = records.get("permanently_closed", pd.Series(dtype=str)).fillna("").str.lower().str.strip()
            if closed.isin(["true", "1", "1.0", "yes"]).any(): continue
            fields = ["category"] + (["all_categories"] if policy != "primary_category" else [])
            category = " | ".join(str(v) for field in fields if field in records for v in records[field].dropna())
            if group(category, policy == "expanded_essential_scope") != "other":
                eligible_ids.add(str(pid).strip())
        source_ids = set(crosswalk.loc[crosswalk.place_id.isin(eligible_ids), "source_place_id"])
        mask = reviews.place_id.astype(str).str.strip().isin(source_ids)
        rows.append({"policy": policy, "eligible_review_rows_before_deduplication": int(mask.sum()),
                     "matched_places": int(crosswalk.loc[crosswalk.source_place_id.isin(source_ids), "place_id"].nunique()),
                     "changes_service_scope": policy == "expanded_essential_scope"})
    return rows


def fingerprint(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return {'bytes': path.stat().st_size, 'sha256': digest.hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reviews', type=Path, required=True)
    parser.add_argument('--places', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'outputs/matching')
    parser.add_argument('--osm-geojson', type=Path)
    parser.add_argument('--osm-source-url')
    parser.add_argument('--osm-retrieved-at')
    args = parser.parse_args()
    reviews = load(args.reviews)
    eligible = reviews.loc[reviews.place_id.fillna('').str.strip().ne('') & reviews.review.fillna('').str.strip().ne('')].copy()
    report = {'status': 'blocked_missing_places', 'sources': {'reviews': fingerprint(args.reviews)},
              'reviews': {'raw_rows': len(reviews), 'unique_place_ids': int(reviews.place_id.nunique()),
                          'eligible_review_rows': len(eligible),
                          'metadata_nonmissing_rows': reviews.drop(columns='review').notna().sum().to_dict()},
              'coverage_improvement': None}
    keys = defaultdict(set)
    for row in reviews.drop(columns='review').to_dict('records'):
        keys[row['place_id']].update(row_keys(row))
    availability = Counter()
    for entity_keys in keys.values():
        for kind in ('cid', 'name_address'):
            n = sum(key[0] == kind for key in entity_keys)
            if n:
                availability[kind + '_available_places'] += 1
            if n > 1:
                availability[kind + '_conflicting_places'] += 1
    report['reviews']['fallback_key_availability_NOT_matches'] = dict(availability)
    args.output.mkdir(parents=True, exist_ok=True)
    if args.places:
        places = load(args.places)
        crosswalk, audit = match_review_places(places, eligible)
        report.update(status='measured_raw_places_before_scope_or_closure_filter', matching=audit)
        report['sources']['places'] = fingerprint(args.places)
        report['service_filter_alternatives'] = compare_service_filters(places, crosswalk, eligible)
        report['coverage_improvement'] = audit['alternatives'][-1]['coverage'] - audit['alternatives'][0]['coverage']
        crosswalk.to_csv(args.output / 'crosswalk_PRIVATE.csv', index=False)
        if args.osm_geojson:
            enriched = enrich_osm(places, json.loads(args.osm_geojson.read_text()),
                                  source_url=args.osm_source_url, retrieved_at=args.osm_retrieved_at)
            enriched.to_csv(args.output / 'osm_context_PRIVATE.csv', index=False)
            report['osm'] = {'matched_places': len(enriched), 'source': fingerprint(args.osm_geojson), 'is_ground_truth': False}
    elif args.osm_geojson:
        parser.error('--osm-geojson requires --places')
    (args.output / 'matching_report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
