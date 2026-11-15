# Evidence assistant

The explorer includes **Ask the review data**. Clone the repo and launch the existing real classified snapshot:

```sh
python3 scripts/launch_app.py
```

Ask a question and optionally restrict to the selected location. Aspect, service and location-name/address search follow the explorer controls. Explicit single-aspect or service words in the question override the explorer defaults; the response discloses this. Questions about counts, ranking, verification and reliability receive intent-specific explanations; unrelated questions are identified as unsupported. Classification is intentionally always **all** to retain positive, mixed and insufficient evidence. A response records the exact scope and snapshot; changing filters does not change an already returned answer. Questions are independent: conversation history is not sent or persisted.

Offline mode works without credentials. It computes exact aggregate counts across the full filtered snapshot, ranks up to five places by barrier counts then mixed counts/name/ID, and retrieves up to 22 review excerpts using lexical question terms then recency, reserving two additional slots for positive and mixed counterevidence from the full filtered scope. It shows up to eight matches plus positive/mixed counterevidence when present among candidates. Excerpts are capped at 1,200 characters. Counts do not come from the truncated evidence context. Ranking is a verification workload heuristic, not a best/worst accessibility rating. Unequal review volume, sample selection and weak labels limit interpretation; zero barrier reports do not establish access.

## Optional OpenAI evidence selection

On the locally running page, expand **Use your own OpenAI key**, enter your API key and model, then choose **Use key for this run**. The key is submitted once to the same-origin local Python server; the password field clears and the app never stores it in localStorage, sessionStorage, cookies, DuckDB or a results file. Settings are isolated to that server instance, not persisted between server runs. **Remove key** switches this run to offline mode, including when environment credentials were initially configured. Browser-entry settings are disabled if the server binds to a non-loopback interface. Keep the default loopback address.

Saving a key makes no provider request and is not a connection test. Select **Use LLM evidence selection** and ask a question to try it; the response explicitly shows LLM or fallback mode. Requests use the tester's own OpenAI API billing. The default `gpt-5.6-terra` supports Responses structured outputs, and its request disables reasoning for bounded evidence selection. The model ID can be changed to another compatible model available to the tester's account.

Alternatively, configure these **server-side** environment variables before starting the app:

```sh
export ACCESS_CHAT_PROVIDER=openai
export ACCESS_CHAT_MODEL=YOUR_RESPONSES_API_MODEL
export OPENAI_API_KEY=YOUR_KEY
python -m access_app serve --db var/access.duckdb
```

Select a model available to your account that supports structured outputs in the Responses API. When using environment configuration, the provider must be `openai` and a key must be present; a missing model uses the default above. The user must opt in on each browser session. Requests send the question and bounded evidence (including location names and excerpts) to OpenAI. The server never returns the key to the browser, API responses or results bundle. The app requests `store:false`; this is not a promise about provider retention policies. `.env` files are not automatically loaded.

The LLM selects relevant citation IDs from retrieved evidence. It does **not** calculate counts, change ranking, supply SQL, call tools, or generate displayed factual claims. Verification suggestions are curated per aspect. This intentionally conservative extractive design supports evidence exploration rather than unrestricted conversational answers. Citations alone cannot validate generated statements, so free-form model prose is not displayed. Unsupported questions receive scope evidence and an explicit limitation rather than invented answers. Missing configuration, provider errors, invalid IDs, incomplete output, or excess concurrency fall back to offline retrieval with a visible mode label.

Question length is limited to 1,500 characters; filters to 200 characters; requests to 64 KiB. Model output is limited to 500 tokens and 128 KiB; calls time out after 20 seconds, with at most two concurrent calls per process. All input text is treated as untrusted in the system instruction; server-side ID allowlisting and local rendering enforce the output boundary. UI escapes all evidence. These controls cannot make arbitrary model prose trustworthy, which is why the model may only select evidence IDs.

The app is a local loopback tool, not an authenticated public service. Keep its default loopback binding.

Provider contract checked against [OpenAI Responses API reference](https://developers.openai.com/api/reference/resources/responses/methods/create). Tests mock provider output and make no paid API calls. Run `python -m unittest discover -s tests -v` and `node --check access_app/static/app.js`.

Credential handling follows [OpenAI API key guidance](https://developers.openai.com/api/docs/guides/api-keys). Default model capabilities: [GPT-5.6 Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra).

## Live smoke test (deferred)

The live test was explicitly deferred by the user on November 15, 2026. No live provider success is claimed. Once credentials and a supported model are configured, run:

```sh
python scripts/test_live_llm.py --env-file .env
```

This sends only fictional demo evidence in two bounded calls, checks actual LLM mode, citations, counterevidence and deterministic counts, and writes `outputs/live_llm_test.json`. Exit 2 means missing configuration; exit 1 means test failure. Offline fallback cannot pass this live test. The optional env file accepts literal KEY=value entries only, never executes shell code, and is used only by this test script.
