"""Conservative, auditable entity resolution; no network or fuzzy-name joins.

Fallbacks are hypotheses, not independently validated matches. Preserve the
source review place ID and use canonical Places IDs only for grouping/splits.
"""
import math
import re
import unicodedata
from collections import defaultdict
from urllib.parse import parse_qs, urlparse

import pandas as pd

MATCH_COLUMNS = ['source_place_id', 'place_id', 'match_method', 'match_status']
METADATA_COLUMNS = {'place_id', 'name', 'place_name', 'address', 'cid', 'fid',
                    'fid_location', 'url', 'google_maps_url', 'lat', 'lon', 'category'}


def clean(value):
    return '' if value is None or pd.isna(value) else str(value).strip()


def normalize(value):
    # Keep numbers, directionals, unit numbers and diacritics; never strip branches.
    return ' '.join(re.sub(r'[^\w]+', ' ', unicodedata.normalize('NFKC', clean(value)).casefold()).split())


def cid_values(row):
    values = set()
    cid = clean(row.get('cid'))
    if re.fullmatch(r'\d+', cid):
        values.add(str(int(cid)))
    for field in ('fid', 'fid_location'):
        fid = clean(row.get(field))
        if re.fullmatch(r'0x[0-9a-fA-F]+:0x[0-9a-fA-F]+', fid):
            values.add(str(int(fid.split(':')[1], 16)))
    for field in ('url', 'google_maps_url'):
        parsed = urlparse(clean(row.get(field)))
        if parsed.hostname and (parsed.hostname == 'google.com' or parsed.hostname.endswith('.google.com')):
            for value in parse_qs(parsed.query).get('cid', []):
                if re.fullmatch(r'\d+', value):
                    values.add(str(int(value)))
    return values


def row_keys(row):
    keys = {('cid', value) for value in cid_values(row)}
    name = normalize(row.get('name')) or normalize(row.get('place_name'))
    address = normalize(row.get('address'))
    # Require a numbered full address. Name-only and street-only guesses are unsafe.
    if name and address and re.search(r'\d', address) and len(address.split()) >= 4:
        keys.add(('name_address', name + '\x1f' + address))
    return keys


def match_review_places(places, reviews):
    """Return one decision per nonempty review place ID and coverage by method.

    Places may contain duplicate IDs; any fallback key shared across IDs is
    rejected. Conflicting metadata across reviews of one source ID is rejected.
    Exact IDs remain authoritative. Input frames are never mutated.
    """
    for frame in (places, reviews):
        if 'place_id' not in frame:
            raise ValueError('Both inputs require place_id')
    canonical = {clean(v) for v in places.place_id} - {''}
    index = defaultdict(set)
    for row in places.to_dict('records'):
        pid = clean(row.get('place_id'))
        if pid:
            for key in row_keys(row):
                index[key].add(pid)
    source_keys = defaultdict(set)
    counts = defaultdict(int)
    for row in reviews[list(METADATA_COLUMNS.intersection(reviews.columns))].to_dict('records'):
        pid = clean(row.get('place_id'))
        if pid:
            counts[pid] += 1
            source_keys[pid].update(row_keys(row))
    decisions = []
    for pid, keys in source_keys.items():
        target, method, status = None, 'unmatched', 'no_candidate'
        if pid in canonical:
            target, method, status = pid, 'exact_place_id', 'matched'
        else:
            matched_keys = [(key, index[key]) for key in keys if key in index]
            candidates = set().union(*(v for _, v in matched_keys)) if matched_keys else set()
            # Even one nonunique key blocks a seemingly unique second key.
            source_conflict = any(sum(k[0] == kind for k in keys) > 1 for kind in ('cid', 'name_address'))
            if len(candidates) > 1 or (candidates and source_conflict):
                status = 'ambiguous_or_conflicting'
            elif len(candidates) == 1:
                target = next(iter(candidates))
                method = 'cid_or_fid' if any(k[0] == 'cid' for k, _ in matched_keys) else 'name_full_address'
                status = 'matched'
        decisions.append(dict(source_place_id=pid, place_id=target, match_method=method, match_status=status))
    crosswalk = pd.DataFrame(decisions, columns=MATCH_COLUMNS)
    total = len(reviews)
    coverage = []
    cumulative = 0
    for method in ('exact_place_id', 'cid_or_fid', 'name_full_address'):
        selected = crosswalk.loc[crosswalk.match_method.eq(method), 'source_place_id']
        added = sum(counts[pid] for pid in selected)
        cumulative += added
        coverage.append(dict(method=method, added_review_rows=added, added_source_places=len(selected),
                             cumulative_matched_reviews=cumulative, coverage=cumulative / total if total else 0.0))
    audit = dict(review_rows=total, source_places=len(counts), places_ids=len(canonical),
                 missing_source_id_rows=total-sum(counts.values()), alternatives=coverage,
                 ambiguous_source_places=int(crosswalk.match_status.eq('ambiguous_or_conflicting').sum()),
                 unvalidated_fallbacks=True,
                 policy='Exact ID; otherwise all available candidate keys must agree on one unique Places ID. No fuzzy or name-only joins.')
    return crosswalk, audit


def _distance_m(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    a = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371000 * 2 * math.asin(min(1, math.sqrt(a)))


def enrich_osm(places, geojson, *, source_url, retrieved_at, max_distance_m=50):
    """Offline OSM Point GeoJSON: unique same-name POI within 50m.

    Return contextual tags only, never predictions/labels or assumed negatives.
    Reject multiple candidates and reused OSM features. Source URL/date required.
    OSM data is © OpenStreetMap contributors, ODbL; retain attribution.
    """
    if not source_url or not retrieved_at or not 0 < max_distance_m <= 50:
        raise ValueError('Supply provenance and a distance in (0, 50] metres')
    features = defaultdict(list)
    for feature in geojson.get('features', []):
        geom = feature.get('geometry') or {}
        props = feature.get('properties') or {}
        tags = props.get('tags', props)
        fid = feature.get('id') or props.get('@id')
        coords = geom.get('coordinates', [])
        if geom.get('type') != 'Point' or len(coords) < 2 or not fid:
            continue
        lon, lat = coords[:2]
        if not isinstance(lat, (float, int)) or not isinstance(lon, (float, int)) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        name = normalize(tags.get('name'))
        if name:
            features[name].append((str(fid), lat, lon, tags))
    proposals = []
    for row in places.to_dict('records'):
        try:
            lat, lon = float(row.get('lat')), float(row.get('lon'))
        except (TypeError, ValueError):
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
            continue
        candidates = []
        for fid, y, x, tags in features.get(normalize(row.get('name')), []):
            distance = _distance_m(lat, lon, y, x)
            if distance <= max_distance_m:
                candidates.append((fid, distance, tags))
        if len(candidates) == 1:
            fid, distance, tags = candidates[0]
            proposals.append(dict(place_id=clean(row.get('place_id')), osm_id=fid, distance_m=round(distance, 2),
                                  wheelchair=tags.get('wheelchair'), opening_hours=tags.get('opening_hours'),
                                  source_url=source_url, retrieved_at=retrieved_at,
                                  match_method='unique_exact_name_within_50m',
                                  attribution='© OpenStreetMap contributors; ODbL',
                                  interpretation='Context only; missing tags mean unknown, not inaccessible.'))
    uses = defaultdict(set)
    for row in proposals:
        uses[row['osm_id']].add(row['place_id'])
    return pd.DataFrame([row for row in proposals if len(uses[row['osm_id']]) == 1])
