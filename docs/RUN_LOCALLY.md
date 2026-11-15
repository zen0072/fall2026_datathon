# Run Access Beyond the Map locally

Checked against GitHub main on November 15, 2026, at source commit `c7da1b2ef06e947b9e7ee9f89eebbe4461bd0cce`. No newer source revision was present when the commands were checked. This guide uses the existing Python application and scripts.

The quickest path is the fictional demo: it needs Python and the small app requirements file. You do not need the raw CSVs, notebook dependencies, Node.js, an OpenAI key, or a model-training run to open the website and use its offline chatbot.

## 1. Get the repository

Open Terminal (macOS/Linux) or PowerShell (Windows), then run:

```sh
git clone https://github.com/zen0072/fall2026_datathon.git
cd fall2026_datathon
```

If you already have the repository, open that existing folder in your terminal and update it instead of cloning again:

```sh
git pull --ff-only origin main
```

If Git reports local edits or divergent history, preserve those changes before updating; do not reset or delete them to follow this guide. Downloading and extracting the GitHub ZIP is also an option; open the extracted folder containing `README.md` and `access_app`.

All following commands assume you are in the repository root. The commands use the virtual environment's Python explicitly, so activation is unnecessary.

## 2. Create a Python environment

Use Python 3.11–3.13; Python 3.12 is recommended for consistency with the checked notebook environment. Install an appropriate Python version if it is not already available.

**macOS/Linux:**

```sh
python3.12 --version
python3.12 -m venv .venv
```

If your compatible Python is named `python3` instead, use that command to create `.venv`.

**Windows PowerShell:**

```powershell
py -3.12 --version
py -3.12 -m venv .venv
```

If the `py` launcher is unavailable but `python --version` reports a supported version, use `python -m venv .venv`.

## 3. Install website dependencies

**macOS/Linux:**

```sh
.venv/bin/python -m pip install -r requirements-app.txt
```

**Windows PowerShell:**

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-app.txt
```

The app requirements currently contain DuckDB. The full notebook dependencies in `requirements.txt` are only needed for training, data auditing, or the complete test suite.

## 4. Start the fictional demo

**macOS/Linux:**

```sh
.venv/bin/python -m access_app serve --demo --db var/demo.duckdb
```

**Windows PowerShell:**

```powershell
.\.venv\Scripts\python.exe -m access_app serve --demo --db var/demo.duckdb
```

Expected terminal output includes:

```text
Access workspace: http://127.0.0.1:8000/
DuckDB: .../var/demo.duckdb
```

Leave this terminal open. Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/) in your browser. You should see four fictional locations, service/aspect filters, the map/list, evidence details and the question form. The demo database is separate from `var/access.duckdb`, which the real-data instructions below use.

The `--demo` flag seeds examples only when the selected database has no snapshot. It never replaces existing imported results. If `var/demo.duckdb` was previously populated with different results, choose a new database filename to get a fresh demo without deleting anything.

## 5. Try the website

1. Select **Physical**, **Language**, **Cost**, or another aspect.
2. Filter by clinic, pharmacy or grocery, or search a location name/address.
3. Select a location to inspect supporting and conflicting review excerpts.
4. In **Ask the review data**, try “Which clinics have the most language barriers?” or “How reliable is this?”
5. Leave the LLM option off for offline retrieval. No API key is required.

The demo is fictional software test data. It does not demonstrate real-world model accuracy or current accessibility. Internet access is needed for basemap tiles; the stored list, evidence and offline chatbot remain available if tiles fail.

## 6. Stop and restart

Press **Ctrl+C** in the server terminal. To restart, run the same serve command again. The database persists on disk.

If port 8000 is already in use, choose another port:

```sh
.venv/bin/python -m access_app serve --demo --db var/demo.duckdb --port 8001
```

Then open [http://127.0.0.1:8001/](http://127.0.0.1:8001/). Use the same Windows Python executable substitution for this and later Python commands.

Do not start two processes using the same DuckDB file. Stop the first one, use its browser import button, or use separate database files for separate instances.

## 7. Use real notebook results

A fresh Git clone contains code and fictional examples, not the historical private raw files, trained artifacts, results JSON or database.

**If you already have `frontend_results_PRIVATE.json`:**

Start a separate real-results database, without seeding a demo:

```sh
.venv/bin/python -m access_app serve --db var/access.duckdb
```

Click **Import results** and choose the exported JSON. The map/list refresh after a successful import. Select the JSON file, not the notebook, a raw CSV, or the results ZIP; extract the ZIP first if needed. Browser imports are limited to 128 MiB.

Alternatively, stop the server and import through the command line:

```sh
.venv/bin/python -m access_app import "/path/to/frontend_results_PRIVATE.json" --db var/access.duckdb
.venv/bin/python -m access_app serve --db var/access.duckdb
```

Replace the example path with the actual file path. The importer validates the result before switching the active snapshot.

**If you need to generate results locally:**

Install the notebook requirements as well:

```sh
.venv/bin/python -m pip install -r requirements.txt -r requirements-app.txt
```

Place the full organizer CSVs at:

```text
data/google_maps.csv
data/google_maps_reviews.csv
```

Then, with the server stopped, run:

```sh
.venv/bin/python scripts/run_real_notebook.py --prediction-model tfidf_word --db var/access.duckdb
.venv/bin/python -m access_app serve --db var/access.duckdb
```

The runner executes the notebook and imports only after successful completion. It can download missing sources through the notebook's acquisition code, but the Places file was quota-blocked during this session. If acquisition fails, obtain the authorized full file; no sample or synthetic substitution happens silently. Keep using the separate demo while access is unavailable.

Other supported model selections are `tfidf_word_char`, `tfidf_nb` and `validation_winner`. Inspect `outputs/real/run_status.json` and `outputs/real/run_PRIVATE.log` when a run stops. Human annotations in `data/labels.csv` are required for independent evaluation; predictions trained on provisional rules remain labeled as provisional.

## 8. Optional: enable OpenAI evidence selection

This step is optional. The chatbot works in offline mode without it. The app uses the LLM to select evidence IDs, while counts, rankings and displayed explanations are produced locally.

Create a file named **`.env`** beside `README.md` with your own values:

```dotenv
OPENAI_API_KEY="your-api-key"
ACCESS_CHAT_PROVIDER="openai"
ACCESS_CHAT_MODEL="your-supported-responses-model-id"
```

Replace the placeholders. The model must be available to your API account and support structured output through the Responses API. `.env` is ignored by Git. Do not place the key in frontend JavaScript or commit it. The application does **not** automatically load `.env`.

**macOS/Linux:** stop the server, load the file you created, and restart from the same terminal:

```sh
set -a
source .env
set +a
.venv/bin/python -m access_app serve --demo --db var/demo.duckdb
```

Use `--db var/access.duckdb` without `--demo` to serve an imported real-results database instead.

**Windows PowerShell:** set process-local environment variables before launching the app. The key prompt below does not display the key as you type:

```powershell
$secureKey = Read-Host "OpenAI API key" -AsSecureString
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new("", $secureKey).Password
$env:ACCESS_CHAT_PROVIDER = "openai"
$env:ACCESS_CHAT_MODEL = "your-supported-responses-model-id"
.\.venv\Scripts\python.exe -m access_app serve --demo --db var/demo.duckdb
```

Refresh the webpage and explicitly select the LLM option. Configuration availability does not prove the key/model works; each answer states whether LLM selection succeeded or offline retrieval was used. Opting in sends the question and bounded evidence excerpts to OpenAI. Use only data you are permitted to transmit.

Live testing was deferred by the user. When ready to perform two bounded live calls using fictional evidence, run:

```sh
.venv/bin/python scripts/test_live_llm.py --env-file .env
```

On Windows, replace the Python executable as above. If variables are already configured in the current terminal, omit `--env-file`. The script writes `outputs/live_llm_test.json`:

| Exit | Meaning |
|---|---|
| `0` | Both live checks passed |
| `1` | A live check failed; offline fallback cannot count as success |
| `2` | Required configuration missing; no calls attempted |

No paid live call was made while checking this guide.

## 9. Script reference

| Command/file | Use it when | Requirements |
|---|---|---|
| `python -m access_app serve` | Launch website | `requirements-app.txt`; imported data or `--demo` |
| `python -m access_app import ...` | Import notebook results through CLI | App dependencies; stop server using the same DB |
| `scripts/run_real_notebook.py` | Train/compare/export on full sources | Both requirements files and full source access |
| `scripts/compare_matching.py` | Audit matching/filter alternatives | Notebook dependencies; CSV inputs |
| `scripts/test_live_llm.py` | Explicitly check live provider behavior | App dependencies, API key/model; optional literal env file |
| `scripts/import_real_reviews.py` | Intentionally create a partial Reviews-only snapshot | Separate fallback workflow; not equivalent to the full joined pipeline |

There is no separate npm server or setup shell script on the checked main branch. The supported website entry point is `python -m access_app`.

## 10. Troubleshooting and verification

| Symptom | What to check |
|---|---|
| `No module named access_app` | Run from the folder containing `access_app`, beside `README.md` |
| `No module named duckdb` | Install `requirements-app.txt` using the same `.venv` Python used to launch |
| Python version command not found | Check the installed Python name/version; create `.venv` with Python 3.11–3.13 |
| Blank/empty results | No snapshot is loaded; use the demo flag with an empty database or import valid results |
| Address already in use | Stop the other server or choose `--port 8001` |
| Database lock error | Another process owns the same DuckDB file; stop it before CLI imports/runs |
| LLM checkbox disabled | Provider must be `openai`, with key and model in the server's environment; restart server and refresh |
| LLM request falls back | Check account/model access and provider connectivity; inspect the explicit live-test result when you choose to run it |
| Drive quota/download error | Full-data execution is blocked; the fictional demo remains available |
| Missing map tiles | Check network availability; use the list and evidence in the meantime |
| Import rejects a file | Use the notebook's versioned frontend JSON, not raw data or a manually altered schema |

Health check after startup: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health) should return JSON containing `"ok": true`.

To run the full software suite after installing both requirements files:

```sh
.venv/bin/python -m unittest discover -s tests -v
```

**What was checked for this guide:** a fresh Python 3.12 environment with only `requirements-app.txt`; actual server startup; four fictional demo locations; health and location APIs; HTML serving; offline chatbot aspect/service resolution; and the live-test script's missing-configuration exit with zero calls. These checks passed. The script help commands match the instructions. Earlier full verification passed 39 tests. Visual browser QA, real-data retraining and live LLM success are not claimed by this guide.

For implementation details, see [system design](SYSTEM_DESIGN.md) and [evidence assistant configuration](evidence-assistant.md).
