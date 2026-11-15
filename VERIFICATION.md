# Colab verification and implementation review

Reviewed November 14, 2026 (Pacific). Source: `zen0072/fall2026_datathon`, main commit `05ad25d35f053f210efca177ab198dccf795c3b3`.

## Outcome

The repository version did not run cleanly in the current Colab environment. The included corrected notebook passes synthetic execution and interactive dashboard checks. A full real-data run remains blocked by the organizer's Google Drive download quota. Do not describe this as completed real-data verification or validated model performance.

## Fixed

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
