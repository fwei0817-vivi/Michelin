# Design decisions

Recorded after the Week 3 proposal review. Each entry: decision, why, what it changes.

## 1. Menus are pre-parsed, not photographed at the table

Menu photos are collected by hand from public listings (Google Maps, Yelp, restaurant sites)
and parsed offline. The demo flow is "pick restaurant → pick diners → budget → plan". Photo
upload stays as a fallback path.

Why: Google Maps has no menu API and scraping violates its terms. Offline parsing also removes
the 20-second vision wait from the demo and lets a human verify every menu before use.

## 2. Ingredients are an output of the system, not an input

Authentic Chinese menus usually print only a dish name and price. Americanized menus add a
one-line English description. Ingredient and allergen fields are therefore produced by the
LLM and tagged with an evidence tier:

| Tier | Source | UI wording |
|---|---|---|
| `menu` | printed on the menu | "contains peanuts" |
| `inferred` | typical recipe for that dish name | "usually contains pork" |
| `unknown` | sauces, broths, frying oil | "ask staff about the sauce" |

Why: dish names hide ingredients (鱼香肉丝 has no fish, 蚂蚁上树 has pork, many "vegetable"
dishes use oyster sauce). A binary contains / does-not-contain flag would be wrong often
enough to be dangerous. The tier drives both the optimizer (only `menu` and `inferred` block a
dish) and the "confirm with staff" list.

## 3. Hard constraints vs soft preferences

Allergies and diets are hard. Spice tolerance, dislikes and likes are soft and only affect
ranking. Each diner has a saved profile so the orderer adds people to the table rather than
re-typing restrictions.

## 4. Coverage is per person

Every diner must be able to eat at least `min_dishes_per_person` (default 2) non-staple
dishes. A single vegetable dish on a table of six does not satisfy a vegetarian guest.

## 5. Budget includes tax and tip

NYC defaults: 8.875% sales tax, 18% tip. A $25 per-person budget leaves roughly $19.70 of
menu price per person. The optimizer works against the menu-price cap derived from this.

## 6. Portions use a unit heuristic

Rule of thumb for family-style Chinese dining: N people order about N dishes plus rice. Each
dish gets portion units by class (typical stir-fry = 1.0, large dry pot or whole fish = 1.5,
cold appetizer = 0.6, shared soup = 0.8, individual bowl = 0.35). The plan must land between
0.9·N and 1.3·N units. The numbers are a starting point to be tuned against real orders.

## 7. Deterministic optimizer, LLM only for understanding and explaining

OR-Tools CP-SAT selects dishes. The LLM parses menus and writes one-line reasons. Constraint
satisfaction must be reproducible and explainable; an LLM choosing dishes is neither.

## 8. Infeasibility is diagnosed, not hidden

When no order satisfies every hard constraint, the system re-solves with one constraint
relaxed at a time and reports the options: "raise the budget to $28 per person" or "drop the
vegetarian constraint for Amy". This is the core difference from asking a chatbot to order.

## 9. Variety score replaces "nutritional balance"

Menus carry no nutrition data. The score rewards distinct categories, proteins and cooking
methods and penalizes an all-fried table.

## 10. Success criteria

- Hard-constraint satisfaction on all test scenarios: 100%.
- Allergen recall against hand labels: the primary parsing metric. Precision is secondary.
- Testers accept a plan after fewer than two dish swaps on average.
- Total lands within 5% under the all-in budget.

## 11. Scope

v1: Chinese menus only, three verified restaurants. The persona is updated to a Chinese
restaurant with a user who does not read Chinese, so the parsing step has clear value.
Korean menus, ordering, payment and personalization are out of scope.

## 12. Frontend is React + Vite, and the plan is drawn as an order slip

The first frontend was plain HTML. It is now a Vite + React + Tailwind app in `web/`, built
from the AI Studio prototype's feature set (edit the party, keep / swap / remove dishes, a
screen to show the waiter, copy-for-the-group-chat) but redrawn: the plan is rendered as the
restaurant's paper order slip on a jade page, Chinese dish names lead, evidence tiers are
written as words ("peanuts, on the menu", "pork, usually", "shellfish? ask") and vermilion is
reserved for a real allergy match, the stamp and the one primary button.

Why: the prototype's client-side rule engine and Gemini server duplicated the backend and the
LLM stage, against the division of trust. The frontend now only renders what `/api/plan`
returns. The prototype's engine was not merged; the backend owner may read it for heuristics.

## 13. The plan request carries inline diners and kept / removed dishes

`/api/plan` accepts `diners` (edited or ad-hoc people, sent inline) next to `diner_ids`, plus
`locked_dish_ids` and `excluded_dish_ids`. `TableRequest` carries the last two to the
optimizer.

Why: at the table people change their minds ("actually I'm vegan tonight") and the orderer
swaps dishes one at a time. Both are cheap to express as constraints and keep the frontend
free of any selection logic.

## 2026-09-21 — English recommendation workspace

- Make the recommended courses the primary workspace; move party settings into a drawer and reserve the paper ticket for the final order. Keep jade, cream, and red as the shared visual language.
- Show all interface text and dish labels in English, including the waiter ticket.
- Keep completed plans paired with the exact menu, diners, and settings that produced them. Changes invalidate order actions until a new request succeeds; late responses cannot replace newer choices.
- Keep eligibility on the API, including menu browsing and swap filtering. Course counts and dining styles are ranking preferences; individual coverage, budget, and portions remain requirements.
- Use a bounded, dependency-free search for small menus (up to 40 dishes). It returns a constraint-valid order or a proven conflict; an exhausted search with no valid incumbent returns a retryable error, never a false infeasibility claim. Do not claim global optimality.
- Generate explanations from actual selected dishes and diner eligibility. Variety is not a satisfaction or nutrition score.
- Menu imports extract explicit English names and prices, using optional local Tesseract for images. Never invent ingredients, prices, or dietary flags. Edits stay in the browser session and require human review before planning; no external AI service receives menu images.
- Dish cards may show an illustrative Wikimedia Commons photo of a similar dish, labelled as such and credited. Photos are decoration, never evidence: ingredient and allergen claims come only from the reviewed menu and its evidence tiers.
- Kitchen questions are shown twice on the plan page, inline under the dish they concern and as one list below the dishes, never as a banner above them. The order panel is the one dark block on the page so the bill reads as separate from the dishes.

## 2026-09-30 — Persistent explicit preferences and independent validation

This user-authorized backend extension supersedes the proposal's exclusion of history.
Store explicit profile snapshots in local SQLite by `(scope, person_id, revision)`; never
infer allergies, diets, or tastes from an order. Full profile updates append history with
optimistic revision checks. DELETE erases all revisions for that person in that scope.
Saved likes/dislikes/spice preferences inform ranking; current inline values (including
empty lists) win. Inline hard restrictions remain authoritative as in the existing API.
Planning never writes profiles. Scope keys isolate local prototype groups, not authenticated
accounts; a real deployment needs trusted identity binding and access control first.

Unknown or absent allergen evidence now excludes that diner from coverage. This supersedes
section 2's old unknown-tier behavior. `reviewed_allergens` is an explicit review of available
evidence for named allergens, not proof of absence or a cross-contact guarantee. Recorded
or inferred presence and unknown flags always override this review. Existing sample menus
are deliberately not relabeled as reviewed; requests involving allergies may now return
`missing_information`. Public menu V badges establish vegetarian only, not vegan.

The new order validator recomputes quantities, cents, eligibility, coverage, pins/exclusions
and portion estimates from current inputs. Every API-generated order, including mock output,
passes this independent check. Explanations may change reasons only. Coverage counts distinct
dishes, not quantity; price and estimated portion units multiply by quantity. This is still
per-diner coverage, not a claim that all dishes suit all people or that shared-table
cross-contact is safe. Conflicts with unresolved evidence are conservatively reported as
`missing_information`, not proof that the restaurant cannot accommodate the group.

Budget is strict (no 5% overshoot): USD cents, decimal ROUND_HALF_UP, tax and pre-tax tip
rounded separately. Cap search uses those same rounded rules. Missing prices never mean
zero. Defaults remain the existing configurable 8.875% tax and 18% tip assumptions, not
verified restaurant charges. Unlisted fees are not included. No exact serving adequacy is
claimed; retain the existing portion heuristic and bounded search.

Public evidence: small regular-menu extracts from Café China and CHILI, observed 2026-09-30,
live in `tests/fixtures/public_menus.json` with official URLs and meal context. Synthetic
mutations are explicit in tests. Do not substitute weekday lunch prices, infer missing piece
counts, or infer ingredient omission is possible. Piece-target optimization, meal-time offer
validation, accommodation requests and fee schedules (including outside-cake caps) remain
out of scope; callers must supply a reviewed menu for the actual context and confirm fees.
No live model extraction or OCR was run; model boundaries are exercised with mocked failures.

## 2026-09-30 — Assistant-prepared model adapter

User explicitly requested authored model replies now, with a replaceable genuine provider
later, without live model spending. Add an exact-input replay adapter at the extraction
boundary rather than a separate fixture-only application. Menu identity, input kind and hash
must match; missing responses fail honestly. All output still requires explicit review and
independent planning validation. No fake recommendation model: selection/explanation already
work deterministically. Provenance is retained in Menu and visible in the existing import and
plan views. Minimal UI integration also exposes explicit synthetic profile history and
three-state diner assessments. See `offline-replay.md` for reproducible tests and exclusions.
