# Michelin — a smarter way to order for the table

IEOR E4577 course project. Given a parsed restaurant menu, the diners' saved profiles and a
per-person budget, the app proposes a table order that satisfies every allergy and diet
constraint, fits the budget including tax and tip, and feeds everyone. If no order can, it
says exactly which constraint to relax.

See `CLAUDE.md` for architecture, product rules and conventions; `docs/` for the proposal
and design decisions.

## Setup

```bash
uv sync --extra dev
cp .env.example .env    # then put your ANTHROPIC_API_KEY in .env
uv run pytest
uv run uvicorn michelin.api:app --reload   # http://localhost:8000
MICHELIN_MOCK=1 uv run uvicorn michelin.api:app --reload   # canned plan/conflict for frontend work
```

## Deploy

```bash
docker build -t michelin .
docker run -p 8000:8000 --env-file .env michelin
```

The image serves the API and the static frontend together. To host the frontend separately,
copy `web/` to any static host and set `window.MICHELIN_API` to the API origin.

## Adding a restaurant

Menus are produced by the LLM stage (`src/michelin/parse/`) as `data/menus/<slug>.json` and
must be human-verified (`"verified": true`) before the API serves them.
