# Backend implementation and evaluation — 2026-09-30

Baseline: commit `82a3a78`; clean original checkout on `work`. Fetched fork `main` and
`codex/backend`, created isolated `/workspace/Michelin-backend` on `codex/backend`.
Upstream fetch returned HTTP 403; no additional access was requested. Original checkout,
main, frontend, LLM parsing/explanation modules and production sample data were not modified.
No PR, merge, deployment, external service, real diner data, or secrets were involved.

## Delivered

- Local SQLite full-profile snapshots by caller-supplied scope/person ID, append-only
  revisions, optimistic update conflicts, person history, and complete history deletion.
  Transactions prevent lost concurrent updates. Scoped calls never fall back to samples.
- Explicit likes/dislikes/spice history informs ranking; current inline restrictions and
  explicitly provided preferences win. No automatic order-history inference or writes.
- Three eligibility states; missing allergen review and unknown flags cannot count toward
  validated coverage. Public vegetarian labels are not upgraded to vegan.
- Decimal/cents arithmetic with strict budget, shared rounded-cap calculation, missing-price
  rejection, positive integer quantities, and whole-order server validation after swaps.
- Additive validation endpoint and reason codes. Planner/explanation malformed outputs fail
  closed; explanation output may only change item reasons. Mock orders are checked too.

Existing endpoint response shapes and numeric money types remain compatible. New fields and
routes are documented in README/CLAUDE. Intentional behavior changes: unknown-allergen sample
requests can return `missing_information`; invalid mock orders return conflicts; malformed
prices/quantities and duplicate inline IDs are rejected. Original tests expecting unsafe
unknown eligibility or unchecked mock plans were updated. Positive optimizer tests explicitly
use a synthetic evidence-review mutation, never a claim about restaurant ingredients.

## Evidence and offline scenarios

Official menu extracts supplied from direct page review on 2026-09-30:

- Café China: https://cafechina.nyc/menu
- CHILI: https://chilinyc.com/new-york-midtown-manhattan-chili-food-menu

The small factual fixture is `tests/fixtures/public_menus.json`; it preserves restaurant and
regular-menu context. Ingredient lists and cross-contact remain incomplete. Tests exercise:
Café China two pot-sticker orders + mapo + four rice = $51 subtotal; synthetic zero-fee
boundary versus $50.99; three four-piece pot-sticker orders = twelve pieces/$36; fish with
minced pork vs no-pork; chive pancake vs shellfish; vegetarian vs vegan uncertainty;
CHILI bok choy vs unknown sesame; CHILI regular mapo + two rice = $26. Missing price is an
explicit synthetic mutation. Café China's unknown scallion-piece count never inherits
CHILI's six-piece count. Public price tests do not claim real all-in restaurant quotes.

Separate synthetic menus test successful complete plans, swaps, quantities, restrictions,
current-over-history precedence, pins/exclusions, exact budget checks, and no-solution versus
missing-information responses. Profile tests cover create/read/update/delete/history,
scope and person identity, reopening storage, conflicting revisions and concurrent updates.
Mocked planner/explanation outputs test malformed payloads, altered totals, null responses,
exceptions and search timeout. No live model or image extraction was tested; the current
planner and explainer are deterministic, with no model credentials required.

## Validation

Commands used writable cache `UV_CACHE_DIR=/workspace/.cache/uv` because the default home
cache was read-only. The isolated worktree needed `uv sync --extra dev`; no dependencies or
lockfile were changed. Baseline `uv run pytest -q`: **39 passed**.
Final `uv run pytest -q`: **64 passed**, two existing Starlette/httpx/anyio deprecation warnings.
`uv run ruff check src tests`: **passed**. `git diff --check`: **passed**.
One pre-existing import-order lint issue in `tests/test_score.py` was corrected.

## Limits and review decisions

Scopes/person IDs are trusted caller-provided values, not authenticated access boundaries.
Use synthetic data only until a trusted identity/access-control layer is added. SQLite
survives restart while its file survives; cross-container durability needs an explicit volume.
Runtime DB directory is git-ignored; test databases live under temporary paths. No frontend
profile editor, production accounts, or hosting/storage services were implemented.

The original bounded search and portion heuristic remain. Coverage is per diner, not all
people eating every dish; cross-contact is not certified. `missing_information` is conservative
if any relevant menu assessment is uncertain; it is not a proof of restaurant infeasibility.
No allocation optimizer or people-fed guarantee. No piece-target optimization, meal-time
validation, ingredient-omission accommodation, extra-fee engine, or automatic price refresh.
In particular weekday lunch discounts and the outside-cake fee cap are documented evidence,
not implemented pricing rules. The caller must use the correct reviewed menu and confirm
fees. Existing tax/tip defaults are assumptions. Other owners should review additive contracts
and the stricter behavior before the user approves any upstream PR.
