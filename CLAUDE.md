# Michelin — group ordering assistant

Course project for IEOR E4577 (Product Management with AI), Columbia, Fall 2026.
Three owners: **frontend**, **backend**, **LLM**. This file defines the skeleton, the contracts
between the three parts, and how we work together. Implementation detail belongs in each
owner's module docstrings, not here.

## What we are building

3–6 people at a Chinese restaurant, one person orders for the table. Input: a pre-parsed
menu, the diners' saved profiles (allergies, diets, preferences) and a per-person budget.
Output: a table order that satisfies every hard constraint, or a precise statement of which
constraint to relax. Background and the reasoning behind each decision: `docs/decisions.md`.

## Pipeline and ownership

| Stage | Owner | Code | Produces |
|---|---|---|---|
| Understand: menu photos/text → reviewed dishes; explain a plan | LLM | `src/michelin/parse/`, `explain.py` | `data/menus/<slug>.json`, `Plan.items[].reason` |
| Decide: `Menu` + `TableRequest` → `Plan` or `Conflict` | Backend | `src/michelin/plan/`, `api.py`, `Dockerfile` | `POST /api/plan` |
| Present: table, budget → the order slip, or a conflict | Frontend | `web/` (React + Vite + Tailwind) | the page users see |
| Shared | all three | `schemas.py`, `data/`, `docs/`, `tests/` | the contracts below |

Division of trust: the LLM never selects dishes, the optimizer never guesses ingredients, the
frontend never re-checks constraints. Each stage renders or consumes what the previous one
produced.

## Contracts

These are the only things one owner needs from another. Change them by PR only, with both
other owners tagged, and update the sample data and tests in the same PR.

**1. Schemas** — `src/michelin/schemas.py`. `Menu`, `Dish`, `DinerProfile`, `TableRequest`,
`Plan`, `Conflict`. Every JSON file under `data/` and every API payload has one of these
shapes. Dish `id`s are stable ASCII slugs (`mapo_tofu`) referenced by plans and eval labels.

**2. HTTP API** — `src/michelin/api.py`, same origin as the frontend by default.

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/api/menus` | | `[{slug, restaurant_name, cuisine, verified, n_dishes}]` |
| GET | `/api/menus/{slug}` | | `Menu` |
| GET | `/api/profiles` | | `[DinerProfile]` |
| POST | `/api/plan` | `{menu_id, diner_ids?, diners?, budget_per_person, tax_rate?, tip_rate?, min_dishes_per_person?, locked_dish_ids?, excluded_dish_ids?, menu_override?, dish_count_target?, style_preference?, explain?}` | `{kind: "plan", plan, subtotal_cap}` or `{kind: "conflict", conflict, subtotal_cap}` |
| POST | `/api/menu/parse` | `{text?, image_base64?}` | `{dishes: Dish[], text}`: name and price rows, labeled from `data/knowledge/` with evidence tiers (unrecognized dishes stay unknown); images need `tesseract` on the server |
| POST | `/api/menu/evaluate` | `{menu, diners}` | per dish: `edible_by`, `blocked_for` reasons per diner, staff `questions` |

`diner_ids` name saved profiles; `diners` carries edited or ad-hoc people inline and wins on the
same id; at least one of the two is required. `menu_override` plans against a menu edited in
the browser instead of the saved one; it must be `verified`, have unique ids, prices on every
dish and at most 40 dishes. `locked_dish_ids` must stay on the slip,
`excluded_dish_ids` must not appear (both reach the optimizer via `TableRequest`).
Optional `dish_count_target` and `style_preference` (`balanced` | `lighter` | `favorites`)
steer the objective only. Errors: `404` unknown menu, diner or dish, `503` when the search
times out. `MICHELIN_MOCK=1` makes `/api/plan` answer from `data/fixtures/`: the dish
selection is fixed (minus excluded, plus locked) but `edible_by`, totals, checks and staff
questions are computed for real, and a budget under $20 returns the sample conflict.

**3. Sample data** — `data/menus/sample_sichuan.json`, `data/profiles/sample_group.json`,
`data/fixtures/plan_sample.json`, `data/fixtures/conflict_sample.json`. This is the shared
test bed; `tests/test_schemas.py` checks that all of it validates.

## Product rules everyone must respect

1. **Allergen claims carry an evidence tier**: `menu`, `inferred` or `unknown`. The UI wording
   follows the tier ("contains peanuts", "usually contains pork", "ask staff about the sauce").
2. **We never say "does not contain X".** The strongest negative is "no evidence of X". Every
   plan ships a `confirm_with_staff` list and the frontend always shows it.
3. **Allergies and diets are hard constraints; taste is soft.** A dish with a `null` diet flag
   counts as unsafe.
4. **Coverage is per person.** Each diner must be able to eat `min_dishes_per_person` dishes.
5. **Budget is all-in** (tax and tip included). Defaults are NYC: 8.875% tax, 18% tip.
6. **Infeasible means say so**, with concrete relaxations. Never drop a constraint silently.
7. **Variety, not nutrition.** We make no nutrition claims.

## Repository layout

```
CLAUDE.md, README.md, pyproject.toml, Dockerfile, .env.example
docs/          proposal.md (as submitted), decisions.md (why things are the way they are)
data/          raw/ menu photos · menus/ parsed JSON · profiles/ · fixtures/ (mock responses)
src/michelin/  schemas.py · api.py · explain.py · parse/ · plan/
web/           React + Vite + Tailwind; src/types.ts mirrors schemas.py; dist/ is served by api.py
tests/         pytest
```

## Commands

```bash
uv sync --extra dev                          # install everything into .venv
uv run pytest                                # must pass before any PR
uv run uvicorn michelin.api:app --reload     # API on :8000, serves web/dist when built
MICHELIN_MOCK=1 uv run uvicorn michelin.api:app --reload   # same, with canned plans
cd web && npm install && npm run dev         # frontend on :5173, /api proxied to :8000
cd web && npm run build                      # type-check + build to web/dist
docker build -t michelin . && docker run -p 8000:8000 --env-file .env michelin
```

## Working together

- `main` is always green. Run `uv run pytest` before opening a PR.
- One branch per task, named `<owner>/<topic>`, e.g. `frontend/dish-cards`, `backend/cp-sat`,
  `llm/enrich-prompt`. Squash-merge into `main` via PR.
- Stay in your own area. A one-line fix in someone else's directory is fine; say so in the PR
  and tag them. Anything bigger, ask first.
- Contract changes (schemas, the API table, sample data) get a dedicated PR with no feature
  work mixed in.
- Tests use fixtures and the sample data, never live LLM calls.
- `.env` holds API keys and is never committed. Only the LLM stage needs one; the frontend
  and the optimizer run without it.
- A decision that changes product behaviour goes into `docs/decisions.md` with a one-line why.
- Python ≥ 3.11, `src` layout, pydantic v2; data crosses module boundaries as schema objects,
  not dicts. Code and comments in English; UI strings and displayed dish names are English. Original menu names may remain in source data.
- Each owner documents the "how" in their own module docstrings. For example the optimizer
  model is described in `plan/optimizer.py`, the extraction rules in `parse/`. Keep this file
  to skeleton and contracts.

## Owner notes (one line each; the rest lives in your code)

- **Frontend**: `web/` is React + Vite + Tailwind v4, no server code of its own. `src/api.ts` is
  the only place that talks to the backend and `src/types.ts` mirrors `schemas.py`. The built
  `dist/` is served by FastAPI; to host it elsewhere set `window.MICHELIN_API` to the API origin.
- **Backend**: `solve()` uses bounded search with concrete budget/coverage suggestions. `budget.py`,
  `portions.py`, `edibility.py`, and `score.py` supply the shared checks.
- **LLM**: `parse/` and `explain.py` are yours, including the choice of provider and
  dependencies. The team only depends on the output shapes: a `Menu` JSON that a human has
  marked `verified: true`, and `explain()` returning the plan with every `reason` filled.
  Labels come from `parse/knowledge.py` + `data/knowledge/`; `eval/` scores them.

## Scope (v1)

In: Chinese menus, three verified restaurants, allergens shellfish / fish / peanut / tree nut
/ egg, diets vegetarian / vegan, all-in budget, per-person coverage, conflict explanation,
card UI with swap-a-dish.
Out: Korean menus, placing or paying for orders, personalization from history, nutrition
claims, live scraping of Google Maps or delivery platforms.

## Current workspace additions (2026-09-21)

`POST /api/plan` also accepts an optional reviewed `menu_override`, `dish_count_target`,
and `style_preference` (`balanced`, `lighter`, `favorites`). Menu overrides are request-local,
not written to the shared fixtures. `POST /api/menu/evaluate` evaluates candidate eligibility
for `{menu, diners}`. `POST /api/menu/parse` extracts English name/price rows from `{text}` or
`{image_base64}`; image OCR uses local Tesseract. Imported dishes are now labeled from
`data/knowledge/` (2026-10-02 in `docs/decisions.md`); unrecognized ones stay unknown.
All imports and edits require review before planning. No LLM credentials are required for
the current deterministic planner or grounded explanations. See README for operating limits.
