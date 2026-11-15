# Matching, model comparisons, and evidence assistant

## Implemented

- Conservative entity resolution: exact Places ID, alternate Google CID/FID (including supported Google URL IDs), then unique normalized name plus numbered full address. Conflicting fallback metadata and ambiguous businesses are rejected. Source review IDs remain stable; canonical place IDs define grouped splits. Match decisions and per-method coverage are exported. No name-only or fuzzy chain-name joins.
- Filtering audit compares primary category, all category fields, and an explicitly broader essential-service scope. The broader policy is measured separately and does not silently change training scope. Closed locations remain excluded.
- Five comparisons: keyword rules, training-majority baseline, word TF-IDF logistic regression, word/character TF-IDF logistic regression, and Multinomial Naive Bayes. Thresholds and comparison selection use validation data. Human test labels remain separate. Scores are explicitly uncalibrated.
- Separate train/validation/test annotation handoffs and annotation progress, making the remaining independent evaluation work concrete.
- Read-only evidence assistant with cited excerpts, full-scope aggregates, transparent verification ranking and suggested checks. Optional OpenAI evidence selection runs on the server; offline mode requires no credentials. Model-generated IDs are checked against supplied evidence, and displayed statistics are computed in code.
- Optional offline OpenStreetMap Point GeoJSON enrichment: unique same-name POI within at most 50 metres, with source/date/ODbL attribution. Wheelchair and opening-hours tags remain contextual observations, never labels or certifications. Missing tags remain unknown. This exports a separate context file; it is not yet displayed in the map or chatbot.

## What was measured in this session

The full Reviews source downloaded successfully: 221,618,514 bytes, SHA-256 `1787435e1efbaddd88256efe38d481cec2b442e754bbe3d6b9e9e03d7a8674d0`.

- 213,536 raw reviews; 213,528 with nonblank text and place ID; 6,108 unique place IDs.
- 6,106 place IDs have a usable name/full-address matching key.
- 3,326 place IDs have a CID key through a column, FID, or supported URL.
- 42 entities have conflicting name/address keys; one has conflicting CIDs. The fallback matcher excludes conflicting keys/entities rather than choosing arbitrarily.

These are **matching-key availability**, not recovered matches. The full Places download returned Google's quota-exceeded HTML and was quarantined instead of treated as CSV. No fresh two-file join, improved coverage percentage, or real-data retraining is claimed. The earlier 1.33% and 79-location run in the historical README was documented by the original project; its private artifacts are not available in this checkout.

No human annotations or external OSM dataset were supplied. Independent model accuracy, actual enrichment coverage, and stakeholder impact remain unmeasured. Tests use fixtures and are software verification only. No live paid LLM request was made. The user explicitly deferred live LLM testing; missing provider configuration remains unresolved. Provider timeout, malformed/oversized/incomplete responses, invalid citations, missing configuration and opt-in boundaries are tested with mocks.

## Verification

All 39 tests passed in the final combined run, including HTTP/chat contracts, matching ambiguity and closure exclusions, model/annotation invariants, synthetic notebook execution and DuckDB export/import. `node --check access_app/static/app.js` and `git diff --check` passed. Live LLM calls and visual browser QA were not performed. Browser origin approval was declined for Drive and the local preview.

## Reproduce

Install the existing requirements, then profile the available source:

```sh
python scripts/compare_matching.py --reviews data/google_maps_reviews.csv
```

Once the full Places source is available, compare alternative joins:

```sh
python scripts/compare_matching.py --reviews data/google_maps_reviews.csv --places data/google_maps.csv
```

The CLI reports matching before service/closure filtering. The notebook additionally reports downstream closure, service and deduplication counts; use the same denominator when comparing with the historical 1.33%.

Run the notebook with either existing logistic model or the new classifier:

```sh
python scripts/run_real_notebook.py --prediction-model tfidf_nb --db var/access.duckdb
python -m access_app serve
```

The runner still requires both full sources. Do not interpret synthetic output as results for actual communities. Complete the partition-specific annotation files exported under `outputs/real/`, following `annotation_instructions.md`, and place adjudicated records in `data/labels.csv`. Keep reserved test labels separate until model selection is frozen.

For optional OSM context, add `--osm-geojson YOUR_LOCAL_FILE.geojson --osm-source-url SOURCE_URL --osm-retrieved-at YYYY-MM-DD` to the two-file comparison command. The adapter accepts Point features only and does not download data or modify labels. See [OSM wheelchair tags](https://wiki.openstreetmap.org/wiki/Key:wheelchair), [opening hours](https://wiki.openstreetmap.org/wiki/Key:opening_hours), and [ODbL attribution](https://www.openstreetmap.org/copyright).

A future area-level extension could join census tract disability, language and income estimates to geographic coordinates. Such estimates would describe an area, never a reviewer or an individual business. This has not been implemented because the core source join and independent evaluation need to be established first.

## Optional LLM setup

By default, the chatbot operates offline. To enable its optional evidence selector, set server environment variables:

```sh
export ACCESS_CHAT_PROVIDER=openai
export ACCESS_CHAT_MODEL=YOUR_SUPPORTED_RESPONSES_MODEL
export OPENAI_API_KEY=YOUR_KEY
python -m access_app serve
```

Do not put credentials in frontend code or commit them. The app does not automatically load `.env` files. The user must explicitly select the LLM option; it sends the question and bounded review evidence to OpenAI. Use it only with excerpts you are permitted to transmit. Invalid outputs or provider failures fall back to offline retrieval. The LLM selects cited evidence; it does not calculate aggregate counts or supply an unvalidated accessibility score.
