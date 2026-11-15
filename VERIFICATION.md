# Direct LLM classification verification — November 15, 2026

The paid live run completed with OpenAI `gpt-5.6-terra`: **1,868 reviews**, all
**9,340 review/aspect classifications**, **79 mapped locations**, and **1,303
evidence excerpts**. It recovers the exact historical retained cohort using the
original source hash, retained record IDs and per-place counts, without
rerunning matching or passing keyword labels/TF-IDF predictions to the model.

An initial literal-quotation approach stopped when returned text did not match
the source exactly. The final approach selects enumerated source passage IDs
and copies quotations locally. All 1,868 final results passed validation and
imported into DuckDB as snapshot `5682eae30307e819d503159e`, with
`label_mode=llm_direct_classification`. Scores are null; previous model metrics
are not reused. The active local database and bundled snapshot contain these
results. The earlier TF-IDF export remains in private `outputs/real/`.

The runner preserves validated checkpoints, stops after failed request groups,
and never converts missing/failed results to no-mention. Private exports include
all per-review states and request provenance, the frontend JSON, and counts by
aspect under ignored `outputs/llm/`. The API key is read from an ignored `.env`
and is not written to result metadata. The software suite covers quote/source-ID
validation, missing results, true denominator counts, counterevidence, provider
failures, checkpoint resume, and fresh-clone seeding. Independent human accuracy
evaluation remains pending; source fidelity does not establish label accuracy.

After updating the bundled results, the full suite passed **54 tests**. Browser
verification confirmed all 79 mapped locations, changed physical classifications,
and financial-access evidence (including 23 barrier reports at the selected
Santa Clara clinic). The model badge, import button and provisional-label banner
are absent as requested. No browser console warnings/errors were recorded.
JavaScript syntax and diff whitespace checks passed.

The sections below preserve earlier verification contexts and their limits.

---

# Clone-and-run verification — November 15, 2026

The local launcher was tested from a clean copy of the app without raw `data/`,
private `outputs/`, an existing database or a preinstalled virtual environment.
It created `.venv`, installed only `duckdb==1.4.4`, and started the loopback app
with the existing real snapshot: **79 mapped locations, 1,868 retained reviews
summarized, and 365 excerpts**. Its active snapshot remained
`4887f6bd845d108a5285f537`. Packaging did not rerun training or the new matcher.

Browser verification confirmed the real location list/map, password form,
cleared password field after submission, enabled LLM option with a dummy key,
key removal, and an offline answer using all 79 locations/1,868 sampled reviews.
No browser console warnings/errors were recorded. The dummy key was absent from
the local database files. Settings return only availability and model, refuse
cross-origin changes, and disable browser key entry for non-loopback-bound
servers. Separate server instances do not share entered keys.

The full suite passed **46 tests**, including notebook execution/export/import,
bundled real-result seeding, existing-import preservation, key configuration,
HTTP contracts, and mocked OpenAI calls using the provided key without returning
it. JavaScript syntax and diff whitespace checks passed. No paid/live OpenAI
request was made; actual provider access remains for testers to verify using
their own key. Offline fallback is shown explicitly and is not reported as an
LLM success.

The reports below preserve earlier verification contexts and their limits.

---

# Improvement-development verification — November 15, 2026

See [IMPROVEMENTS.md](IMPROVEMENTS.md) for the changes in this checkout and reproducible commands. The final combined suite passed **39 tests**, including HTTP/chat, alternative matching, closure safety, model/annotation invariants and notebook-to-app integration. JavaScript syntax and diff whitespace checks passed.

The full Reviews file was obtained and profiled again. The Places download remains quota-blocked, so a new real-data join/training run and coverage gain are not established. Human evaluation, live LLM calls, real OSM enrichment and visual browser QA remain uncompleted. Browser origin approval was declined for Drive and localhost. The earlier results below are historical; they are not claims about this new checkout.

---

# Colab verification and implementation review

Reviewed November 14, 2026 (Pacific). Source: `zen0072/fall2026_datathon`, main commit `05ad25d35f053f210efca177ab198dccf795c3b3`.

## Current result: full local real-data run

The user supplied the full Places CSV on November 14, 2026 (Pacific). Both full organizer files passed schema checks and were loaded locally: 147,429 Places rows and 213,536 Reviews rows. The actual notebook completed in real mode, passed its integrity checks, and exported/imported **word TF-IDF + logistic regression predictions** for **79 mapped locations, 1,868 retained reviews, and 365 aspect excerpts**. The frontend is now the requested single-page list/map explorer.

The current database model is `tfidf_word`, not the earlier reviews-only keyword baseline. `FRONTEND_MODEL` controls explorer inference separately from the benchmark comparison winner. Keywords remain the comparison winner on rule-generated validation labels, so no advantage over the baseline is claimed. Serialized artifacts confirm a `TfidfVectorizer` and fitted logistic regressions for physical, language and time aspects. Sensory and financial labels have no training variation and use the documented constant no-mention fallback; their accessibility is unsupported.

Source overlap is limited: 2,985 raw review rows have a Places ID match; after empty-review and closure filtering, 2,837 rows match (about 1.33% of eligible review rows). The retained essential-service subset has 1,868 reviews after 5 normalized duplicates are removed. Every exported location has valid coordinates. No human annotations were supplied, so training is provisional and independent test evaluation remains blocked. This verifies real-data execution and source/prediction integration, not real-world model accuracy.

The suite passed all 13 tests, including an actual synthetic notebook export pinned to `tfidf_word` and imported unchanged into DuckDB, with nonbinary model probabilities. Private artifacts include source hashes, frozen selection, trained models, split manifest, the exact executed notebook source, run status/log and frontend JSON under ignored `outputs/real/`. Later notebook documentation updates do not alter the archived executed source.

## Initial Colab review outcome

The repository version did not run cleanly in the current Colab environment. The included corrected notebook passes synthetic execution and interactive dashboard checks. A full real-data run remains blocked by the organizer's Google Drive download quota. Do not describe this as completed real-data verification or validated model performance.

## Follow-up: actual Reviews file and explicit partial frontend run

On November 14, 2026 (Pacific), the connected Google Drive download succeeded for the **full Reviews CSV**: 221,618,514 bytes, 213,536 rows, 6,108 place IDs, SHA-256 `1787435e1efbaddd88256efe38d481cec2b442e754bbe3d6b9e9e03d7a8674d0`. The file is cached under ignored `data/`. The full Places CSV remains blocked by Google Drive quota in both the public downloader and normal browser flow; the connector also rejects its 506,418,083 bytes because of its 256 MB limit. No quota bypass or sample substitution was used.

The user explicitly approved loading a **reviews-only** subset. `scripts/import_real_reviews.py` extracts the notebook's current keyword baseline, builds business metadata from nonempty review fields, and exports/imports an explicitly partial snapshot. Only 79 of 6,108 business IDs have any review category. Existing service rules identify 7 candidate clinic locations; normalized exact deduplication retains 733 reviews and 68 aspect excerpts. Pharmacy/grocery matches are absent from this limited category coverage, not established absent from the region. The app displays the source gap, missing coordinates and unknown closure status. Actual addresses include businesses outside the Bay Area; this subset has no regional filter.

This is **real source ingestion and provisional keyword screening**, not a full notebook run, a two-dataset join, trained-model fitting, or independent model validation. Observed keyword errors include recovery narratives containing “wheelchair” or “stairs” without a facility-access issue. No accuracy scores or probability values are supplied for this run. Source hashes, baseline hash, counts and limitations are stored with the snapshot; raw reviewer identity columns are excluded from derived analysis records. The expanded suite passed all 13 tests, including sparse category propagation, duplicate screening, unknown dates, no fabricated coordinates, preserved contradictions, and rejection of an incompatible source file.

Browser verification confirmed the 7 real candidate locations, missing-coordinate placeholder, partial-source warning, the 213,536/6,108/79 source-coverage counts, and the explicit no-training/no-evaluation status. No JavaScript errors were recorded.

## Fixed in the earlier notebook review

1. **Python 3.13 installation:** Colab reported Python 3.13.18. NumPy 2.0.2 fell back to a lengthy source build because no matching wheel was available. Updated to NumPy 2.2.6 and added `--only-binary=:all:` to the install cell. Installation of the corrected pins completed in Colab.
2. **Colab environment compatibility:** SciPy 1.14.1 conflicted with preinstalled JAX's SciPy >=1.15 requirement. Updated to SciPy 1.15.3. Notebook and requirements pins match.
3. **Map rendering:** The original OpenStreetMap tiles displayed 403 access-blocked images in Colab. A CARTO trial required an API key. The final Esri.WorldStreetMap basemap rendered geographic tiles and markers successfully, with provider attribution. External tile availability can still change.
4. **Closed locations:** The original pipeline discarded closure flags. The corrected pipeline parses explicit true/false values, excludes explicitly permanently closed locations, preserves unknown status, and labels temporary closures in the table and summary. Unmarked locations are not certified open.
5. **Memory and privacy:** CSV readers now load only analysis columns, avoiding unnecessary nested fields and reviewer identity columns. Audit text distinguishes analysis-column statistics from full-file statistics. Real-scale memory savings have not been benchmarked because acquisition was blocked.
6. **Regression coverage:** Added offline integration tests for closed/unknown/temporary flags, evidence integrity, exports, widget callback filters, synthetic evaluation and the provisional no-human-label path.

## What was actually tested

| Check | Result |
| --- | --- |
| Original notebook syntax | Python analysis cells compile |
| Original synthetic pipeline, local | Completed |
| Corrected installation cell, Colab Python 3.13.18 | Completed |
| Full Places acquisition, local and Colab | Failed: Drive quota |
| Corrected 15 analysis cells, Colab diagnostic harness, synthetic fixture | Completed in order; integrity assertions and exports completed |
| Final dashboard cell after basemap change | Executed separately in Colab; geographic tiles and markers visible |
| Service/aspect filters | Pharmacy + language returned 60 synthetic places |
| Recency filter and evidence details | UI events completed; selected detail displayed exact synthetic evidence |
| Local closure and no-human-label regression tests | Both pass |
| Real-data training, real-scale performance and actual schema beyond downloader checks | Not verified |
| Independent real-world accuracy and subgroup fairness | Not established; no human labels supplied |

Colab verification used an appended diagnostic cell that executes the corrected analysis-cell source in sequence with MODE explicitly changed to synthetic. It was not a fresh whole-notebook real-data Run all. The distributed notebook retains MODE="real" and has no fabricated execution outputs. The live browser test page contains diagnostic cells; use the included notebook for the clean version.

## Blocking issues outside the code

Google Drive returned: “Too many users have viewed or downloaded this file recently” for `google_maps.csv` (file ID `1T9ftw9sEYKD9JiCNah4L_vPxQ8nEnrE2`). The downloader correctly stops instead of silently substituting synthetic or sample data. The Reviews file was not reached in that run. Use authorized existing full CSV copies or ask the organizer for an available download source; do not bypass access restrictions.

GitHub's connected integration returned HTTP 403 `Resource not accessible by integration` when creating a branch. Terminal push also lacked credentials. The initial verification pass could not push through either route. In the follow-up, the user authorized pushing and the signed-in GitHub web editor was used to commit the corrected notebook, requirements, tests, and this report to main. The downloadable package from the initial pass also includes an applicable patch.

## Remaining implementation/research limitations

- Without human development labels, classifiers are trained against keyword-generated labels and validation selection favors agreement with those rules. Such scores do not establish real model quality. The notebook correctly blocks independent test metrics without adjudicated human labels.
- Summary generation is deterministic, not an implemented LLM integration. This is acceptable for a reproducible baseline but should be described accurately.
- The map covers places with matched, retained target-service reviews. Places with no matched reviews are absent rather than shown as a complete service inventory.
- The annotation queue's actual topic coverage and the Places–Reviews join rate require the real dataset audit. Sparse categories may require narrowing the project.
- The notebook creates slides and a video script, not a recorded video. Submission and stakeholder verification remain outstanding.

## Use the correction

Choose either direct file replacement or the patch, not both:

1. Replace `Access_Beyond_the_Map.ipynb` and `requirements.txt` with these versions; add `tests/test_notebook.py` and this report.
2. Alternatively, from the repository root at the reviewed commit, run `git apply --check colab_fixes.patch`, then `git apply colab_fixes.patch`.

Install locally with `python -m pip install -r requirements.txt`. Run offline checks with `python -m unittest discover -s tests -v`. In Colab, upload the corrected notebook and Run all. For a software-only smoke test set MODE to synthetic; keep it real for actual analysis. To use authorized existing CSV copies, upload both full source files into `/content/data/` before the acquisition cell; valid existing files are reused. Keep source names unchanged.

After data access is restored, run all in a fresh runtime, inspect schema/join counts and resource use, then create independent human labels before interpreting evaluation metrics.
