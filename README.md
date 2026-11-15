# Accessibility Explorer

Explore accessibility reports through a map, location list, review evidence, and chatbot. The app includes saved classifications for **1,868 reviews across 79 locations**.

## Set up and run

Install **Git** and **Python 3.11 or later** (3.12 recommended), then run:

```sh
git clone https://github.com/zen0072/fall2026_datathon.git
cd fall2026_datathon
python3 scripts/launch_app.py
```

**Windows:** replace the last command with `py -3 scripts/launch_app.py`.

The launcher creates a virtual environment, installs dependencies, loads the included results into an empty local database, and opens **http://127.0.0.1:8000/**. Internet access is needed for the first installation and map tiles. No raw datasets or model training are required.

- **Stop:** press `Ctrl+C` in the terminal.
- **Restart:** run the launch command again.
- **Port busy:** add `--port 8001` to the launch command.

## Add an API key (optional)

The map and offline chatbot work without an API key. To enable OpenAI evidence selection:

1. In **Ask the review data**, expand **Connection settings**.
2. Enter your **OpenAI API key** and a model available to your account. The default is `gpt-5.6-terra`. Click **Use key for this run**.
3. Enable **Use OpenAI evidence selection**, then ask a question.

Requests use **your OpenAI API billing** and send your question and up to 24 review excerpts. The key stays in the local server's memory; click **Remove key** or stop the app to discard it. Saving a key does not test the connection. The app does not automatically load `.env` files.

## How the data is classified

We developed an initial classification pipeline using **keyword rules and TF-IDF features with Logistic Regression** to identify accessibility reports across Physical, Sensory, Language, Cost, and Time.

We then added **LLM-based contextual reasoning** to interpret ambiguity, negation, and mixed experiences that keyword and statistical methods can miss. This stage classifies the original review text independently using a domain-specific rubric, assigning each accessibility dimension one of four labels: **barrier reported, positive access, mixed/unclear, or no mention**. Supporting passages are extracted verbatim and validated against the source review before results are aggregated by location.

The LLM stage was introduced to improve contextual interpretation and classification accuracy; measured accuracy gains have not yet been established through independent human evaluation.

See the [classification guide](docs/LLM_CLASSIFICATION.md) for details on rerunning the analysis.
