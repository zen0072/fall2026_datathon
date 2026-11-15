# Bundled classified results

`classified_locations.json` is the existing, precomputed real-data export from
November 15, 2026: **79 locations**, **1,868 retained reviews summarized**, and
**1,303 aspect evidence excerpts**. All 1,868 reviews were classified directly
with OpenAI `gpt-5.6-terra`, yielding 9,340 aspect classifications. It is not
fictional sample data, and the full collection of review texts is not bundled.

The run reuses the historical matched and deduplicated review cohort; it does
not rerun the new alternate-ID/name-address matcher. Each aspect is classified
as no mention, barrier, positive access, or mixed/unclear using a documented
rubric. The model selects numbered source passages and the application copies
their exact original text. No keyword-generated training labels or old TF-IDF
predictions are supplied. Source hashes, model/rubric provenance and the pending
independent human evaluation are recorded in metadata. Probability scores are
null rather than fabricated. All five aspects use the LLM, including sensory
and financial access. The original TF-IDF export remains in private outputs.

Only the app's analysis fields are included: location metadata, aspect counts,
predictions, dated excerpts and provenance. Raw CSVs, reviewer name/profile
columns, model binaries, local database files and credentials are excluded.
Review excerpts retain the original source wording, so treat them as historical
reports to investigate rather than verified current accessibility.

`python -m access_app serve --bundled` imports these results into an empty local
database. It never replaces an existing imported snapshot. The one-command
launcher uses this option automatically. To replace active results, stop the app
and use the command-line importer, then restart.
