# Access Beyond the Map

A single-page explorer of classified accessibility issues at essential services. Browse the location list and map, filter by access aspect, and select a place to inspect its review evidence.

Read the [complete system design and website walkthrough](docs/SYSTEM_DESIGN.md) for the architecture diagram, every processing stage, model inputs/outputs, database contracts and chatbot flow. The [editable diagram source](docs/diagrams/system-design.mmd) is included.

## 📊 Presentation

[View the slide deck (PDF)](slides/Access_Beyond_the_Map.pdf)

## Improvements in this checkout

This version adds conservative alternate-ID/name-address matching, a five-model comparison including Naive Bayes and a majority baseline, separate human-annotation handoffs, an evidence chatbot, and an optional OSM context adapter. See [IMPROVEMENTS.md](IMPROVEMENTS.md) for commands, measured input coverage, limitations and optional LLM setup.

**Current verification boundary:** the full Reviews file was obtained again, but the Places source is quota-blocked. The historical full-data results below have not been regenerated with these changes. Independent human evaluation remains pending. The app can be tested with the explicitly fictional demo until a real notebook export is available.

## Run the local app

Use Python 3.11–3.13 (3.12 recommended alongside the notebook).

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-app.txt
.venv/bin/python -m access_app serve --demo
```

Open **http://127.0.0.1:8000/**. On Windows, use `.venv\Scripts\python` instead of `.venv/bin/python`.

`--demo` seeds four **fictional** locations only when the database has no imported results. It never replaces an existing real-data snapshot. Omit it to start with an empty database. The demo classifications are illustrative interface examples, not trained-model findings or measured impact.

The app serves its frontend and JSON API from one Python process and persists records in `var/access.duckdb`. No Node build step is required. The default loopback address keeps this prototype local; authentication and organization-level permissions have not been implemented for public hosting.

## Connect a notebook run

1. Run `Access_Beyond_the_Map.ipynb` in Colab with the intended mode and source files. Section 9 now creates **`frontend_results_PRIVATE.json`**, also included in the final results ZIP.
2. In the app, choose **Import results** and select that file. Alternatively:

   ```sh
   .venv/bin/python -m access_app import /absolute/path/frontend_results_PRIVATE.json --db var/access.duckdb
   ```

   Stop the app before running a separate command-line importer against the same DuckDB file. While the app is running, use its import button so its single backend process owns writes.

3. Search or filter the location list and map by service, access issue, and classification. Select a location to read its dated supporting, positive, and conflicting excerpts on the same page.

The browser import limit is 128 MB; use the CLI for larger results files. Refresh the browser after a CLI import. The notebook's existing real-data acquisition and human-label requirements still apply: the app does not bypass download quotas, train models on requests, or turn rule labels into independent evaluation.

## Historical real-data run: TF-IDF + logistic regression

Both full organizer files are cached in ignored `data/`: **Places** has 147,429 rows (506,418,083 bytes) and **Reviews** has 213,536 rows (221,618,514 bytes). Source SHA-256 hashes are recorded in `outputs/real/sources.json` and the imported snapshot. The user supplied the full Places CSV after the earlier Drive quota block.

The notebook completed locally in real mode and its **trained word TF-IDF + logistic regression predictions** are now imported into the frontend database. The current export contains **79 mapped locations, 1,868 retained reviews, and 365 aspect excerpts**. This replaces the earlier reviews-only keyword snapshot. The full notebook filters explicitly permanently closed places, scopes essential-service categories, deduplicates reviews and holds out locations before training.

Coverage is limited: 2,985 raw review rows match a Places ID; after empty-review and closure filtering, 2,837 rows remain matched (about 1.33% of eligible review rows). The essential-service subset retains 1,868 reviews after deduplication. It is not a complete inventory, and zero matches for a service do not establish that the service is absent.

**Training labels are provisional keyword-generated labels.** No adjudicated human labels have been supplied, so independent evaluation is blocked and no real accuracy score is claimed. Physical, language and time aspects have fitted logistic regressions; sensory and financial aspects use the notebook's constant no-mention fallback because their training labels have no variation. Those aspects are unsupported, not established accessible.

`FRONTEND_MODEL` defaults to `tfidf_word`. The keyword baseline and word/character TF-IDF candidate remain comparison models. The comparison winner (currently keywords on rule-generated validation labels) is recorded separately from the explorer's explicitly chosen prediction model; no predictive advantage is claimed from that comparison.

To reproduce and import the full run, stop the app and run:

```sh
.venv/bin/python -m pip install -r requirements.txt -r requirements-app.txt
.venv/bin/python scripts/run_real_notebook.py --prediction-model tfidf_word --db var/access.duckdb
.venv/bin/python -m access_app serve
```

The runner executes the actual notebook cells, skips only the Colab installation magic, saves a private log and run status under `outputs/real/`, validates the resulting JSON, and imports only after the notebook completes successfully. Choose `--prediction-model tfidf_word_char` for the trained word/character variant, or `validation_winner` to export the comparison winner. The current results file is `outputs/real/frontend_results_PRIVATE.json`.

The previous reviews-only adapter remains available as `scripts/import_real_reviews.py` for explicitly requested partial runs. It is not the currently imported result source.

## How the connection works

```text
Organizer CSVs → notebook labeling/modeling → versioned results JSON
                                             ↓
                             DuckDB result snapshots + Python API
                                             ↓
                           Single-page list + map + evidence
```

DuckDB holds immutable result snapshots, location summaries, and review evidence. Imports validate the whole payload before a transaction and switch the active results pointer. Reimporting the same file is idempotent. Source hashes, label provenance, and evaluation status remain in the imported metadata and private exports.

## Frontend

One page, with no sidebar or separate workflow screens:

- Name/address search, service/aspect/classification filters, and report-count/date/name sorting.
- A paginated list beside the map, with consistent classification colors and selected-location highlighting.
- Dated review excerpts and classification counts for the selected location, displayed below the list and map.
- Results import, clear empty states, closure indicators, and a missing-coordinate placeholder.

Permanently closed places are removed upstream in the full notebook run; unknown closure status does not establish that a place is open. Previously stored organization records remain in the database for compatibility; the frontend has no work-item controls or related screens.

The map renders up to the first 500 matching locations; the list is paginated and retains locations without coordinates. Details show up to 50 exported excerpts per access issue, with the total disclosed. Dates use UTC to preserve the source calendar day. Report counts are sampled evidence counts, not a universal accessibility score or population prevalence.

Map code (Leaflet 1.9.4 and its license) is vendored locally. Esri street-map tiles require internet access and carry provider attribution. If tiles are unavailable, the location list and evidence remain usable. The navy/lavender interface follows the selected design and supports light/dark appearance and narrow screens.

## Interchange format

The schema-version-1 file contains:

- `dataset`: mode, generation time, selected model, label mode, evaluation status, source manifest, metrics and selection metadata.
- `places`: stable place IDs, names, service types, optional addresses, coordinates, closure status and sampled-review counts.
- `aspects`: all five access-aspect summaries per place, report counts, dates and verification questions.
- `evidence`: mentioned-aspect excerpts with record IDs, dates, predicted states and optional uncalibrated scores. No-mention rows contribute to denominators without exporting unnecessary review text.

The importer stores only declared analysis fields. Reviewer name/profile columns are not imported. Review text can still contain personal information: keep real-data exports and the local database private, and review excerpts before sharing. Raw data, exports, database files and local environments are ignored by Git.

## Tests

```sh
.venv/bin/python -m pip install -r requirements.txt -r requirements-app.txt
MPLBACKEND=Agg .venv/bin/python -m unittest discover -s tests -v
```

Tests cover notebook execution, the actual notebook-to-DuckDB export/import path, location queries, failed-import isolation, persisted work items, historical evidence after a refresh, stale edits, CSV output, the HTTP API, origin checks and static-file boundaries. They use generated or fictional records and do not establish real-world model accuracy.

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /api/metadata` | Active dataset and coverage |
| `GET /api/places` | Filtered/paginated location summaries |
| `GET /api/places/{place_id}?aspect=physical&snapshot_id=...` | Place, aspect summaries and evidence |
| `POST /api/import` | Import a schema-version-1 notebook JSON payload |

For existing Colab verification and remaining real-data research blockers, see [VERIFICATION.md](VERIFICATION.md).
