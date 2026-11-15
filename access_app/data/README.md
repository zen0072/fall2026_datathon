# Bundled classified results

`classified_locations.json` is the existing, precomputed real-data export from
November 15, 2026: **79 locations**, **1,868 retained reviews summarized**, and
**365 aspect evidence excerpts**. It uses word TF-IDF and logistic regression.
It is not fictional sample data, and the full 1,868 review texts are not bundled.

The snapshot predates the new alternate-ID/name-address matching changes. Its
source hashes, model selection, provisional label provenance and blocked
independent evaluation remain embedded in the dataset metadata. It has not been
retrained just by packaging it here. Physical, language and time have fitted
classifiers; sensory and financial use constant no-mention fallbacks.

Only the app's analysis fields are included: location metadata, aspect counts,
predictions, dated excerpts and provenance. Raw CSVs, reviewer name/profile
columns, model binaries, local database files and credentials are excluded.
Review excerpts retain the original source wording, so treat them as historical
reports to investigate rather than verified current accessibility.

`python -m access_app serve --bundled` imports these results into an empty local
database. It never replaces an existing imported snapshot. The one-command
launcher uses this option automatically. Import a new notebook export through
the app when you want to replace the active results.
