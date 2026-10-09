# Michelin — a smarter way to order for the table

IEOR E4577 course project. Given a parsed restaurant menu, the diners' saved profiles and a
total meal budget (legacy API per-person budgets remain supported), the app proposes an
order using recorded restriction evidence and exact money arithmetic. The AI decides how
many dishes (roughly one per person plus rice); there is no portion math. Unknown ingredients
require confirmation. If no validated order is found, it explains conflicts or missing evidence.

See [the current meal workflow](docs/meal-session.md) for adding people, temporary meal
changes, explicit saved preferences, swaps and the future structured chat boundary.

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

### AI model (required for recommendations)

The LLM chooses the dishes. It also reads menu photos and, when you opt in, matches dish
names. Deterministic code checks every order it proposes: dish ids must be on the menu,
removed and kept dishes are respected, allergies and diets are applied per diner, the
budget includes tax and tip, quantities stay within any limits, and every diner can eat at
least one chosen dish (rice and noodles don't count). The number of dishes is not checked.
Each violation goes back to the model, with up to 3 retries. There is no rules-planner
fallback. If no model answers, or no proposed order passes the checks, the app says so.
When the budget is too low, the model proposes the "Change one thing" fix.

The app uses the first provider that is configured:

1. **OpenRouter** (paid, OpenAI-compatible): set `OPENROUTER_API_KEY`. The default model is
   `google/gemini-3.5-flash-lite` (about $0.30 per million input tokens and $2.50 per million
   output tokens, reasoning effort "low"; a plan costs well under a cent). 2.5 Flash is
   retired on OpenRouter on 2026-10-20.
2. **Gemini Developer API** (free tier): create a key at <https://aistudio.google.com/apikey>
   and set `GEMINI_API_KEY`. The default model is `gemini-3.8-flash`.

Keep keys in your shell or in a git-ignored `.env`, and never commit them:

```bash
export OPENROUTER_API_KEY=...        # or: export GEMINI_API_KEY=...
uv sync --extra dev --extra llm      # installs google-genai
cd web && npm run build && cd ..
uv run --extra llm uvicorn michelin.api:app
MICHELIN_LLM_MATCH=1 uv run --extra llm uvicorn michelin.api:app   # also LLM name matching
```

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | unset | use OpenRouter (preferred when set) |
| `MICHELIN_OPENROUTER_MODEL` | `google/gemini-3.5-flash-lite` | OpenRouter model for every task |
| `MICHELIN_OPENROUTER_REASONING` | `low` | reasoning effort sent to OpenRouter (`minimal`, `low`, `medium`, `high`; empty sends none) |
| `MICHELIN_OPENROUTER_VISION_MODEL` | unset | OpenRouter model for menu photos only (must accept images) |
| `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) | unset | use the free Gemini API |
| `MICHELIN_LLM_PROVIDER` | auto | force `openrouter` or `gemini` |
| `MICHELIN_GEMINI_MODEL` | `gemini-3.8-flash` | Gemini model for every task |
| `MICHELIN_VISION_MODEL`, `MICHELIN_LLM_MODEL`, `MICHELIN_PLANNER_MODEL` | unset | Gemini per-task overrides |
| `MICHELIN_GEMINI_FALLBACK_MODEL` | `gemini-2.5-flash` | tried once when Gemini is overloaded (503); empty disables |
| `MICHELIN_GEMINI_BACKEND=vertex` | unset | Gemini on Vertex AI (billing, `gcloud auth application-default login`) |
| `MICHELIN_VISION=off` | unset | never send photos to a model |

The free Gemini tier is small: for Gemini 3.8 Flash, about 5 requests a minute and 20 a day.
On a 429, or when OpenRouter credit runs out (402), the app says so. It pauses Gemini calls
for a minute, or for an hour once the daily quota is gone. Photos fall back to local OCR if
`tesseract` is installed, and otherwise to pasting the menu text. Without a model, dish facts
stay unknown (nobody with a restriction can eat an unknown dish). The planner returns an explained "No recommendation
right now". Identical plan requests are cached in `data/local/llm_plans.json`, which is
git-ignored. The models transcribe menus, infer each dish's likely ingredients and allergen
risks from its name (cached per dish name in `data/facts/dish_facts.json`), and choose dishes
from the brief; the rules enforce every diner's allergies and diets on top.

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

Recommendations come from the AI model (see above), and the rules enforce the budget
(including tax and tip), kept and excluded dishes, and diner coverage. The old rules optimizer
and portion estimates were removed (2026-10-09). `plan/hints.py` finds the cheapest valid
order deterministically; it tells the model whether any order fits, and when none does it sets
the "Raise the budget to $X per person" fix (X = the lowest budget at which an order exists).
The model writes one server question per chosen dish, naming who it is for and why; rule-based
risks are passed in as facts and any risk the model skips is added back from the rules. The API accepts up to 150 reviewed dishes (a choice of protein counts once per choice; a menu can have up to 8 pages).
Several photos of one menu are read together in one vision call (one call per page if they are very large), and a dish printed twice is listed once. A PDF menu is rendered to page images on the server with `pdftoppm` (poppler-utils, included in the Dockerfile); without it, upload photos of the pages instead.
Set `MICHELIN_MOCK=1` only for fixture-based demos.

Menu editing and imports are session-local. Paste one English dish per line with its price
at the end, or upload an English PNG/JPEG/WebP menu image (up to 8 MB). Image extraction
uses OpenRouter when `OPENROUTER_API_KEY` is set (the photo goes as a base64 `image_url`; default
`google/gemini-3.5-flash-lite`, override with `MICHELIN_OPENROUTER_VISION_MODEL`; `/api/health` then
reports `photo: "openrouter"`), else Gemini when `GEMINI_API_KEY` is set (see above); otherwise it requires the `tesseract` executable with English language data (included in the Dockerfile).
If unavailable, text import and manual entry still work.

**Menus are only name, price and category.** Every other dish field is ignored at runtime:
`plan/dish_facts.py` asks the planner's model once per menu what each dish is usually made
of (likely and possible ingredients, the nine allergens, pork/beef, vegetarian/vegan, heat),
caches the answer by dish name in `data/facts/dish_facts.json` (shipped for the bundled
menus), and the rules enforce diners against it: a likely or possible allergen keeps an
allergic diner off the dish; a "possible" diet risk (e.g. lard in a pancake) keeps the dish
with a question for the server; anything unanswered stays unknown and excluded. Imported
menus still require explicit review before use. The bad-case evaluation lives in
`eval/` (see `eval/README.md`).

**Swapping one dish.** Each recommended dish has "AI swap" (one model call, same provider and
model as the planner) and a menu-pick button. Either way only that dish changes; every other
dish, quantity and reason stays. `POST /api/plan/swap` takes the plan request fields plus the
current `plan` and `dish_id`; add `new_dish_id` for the user's own pick (no model call). The
whole new order goes through the same hard checks as a plan (menu, not already ordered, not
removed, allergies and diets, budget with tax and tip, everyone still has a dish). A failing AI
answer is retried once with the reason; a failing pick is refused with the reason. The UI shows
"Swapped to X, …, $3.00 cheaper" (the price part is computed) and Undo restores the previous
plan without a model call. "Something else in mind?" adds just that dish the same way (send
`new_dish_id` without `dish_id`); a dish that breaks a rule is refused with the reason.

Server questions are one plain sentence per dish ("Is there any pork or lard in the scallion
pancake, for David (vegetarian) and Tom (no pork)?"). Dish-level menu notes only become
questions when they matter to someone at the table (a soy note is skipped if nobody avoids soy).

Additional API fields on `POST /api/plan`: `menu_override` and `style_preference` (`balanced`, `lighter`, `favorites`).
`POST /api/menu/evaluate` takes `{menu, diners}` and returns per-dish eligibility and questions.
`POST /api/menu/parse` takes `{text}` or `{image_base64}` and returns extracted text and dishes.

## Backend history and validation (2026-09-30)

Profile history is an opt-in local prototype. Set `MICHELIN_PROFILE_DB` to a writable SQLite
path (default `data/local/profiles.sqlite3`, git-ignored). No service or credentials are needed.
Send `X-Profile-Scope: synthetic-group-a` consistently for stored profiles and planning:

- `POST /api/profiles`: a `DinerProfile`; creates revision 1, duplicate ID gives 409.
- `GET /api/profiles`: current profiles in that scope; without a scope returns existing samples.
- `GET /api/profiles/{id}` and `GET /api/profiles/{id}/history`: latest/all snapshots.
- `PUT /api/profiles/{id}`: `{profile: DinerProfile}` creates or replaces the person's
  current record (appends a revision). Add `expected_revision: n` for an optimistic check;
  a stale revision gives 409. Keep stable person IDs.
- `DELETE /api/profiles/{id}`: erases that person's current profile and complete history.

All person routes require a scope. Scoped lookups never fall back to another scope or the
sample group. The header is a namespace, **not authentication**: use only synthetic data in
this prototype until a trusted identity/access-control layer binds scopes to callers.
A person is allergies and diets (one-tap checkboxes, hard rules) plus one free-text
`notes` field for tastes ("no spicy food, loves tofu") that only the AI reads. Older saved
people with heat/likes/dislikes are migrated into `notes`. Planning with saved `diner_ids`
uses the latest snapshot. An inline profile controls current restrictions; an omitted
`notes` inherits the saved note in that scope, and an empty one clears it for the request.

The web app saves **everyone** you add: each add/edit is a `PUT /api/profiles/{id}` with no
`expected_revision` (upsert of the person's single current record), under the fixed scope
`household`. The Table step shows saved people as chips to pick tonight's diners (max six);
`DELETE` removes a person. Plans send tonight's diners inline. **There is no login**: anyone
who can reach the server sees and edits the same saved people, so use it for the demo only.

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
sizes with staff. Public-menu fixtures are offline tests, not new selectable
production menus. Mock orders can now return a conflict when independent validation fails.

SQLite survives process restarts only while that database file is retained. Container
replacement is **not** durable by default; persisting history across containers requires an
explicit persistent volume at `MICHELIN_PROFILE_DB`. No such volume or production service
has been provisioned. Test histories use temporary databases and no real diner data.

## Use prepared model responses now; replace the provider later

Menu import now offers **assistant-prepared responses** for Café China and CHILI. The server
replays the response only for its exact menu ID, input kind and SHA-256. Unknown inputs fail
honestly; no live model is called. The same `/api/menu/extract` contract is used by replaceable
provider adapters selected with `MICHELIN_EXTRACTION_PROVIDER` (default `replay`). A real
provider implementation is not installed yet; it can be added without changing the frontend
or rule engine. Genuine local text/OCR import remains a separate, labelled path.

See [offline replay instructions and evaluation](docs/offline-replay.md) for setup, response
registration, the contract, local profile history controls, browser QA, and measured limits.
