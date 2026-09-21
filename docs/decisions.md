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
