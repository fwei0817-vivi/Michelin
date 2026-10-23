# Assistant-prepared model responses and offline QA

## What is implemented

The assistant has authored two small structured extraction responses from the supplied,
directly reviewed official Café China and CHILI regular-menu facts (observed 2026-09-30).
They are in `data/prepared/`, with exact source URLs, input text, SHA-256, and returned Menu.
This is replay of a prepared response, not live ChatGPT, OCR, image recognition, or a free
hosted inference endpoint. New inputs need a newly prepared response or an implemented live
adapter. Unknown inputs return 409, never an unrelated menu. No paid/live model API was used.

The planner and grounded explainer remain deterministic. They were already independent of
model calls; adding a fake recommendation model would undermine the rule engine. Only the
menu-understanding boundary is replaceable here.

## Stable provider contract

`POST /api/menu/extract`:

```json
{"menu_id": "cafe_china_regular", "text": "<exact prepared input text>"}
```

Alternatively supply `image_base64` instead of `text` (exactly one input). No prepared image
responses currently exist: arbitrary images, even renamed ones, return 409. Input kind,
menu identity, and input-byte SHA-256 must all match. Text whitespace/newlines are significant.
The prepared text is a curated name/price transcription, not a claim that the response's
additional source-grounded ingredient facts were extracted from that short text alone.

The response always has `{menu, provider, mode, input_sha256, source_url, retrieved_at, notice}`.
`menu` follows the existing Menu schema, with additive `preparation_mode` provenance. Output
is schema-validated and identity/unique-ID checked. Extracted menus are always `verified:false`:
a person must review them before planning. Missing price stays null; the planner rejects it.
Malformed provider outputs/exceptions return 502 without accepting a menu.

`GET /api/model/prepared` lists the exact available prepared text inputs and provenance.
It does not perform extraction or access the internet. The existing `/api/menu/parse` remains
compatible: actual local text parsing/Tesseract OCR, now with an additive `mode` and notice.
It does not silently use prepared responses. Live OCR evaluation is **NOT RUN**.

Python interface in `src/michelin/model.py`:

- Provider has `name`, `mode` (`prepared_replay` or `live`), and
  `extract(ExtractionRequest) -> dict` containing `menu` and optional source/date metadata.
- `PROVIDERS` maps configuration names to provider factories.
- `MICHELIN_EXTRACTION_PROVIDER=replay` is the default and performs file reads only.
- A future genuine API implementation plugs into the same interface and registry; select it
  with the environment variable. HTTP contract, frontend and planner stay unchanged.
  That live adapter, credentials, retries and provider-specific mapping are **not implemented**.
  Selecting an uninstalled provider fails closed, without network calls or fallback.
- Tests inject a replacement factory using the same request/response contract, plus failures.

## Add another authored response without a model call

Prepare exact UTF-8 input text and a Menu-schema JSON response from reviewed source facts;
keep unknowns null/empty and keep evidence tiers honest. Use the same restaurant ID:

```bash
uv run python scripts/register_prepared_response.py \
  --menu-id my_restaurant_regular --input /tmp/menu-input.txt \
  --response /tmp/assistant-menu.json --source-url https://example.org/menu \
  --retrieved-at 2026-09-30 --output data/prepared/my_restaurant_regular.json
```

The command validates the response, computes the input hash, forces review, and refuses to
overwrite an existing record. It neither retrieves the URL nor generates model output. The
operator is responsible for the stated source/retrieval date. Only prepared text records are
registered by this utility; it does not synthesize image results.

## Run the local demonstration

```bash
uv sync --extra dev
npm --prefix web ci --no-audit --no-fund
npm --prefix web run build
MICHELIN_EXTRACTION_PROVIDER=replay MICHELIN_MOCK=0 \
  MICHELIN_PROFILE_DB=/tmp/michelin-local-demo.sqlite3 \
  uv run uvicorn michelin.api:app --host 127.0.0.1 --port 8000
```

Use a retained local path instead of `/tmp` for persistence beyond temporary-workspace
cleanup. Open localhost:8000, select **Bring your own menu → Prepared menu → Replay prepared
response**, add it for review, confirm review, and use that menu. Choose **Three synthetic
diners** on the table screen for an initial feasible scenario. Adjust restrictions/budget,
generate, swap, and inspect per-diner suitability and confirmation questions. Unknown
allergens deliberately prevent validated coverage for allergic diners.

The existing layout is retained. A small optional **Local synthetic profile history** panel
adds explicit per-person saves, revision history, and loading a saved group. Editing a diner
changes tonight's table; it does not persist until **Save current person**. Scope/person IDs
are caller-provided namespaces, not authenticated accounts. Do not use real personal data.
Separate process and actual server-restart tests verify SQLite history when the file remains.
Ephemeral workspace/container replacement can erase it; no persistent volume or production
authentication was provisioned. All test histories use temporary files and are uncommitted.

External font requests were removed so the interface uses local font fallbacks and can run
without external traffic. Browser QA rejects any non-loopback request. Docker includes the
prepared-response data, but a Docker build/deployment was not run in this task.

## Repeatable evaluation

```bash
uv run python scripts/evaluate_offline.py --output /tmp/michelin-offline-evaluation.json
uv run pytest -q
uv run ruff check src tests scripts
npm --prefix web run lint
npm --prefix web run build
# Optional: Python environment with playwright installed and a local Chromium executable
python scripts/browser_offline_qa.py
```

The harness reports individual regression outcomes, totals and explicit NOT RUN fields.
It is not a measurement of live extraction accuracy or a comparison against ordinary ChatGPT.
No synthetic score is presented as model accuracy. The official menus are incomplete excerpts;
all people and error mutations are synthetic. Fee schedules, timed lunch offers, piece-target
optimization and true serving adequacy remain outside scope, as documented previously.

Final recorded results for this change:

- Full backend suite: **78 passed**, two existing Starlette/httpx/anyio deprecation warnings.
- Offline targeted harness: **39/39 passed** (replay, bad cases, order validation, profiles).
- Ruff, frontend TypeScript lint/build, and `git diff --check`: **passed**.
- Chromium desktop loopback QA: **10 checkpoints passed**, zero page errors and zero external
  requests. Includes replay/review/provenance, back and cancel, two profile revisions,
  real-menu plan/coverage, two swaps, swap cancel, changed allergy and uncertainty display,
  over-budget swap failure with Undo recovery, budget no-solution, actual server restart.
- Browser evidence: `/tmp/michelin-browser-qa.json`, `/tmp/michelin-offline-plan.png`.
  These are local QA outputs, not committed personal histories or published artifacts.

Browser coverage is one desktop Chromium scenario using Café China. CHILI is exercised by
backend replay and menu arithmetic tests, not a second full browser path. This is not exhaustive
cross-browser, mobile, accessibility, security, deployment, or load testing. Live model
comparison, live API calls, and restaurant-image OCR evaluation are **NOT RUN**.
