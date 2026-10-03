# Michelin — a smarter way to order for the table

IEOR E4577 course project. Given a parsed restaurant menu, the diners' saved profiles and a
per-person budget, the app proposes a table order that satisfies every allergy and diet
constraint, fits the budget including tax and tip, and feeds everyone. If no order can, it
says exactly which constraint to relax.

See `CLAUDE.md` for architecture, ownership, contracts and conventions; `docs/` for the
proposal and design decisions.

## Setup

```bash
uv sync --extra dev          # Python API + tests
cd web && npm install        # frontend
```

## Run

Two terminals during development:

```bash
uv run uvicorn michelin.api:app --reload   # Live recommendations on :8000
cd web && npm run dev                                     # frontend on http://localhost:5173, /api proxied
```

One process for a demo or deploy:

```bash
cd web && npm run build && cd ..
uv run uvicorn michelin.api:app          # http://localhost:8000 serves API and web/dist
```

Tests: `uv run pytest` and `cd web && npm run lint`.

## Deploy

```bash
docker build -t michelin .
docker run -p 8000:8000 --env-file .env michelin
```

The image builds the frontend and serves it with the API. To host the frontend separately,
deploy `web/dist` to any static host and set `window.MICHELIN_API` to the API origin.

## Adding a restaurant

Menus are produced by the LLM stage (`src/michelin/parse/`) as `data/menus/<slug>.json` and
must be human-verified (`"verified": true`) before the API serves them.

## Recommendation workspace

The English-only interface includes course cards, icon actions, a party/budget drawer,
per-diner coverage, menu search, swap comparisons, and a printable order ticket. Changing
settings marks the previous plan stale until replanning succeeds.

The real planner runs without API keys. Target courses and dining style affect ranking;
budget (including tax/tip), portions, kept/excluded dishes, and diner coverage are enforced.
For small menus the search is exact if it completes; on its time limit it can return a
feasible incumbent, without claiming optimality. The API accepts up to 40 reviewed dishes.
Set `MICHELIN_MOCK=1` only for fixture-based demos.

Menu editing and imports are session-local. Paste one English dish per line with its price
at the end, or upload an English PNG/JPEG/WebP menu image (up to 8 MB). Image extraction
requires the `tesseract` executable with English language data (included in the Dockerfile).
If unavailable, text import and manual entry still work. Imported dishes are labeled from the
reviewed hidden-ingredient knowledge base (`data/knowledge/`); dishes it does not recognize
keep unknown dietary flags. Either way they require explicit review before use. No external
AI calls are made.

To label a whole menu file for review: `uv run python -m michelin.parse.label_menu draft.json
-o data/menus/<slug>.json`. The output is unverified. Add `--llm` (with `uv sync --extra llm` and
`gcloud auth application-default login`) to let an LLM map names the knowledge base misses;
set `MICHELIN_LLM_MATCH=1` to do the same for in-app imports. The default provider is
`gemini-2.5-pro` on Vertex AI; `MICHELIN_LLM_PROVIDER=claude-vertex` or `claude` switches it. Stored answers live in
`data/knowledge/llm_matches.json`.

Dishes neither matches go to a spreadsheet for hand labeling: `uv run python -m
michelin.parse.review_workbook export data/menus/<slug>.json -o review.xlsx`, fill the dropdowns,
then `... review_workbook import review.xlsx data/menus/<slug>.json`. The answers used for the
three restaurant menus are kept in `data/menus/review_answers.xlsx`; to rebuild a menu, run
`label_menu` and then this import. Setting `verified: true` stays a manual step. The bad-case evaluation lives in
`eval/` (see `eval/README.md`).

Additional API fields on `POST /api/plan`: `menu_override`, `dish_count_target` (1–20),
and `style_preference` (`balanced`, `lighter`, `favorites`).
`POST /api/menu/evaluate` takes `{menu, diners}` and returns per-dish eligibility and questions.
`POST /api/menu/parse` takes `{text}` or `{image_base64}` and returns extracted text and dishes.
