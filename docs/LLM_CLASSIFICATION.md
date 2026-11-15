# Direct LLM classification of reviews

The optional offline runner replaces the review classifier, not the chatbot.
It classifies each review across physical, sensory, language, financial and time
access using a documented rubric and structured output. It sends only review
text, with no keyword labels, previous model predictions, reviewer profile
columns, or owner responses. Non-mention is distinct from positive access.

The completed local run classified all **1,868 reviews**, producing **9,340
aspect classifications**, **79 locations** and **1,303 evidence excerpts**. Its
validated snapshot is now bundled for clone-and-run exploration. The original
TF-IDF results remain in private `outputs/real/`. No independent accuracy score
is claimed.

The current scope deliberately reuses the historical retained cohort behind
the map: 1,868 reviews and 79 locations. The runner recovers the original full
texts from the raw Reviews CSV using `outputs/real/split_manifest.csv`, checks
the source hash and per-place counts, and rejects missing records. It does not
rerun the updated matcher. A normal clone includes the saved frontend snapshot,
but needs the raw Reviews CSV and historical manifest to run this comparison.

Install `requirements.txt` and `requirements-app.txt` in the local environment.
Create an ignored `.env` in the repository root:

```dotenv
OPENAI_API_KEY=your-key-here
# Optional; otherwise uses the existing chatbot's default model.
ACCESS_CLASSIFY_MODEL=gpt-5.6-terra
```

The key entered through the browser's chatbot form is kept in that separate
server's memory and is not available to this command. Never paste a key into
chat or commit it. This runner reads only literal key/model values from the
explicit env file; it does not execute shell code or print credentials.

Preflight (zero API requests):

```sh
.venv/bin/python scripts/classify_reviews_llm.py --env-file .env
```

Classify a bounded 20-review pilot with paid API requests:

```sh
.venv/bin/python scripts/classify_reviews_llm.py --env-file .env --run --limit 20
```

Then classify the full cohort, reusing the pilot's cached results:

```sh
.venv/bin/python scripts/classify_reviews_llm.py --env-file .env --run
```

On Windows, replace `.venv/bin/python` with `.venv\Scripts\python.exe`.
The model must be accessible to the API account and support Responses API
structured outputs. API billing, rate limits and model access are checked by
actual calls, not by saving a key. No dollar-cost estimate is claimed by preflight;
one call per uncached review classifies all five aspects. No automatic retry
loop runs after errors; rerun the command to resume completed checkpoints.
The default is four concurrent requests; use `--workers 1` for slower sequential
processing or up to `--workers 8` when the account's rate limits allow it.

Outputs stay in ignored `outputs/llm/`:

- `run_status.json`: configuration blockers, selected/completed counts and run state.
- `cache/`: validated per-review results, model/response IDs, timestamps and usage.
- `review_classifications_PRIVATE.json`: every review's full text, all five
  predicted states, exact evidence and request provenance; the pilot uses a
  separate `review_classifications_PARTIAL_PRIVATE.json`.
- `frontend_results_PARTIAL_PRIVATE.json`: successful pilot only, with denominators
  recomputed from the selected reviews and explicit partial-coverage metadata.
- `frontend_results_PRIVATE.json`: successful complete-cohort export.

The model selects numbered source passages; quotations are copied locally from
the original review, including the full span across selected passages. It cannot
write or paraphrase the displayed quote. Invalid schemas, unknown passage IDs,
refusals and incomplete responses stop the run; they never
silently become `no_mention`. Checkpoints are keyed by model, review, rubric and
schema, so changed inputs cannot silently reuse an old prediction. Model aliases
can change over time; returned model IDs and timestamps are retained.

The export uses the existing versioned frontend schema and DuckDB importer.
It records `label_mode=llm_direct_classification`, discards old model metrics and
does not invent probability/confidence scores. Independent human evaluation is
still pending. Exact quote validation proves source fidelity, not label accuracy.

After reviewing a completed export, stop the app using the target database and
import it with the existing command:

```sh
.venv/bin/python -m access_app import outputs/llm/frontend_results_PRIVATE.json
```

Alternatively pass `--db var/access.duckdb` to an explicit `--run` to import only
after every selected review has a validated result. The runner never overwrites
the bundled snapshot shipped to Git users. Updating that snapshot is a separate
step after reviewing results.

API references: [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses),
[default model](https://developers.openai.com/api/docs/models/gpt-5.6-terra).
