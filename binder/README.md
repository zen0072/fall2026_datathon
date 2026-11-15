# Classify your own reviews

Binder opens `Classify_Your_Own_Data.ipynb` in JupyterLab. It does not launch the
app, read its saved predictions, or download the organizer datasets. API calls
are made only when a user explicitly enables the LLM method and paid requests.
Run the small invented example first, then upload your CSV, set `INPUT_CSV`, and
run the notebook again. The only required columns are `place_id` and `review`.
The organizer Reviews CSV is supported directly; this workflow does not join
the Places dataset or reproduce the historical 79-location cohort.

Choose keyword rules, TF-IDF + Logistic Regression, or OpenAI LLM classification
with your own API key. Rule-derived training
labels are provisional. To train on your own human annotations, complete the
exported template and set `LABELS_CSV` and `TRAINING_LABEL_SOURCE = "human"`.
Keep the input, seed and sample limit unchanged when adding annotations. Never
use model predictions as independent test labels.

Download the results ZIP before leaving. Binder sessions are temporary. Use a
sample (2,000 reviews by default, maximum 10,000); the larger analysis notebook
is available for full local workflows. Public Binder is a shared cloud service;
use shareable data and enter a key only through the masked runtime prompt.

For LLM classification, set `METHOD = "llm"`, choose `OPENAI_MODEL`, reduce
`MAX_REVIEWS` to a small pilot (for example 20), and set
`ALLOW_PAID_API_CALLS = True`. The notebook checks `LLM_MAX_NEW_REQUESTS` (default
20) before prompting for a key. One uncached review is sent per request; your
OpenAI account is billed. The limit counts requests, not dollars. The key is
never written to a file, output, notebook cell or environment variable. Restart
the kernel after the run to release memory. Masked input is not a guarantee of
privacy on public infrastructure.

Validated results are checkpointed; API failures stop processing without
inventing labels. The results ZIP includes the checkpoints, model/response IDs,
token usage, and classification rubric. To resume in another session, extract
the ZIP into `outputs/workshop/llm/`, restore the same data and settings, then
rerun. Fully cached runs need no key or paid requests. This model classifies your
uploaded sample independently; the separate
[historical LLM runner](../docs/LLM_CLASSIFICATION.md) retains its original scope.

## Run locally or verify

From the repository root with Python 3.12 and a virtual environment:

```sh
python -m pip install -r binder/requirements.txt
python -m jupyterlab Classify_Your_Own_Data.ipynb
```

Execute all notebook paths without opening a browser or making paid requests:

```sh
python scripts/check_classification_notebook.py
python scripts/check_classification_notebook.py --method tfidf_logreg
python scripts/check_classification_notebook.py --method llm
```

Binder uses `binder/requirements.txt` and `binder/runtime.txt`; the root app and
analysis requirements remain separate. `postBuild` verifies the notebook in a
temporary workspace without saved app results; the LLM check uses fake responses
and a fake key. Dependencies used directly by
this workflow are version-pinned; Python is pinned to the 3.12 series, and this
is not a complete transitive dependency lock.

The README badge follows `main`, so it needs these files pushed to GitHub before
it works. For an archived experiment, replace `main` in the Binder URL with the
full Git commit hash and retain the downloaded ZIP with its source checksums,
split manifest, rubric, code hashes, configuration and environment versions.

References: [Binder configuration](https://repo2docker.readthedocs.io/en/latest/use/repository/),
[launching a notebook](https://mybinder.readthedocs.io/en/latest/howto/user_interface.html),
[service limits and privacy](https://mybinder.readthedocs.io/en/latest/about/user-guidelines.html).
