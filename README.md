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
If unavailable, text import and manual entry still work. Imported dishes retain unknown
dietary flags and require explicit review before use. No external AI calls are made.

Additional API fields on `POST /api/plan`: `menu_override`, `dish_count_target` (1–20),
and `style_preference` (`balanced`, `lighter`, `favorites`).
`POST /api/menu/evaluate` takes `{menu, diners}` and returns per-dish eligibility and questions.
`POST /api/menu/parse` takes `{text}` or `{image_base64}` and returns extracted text and dishes.

## Backend history and validation (2026-09-30)

Profile history is an opt-in local prototype. Set `MICHELIN_PROFILE_DB` to a writable SQLite
path (default `data/local/profiles.sqlite3`, git-ignored). No service or credentials are needed.
Send `X-Profile-Scope: synthetic-group-a` consistently for stored profiles and planning:

- `POST /api/profiles`: a `DinerProfile`; creates revision 1, duplicate ID gives 409.
- `GET /api/profiles`: current profiles in that scope; without a scope returns existing samples.
- `GET /api/profiles/{id}` and `GET /api/profiles/{id}/history`: latest/all snapshots.
- `PUT /api/profiles/{id}`: `{profile: DinerProfile, expected_revision: 1}` replaces the
  full profile and appends a revision; stale revisions give 409. Keep stable person IDs.
- `DELETE /api/profiles/{id}`: erases that person's current profile and complete history.

All person routes require a scope. Scoped lookups never fall back to another scope or the
sample group. The header is a namespace, **not authentication**: use only synthetic data in
this prototype until a trusted identity/access-control layer binds scopes to callers.
Likes/dislikes/spice preferences remain separate from allergies/diets. Planning with saved
`diner_ids` uses the latest snapshot. An inline profile controls current restrictions and
explicit preference values; omitted soft fields inherit saved preferences in that scope.
An inline empty list clears that preference for the request. Nothing is saved automatically.

`POST /api/order/validate` accepts `{menu: Menu, request: TableRequest, items: PlanItem[]}`
and returns `valid`, structured `reasons[{code, detail}]`, recomputed `totals`, per-dish
`evaluations`, staff questions, and assumptions. Send the **entire current order and inputs**
after swaps or edits. The planner also uses this check before returning an order.
`/api/menu/evaluate` additionally returns per-person `assessments` with status `conflict`,
`requires_confirmation`, or `validated_under_known_data`. Unknown evidence never counts
as validated allergy coverage. `Dish.reviewed_allergens` records explicit evidence review,
not an allergy-safety guarantee; present/unknown allergen flags still take precedence.
`Conflict.code` distinguishes `missing_information`, `no_solution`, and
`order_validation_failed`. Existing response keys and numeric money fields are preserved.

USD prices/budgets must be finite nonnegative/positive amounts with at most two decimals
(and at most one billion dollars). Tax and tip round separately using ROUND_HALF_UP; tip is
on the pre-tax subtotal. The exact all-in budget cannot be exceeded, even by one cent.
Defaults are assumptions, not restaurant fee evidence. Confirm extra charges and serving
sizes; portions are only estimates. Public-menu fixtures are offline tests, not new selectable
production menus. Mock orders can now return a conflict when independent validation fails.

SQLite survives process restarts only while that database file is retained. Container
replacement is **not** durable by default; persisting history across containers requires an
explicit persistent volume at `MICHELIN_PROFILE_DB`. No such volume or production service
has been provisioned. Test histories use temporary databases and no real diner data.
