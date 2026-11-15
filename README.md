# Access Beyond the Map

A single-page explorer of classified accessibility issues at essential services. Browse the location list and map, filter by access aspect, and select a place to inspect its review evidence.

Read the [complete system design and website walkthrough](docs/SYSTEM_DESIGN.md) for the architecture diagram, every processing stage, model inputs/outputs, database contracts and chatbot flow. The [editable diagram source](docs/diagrams/system-design.mmd) is included.

## 📊 Presentation

[View the slide deck (PDF)](slides/Access_Beyond_the_Map.pdf)

## Improvements in this checkout

This version adds conservative alternate-ID/name-address matching, a five-model comparison including Naive Bayes and a majority baseline, separate human-annotation handoffs, an evidence chatbot, and an optional OSM context adapter. See [IMPROVEMENTS.md](IMPROVEMENTS.md) for commands, measured input coverage, limitations and optional LLM setup.

**Current bundled results:** direct LLM classification of **1,868 real reviews across 79 mapped locations**, producing **1,303 evidence excerpts** across five access aspects. The run uses `gpt-5.6-terra` and the historical retained review cohort; it does not rerun the latest matching changes or use keyword-generated training labels. Independent human evaluation remains pending. Raw organizer files, training dependencies and an API key are not needed to explore the saved results.

## Run the local app

For a verified step-by-step setup, see [Run locally](docs/RUN_LOCALLY.md), including macOS/Linux and Windows commands, real-results import, optional LLM setup and troubleshooting.

Install Python 3.11 or later (3.12 recommended), then clone and launch:

```sh
git clone https://github.com/zen0072/fall2026_datathon.git
cd fall2026_datathon
python3 scripts/launch_app.py
```

On Windows, use `py -3 scripts/launch_app.py`. The launcher creates `.venv`, installs only `requirements-app.txt`, loads the **real classified results** into an empty local DuckDB database, and opens **http://127.0.0.1:8000/**. Initial dependency installation requires internet access. No Node build, raw CSV downloads or model training are needed.

If port 8000 is busy, use `python3 scripts/launch_app.py --port 8001`. Add `--no-browser` to open the URL yourself. Stop the app with **Ctrl+C**. Existing imported data is never overwritten; use `--db var/fresh.duckdb` for a fresh database.

To test OpenAI evidence selection:

1. In **Ask the review data**, expand **Connection settings**.
2. Enter your own API key and a Responses API model available to your account. The default is `gpt-5.6-terra`, which supports structured outputs. Choose **Use key for this run**.
3. Select **Use OpenAI evidence selection**, then ask a question. A saved key has not been validated until an actual request succeeds; the answer shows whether it used OpenAI or offline retrieval.

The password field clears after submission. The key goes only to your local Python server and is kept in memory, never in browser storage, the results JSON or the local database. Choose **Remove key** or stop the server to discard a key entered through the page. Requests made with your key use **your OpenAI API billing**. No API key is needed to explore locations or use offline evidence retrieval. Each LLM request sends your question and up to 24 review excerpts to OpenAI; no conversation history is sent. The app does not automatically load `.env` files; setting server environment variables remains an alternative to the form.

For a manual setup:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-app.txt
.venv/bin/python -m access_app serve --bundled
```

On Windows, use `.venv\Scripts\python` instead of `.venv/bin/python`. `--bundled` loads the included real snapshot only into an empty database. For an empty app, omit it or use the launcher with `--empty`. `--demo` is still available explicitly for four **fictional** test locations, with no measured model findings or impact.

The app serves its frontend and JSON API from one Python process and persists records in `var/access.duckdb`. No Node build step is required. The default loopback address keeps this prototype local; authentication and organization-level permissions have not been implemented for public hosting.

## Connect a notebook run

1. Run `Access_Beyond_the_Map.ipynb` in Colab with the intended mode and source files. Section 9 now creates **`frontend_results_PRIVATE.json`**, also included in the final results ZIP.
2. Stop the app and import that file through the command line:

   ```sh
   .venv/bin/python -m access_app import /absolute/path/frontend_results_PRIVATE.json --db var/access.duckdb
   ```

   Restart the app after importing. The explorer loads the active database snapshot.

3. Search or filter the location list and map by service, access issue, and classification. Select a location to read its dated supporting, positive, and conflicting excerpts on the same page.

Refresh the browser after a CLI import. The notebook's existing real-data acquisition and human-label requirements still apply: the app does not bypass download quotas, train models on requests, or turn rule labels into independent evaluation.

## Direct LLM classification

The offline [LLM classification runner](docs/LLM_CLASSIFICATION.md) classified
the 1,868 reviews behind the existing map across all five accessibility aspects,
and exported review predictions and a frontend-compatible locations snapshot.
It requires the local raw Reviews CSV, historical split manifest and your own
API key. It uses numbered source passages to preserve exact review evidence,
checkpoints completed requests, and makes zero API calls unless `--run` is set.
This is separate from the chatbot's optional evidence selection.

## Historical real-data run: TF-IDF + logistic regression

In the original local run, both full organizer files were cached in ignored `data/`: **Places** has 147,429 rows (506,418,083 bytes) and **Reviews** has 213,536 rows (221,618,514 bytes). These raw files are not included in a clone. Source SHA-256 hashes are recorded in the bundled snapshot and the private run's `outputs/real/sources.json`. The user supplied the full Places CSV after the earlier Drive quota block.

The earlier notebook completed locally in real mode and exported **trained word TF-IDF + logistic regression predictions** for **79 mapped locations, 1,868 retained reviews, and 365 aspect excerpts**. That original export remains in private `outputs/real/frontend_results_PRIVATE.json` for comparison. The bundled snapshot at `access_app/data/classified_locations.json` now contains direct LLM classifications of the same retained reviews. The notebook filters explicitly permanently closed places, scopes essential-service categories, deduplicates reviews and holds out locations before training.

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

The previous reviews-only adapter remains available as `scripts/import_real_reviews.py` for explicitly requested partial runs. The bundled and current local results use direct LLM classification, not that adapter.

## How the connection works

```text
Organizer CSVs → retained matched reviews → LLM classification → versioned results JSON
                                             ↓
                             DuckDB result snapshots + Python API
                                             ↓
                           Single-page list + map + evidence
```

DuckDB holds immutable result snapshots, location summaries, and review evidence. Imports validate the whole payload before a transaction and switch the active results pointer. Reimporting the same file is idempotent. Source hashes, label provenance, and evaluation status remain in the imported metadata and private exports.

The original TF-IDF notebook remains available as a comparison workflow. The LLM
runner uses the same retained cohort, classifies every review across all five
aspects, and aggregates states locally. Quoted evidence is copied from selected
source passages; it is not generated prose.

## Frontend

One page, with no sidebar or separate workflow screens:

- Name/address search, service/aspect/classification filters, and report-count/date/name sorting.
- A paginated list beside the map, with consistent classification colors and selected-location highlighting.
- Accessibility categories default to locations with review excerpts for that category. Choose **Insufficient evidence** explicitly to inspect places without reported evidence. Scroll over the map to zoom in or out.
- A compact evidence card below the list and map: the location summary stays visible above All, Barriers, Positive, and Mixed filters. Reviews scroll inside the card, with source IDs available under **Source details**.
- A conversation-style review assistant with a bounded scroll area, suggested questions, and a composer below the answers. It starts with the selected location; turn off **Only the selected location** for the full scope. Each answer keeps its own applied scope, sources, priorities, and verification steps. Up to 20 exchanges stay in page memory until refresh; previous messages are never sent as question context.
- Results import, clear empty states, closure indicators, and a missing-coordinate placeholder.

Permanently closed places are removed upstream in the full notebook run; unknown closure status does not establish that a place is open. Previously stored organization records remain in the database for compatibility; the frontend has no work-item controls or related screens.

The map renders up to the first 500 matching locations; the list is paginated and retains locations without coordinates. Evidence tabs count all exported excerpts for the selected access issue, load 50 at a time, and offer **Load more excerpts** inside the scroll area. Dates use UTC to preserve the source calendar day. Report counts are sampled evidence counts, not a universal accessibility score or population prevalence.

Map code (Leaflet 1.9.4 and its license) is vendored locally. Esri Light Gray Canvas tiles and reference labels require internet access and carry provider attribution. Labels sit beneath the colored markers, which use white outlines for contrast. If tiles are unavailable, the location list and evidence remain usable. The navy/lavender interface follows the selected design and supports light/dark appearance and narrow screens.

## Interchange format

The schema-version-1 file contains:

- `dataset`: mode, generation time, selected model, label mode, evaluation status, source manifest, metrics and selection metadata.
- `places`: stable place IDs, names, service types, optional addresses, coordinates, closure status and sampled-review counts.
- `aspects`: all five access-aspect summaries per place, report counts, dates and verification questions.
- `evidence`: mentioned-aspect excerpts with record IDs, dates, predicted states and optional uncalibrated scores. No-mention rows contribute to denominators without exporting unnecessary review text.

The importer stores only declared analysis fields. Reviewer name/profile columns are not imported. The deliberately included `access_app/data/classified_locations.json` contains the saved classifications and original evidence excerpts used for testing. Raw data, private notebook outputs, database files, credentials and local environments remain ignored by Git. Review text can contain personal information; review any new exports before redistributing them.

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
| `GET /api/chat/config` | Public connection status and model; never returns credentials |
| `POST /api/chat/config` | Set or remove an in-memory key, on a loopback-bound local server only |
| `POST /api/chat` | Query local evidence with optional OpenAI evidence selection |

For existing Colab verification and remaining real-data research blockers, see [VERIFICATION.md](VERIFICATION.md).
