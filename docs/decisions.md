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

## 2026-10-02 — Hidden-ingredient knowledge base labels imported dishes

Supersedes the "never invent ingredients or dietary flags" part of the 2026-09-21 import rule;
prices and names are still never invented.

- `data/knowledge/hidden_ingredients.json` holds reviewed typical-recipe components per dish
  (definite / likely / possible) and per named sauce. `parse/knowledge.py` turns the printed
  text plus that file into labels: printed → `menu`, definite/likely → `inferred`,
  possible → `unknown` with a staff question. Same text, same labels, every time.
- A dish the knowledge base does not recognize is never certified: diet flags stay `null`
  and every allergen is `unknown`, with a "not a dish we recognize" staff question.
- `/api/menu/parse` returns these labels; `python -m michelin.parse.label_menu` does the same
  for a whole menu file. Output is always unverified and still needs human review.
- An LLM may later map unusual dish names to a knowledge-base entry. It never writes
  ingredients or flags itself.

Why: the bad-case evaluation (`eval/`) showed every severe violation came from labels built
from printed text alone (hidden egg, minced pork, peanuts, sauces); the planner's rules were
already correct given correct labels. With knowledge-base labels severe violations went from
14 to 0 on the trap scenarios, while unrecognized holdout dishes fell back to "ask staff".

`possible` components: allergies are strict, diets ask. An allergen that is only possible is
labeled `unknown`; the `backend-integrated` planner does not count the dish for that diner. The
planner on `main` still counts `unknown` allergens as eligible (with a staff question), so
strict allergies need that backend fix merged. For vegetarian, vegan, no-pork and
no-beef diners the dish stays eligible and the staff question names the component (chicken
powder, oyster sauce, minced pork). Meat of an unspecified kind that is definite or likely
still blocks no-pork and no-beef, since it may be either.
Why: refusing every `possible` dish made four evaluated tables report "no order works" while
a safe order existed (including the sample group). A diet is confirmed by asking staff, the
same question for a vegetarian or a no-pork diner; an allergy is medical, so a question is not
enough. An earlier version kept no-pork and no-beef strict while letting vegetarians ask, which
treated the same uncertain minced meat differently for two diners. Effect on the evaluation:
false refusals 4 -> 1 (the remaining one involves dishes the knowledge base does not know),
severe violations still 0.

## 2026-10-02 — An LLM maps unusual dish names to the knowledge base

`parse/matcher.py` sends dish names the knowledge base does not match exactly (names and
printed descriptions only, never images) to an LLM, which may only answer with a
knowledge-base id or "none". Default: `gemini-2.5-pro` on the course's Vertex AI project with
gcloud ADC (the organization disallows API keys). `MICHELIN_LLM_PROVIDER` selects another
provider (`claude-vertex`, `claude`) behind the same prompt. Temperature 0. The answer is stored in `data/knowledge/llm_matches.json`
and reused for the same text, so labels stay deterministic and reviewable. Until a person
accepts a match (`"reviewed": true`), the dish gets a staff question to confirm it is the same
dish; printed evidence applies either way. Calls happen only with `MICHELIN_LLM_MATCH=1` (or `label_menu --llm`) and credentials;
without them the app behaves as before.
Why: exact names miss common spellings ("Spicy Tofu w/ Ground Pork"); letting the model pick
from a closed list keeps it out of ingredient claims. `eval/matcher_eval.py` measures accuracy
and run-to-run agreement before answers are stored: on 27 name variants, 5 runs, Gemini
answered 96% correctly and gave the same answer on every run for all 27. Its one miss maps
"Shrimp Lo Mein" to the generic lo_mein entry instead of "none"; printed shrimp still blocks
shellfish allergies.

## 2026-10-02 — Three real restaurants: Atlas Kitchen, Café China, CHILI

Up to 40 dishes each from the regular dinner menu on each restaurant's own site (lunch and
happy-hour prices excluded), with provenance in `data/raw/<slug>_source.json` (URL, date,
names, prices, printed descriptions and tags as listed). Atlas Kitchen is near campus and
mid-priced; Café China and CHILI are Midtown and pricier, which exercises budget conflicts.
Labels come from `label_menu --llm` plus the review answers described below. Finding from that
review: Café China and CHILI both print Ma Po Tofu as vegetarian, while the knowledge base
expects minced meat; neither side is overridden silently. Meat is treated as `possible`, so vegetarian,
no-pork and no-beef diners may order it after the staff question.

### Labels for the three restaurants: how they were made (2026-10-02)

The three menus are marked `verified: true` for the classroom prototype, on the LLM owner's
decision. What that means, so nobody over-claims it:

- Names and prices: copied from each restaurant's own menu page (`data/raw/`).
- Ingredient labels: knowledge-base entries for recognized dishes; for the 35 dishes it did not
  recognize, plus three corrections (Shanghai spring rolls are not vegetable spring rolls; the
  two Ma Po Tofu dishes the restaurants print as vegetarian), typical-recipe assessments drafted
  by Claude and accepted by the team, recorded in `data/menus/review_answers.xlsx` and imported
  with `parse/review_workbook.py`. LLM name matches were accepted after review.
- Not done: no restaurant was asked. Everything that is only "possible" stays a staff question,
  and labels keep the `inferred` / `unknown` tiers; nothing is presented as printed fact.

Re-labeling: `label_menu` (stored LLM answers) followed by `review_workbook import` on the
answers file reproduces the menus; setting `verified` stays a deliberate manual step.

### Knowledge-base review status (2026-10-02)

All 58 dishes and 10 sauces in `data/knowledge/hidden_ingredients.json` were drafted with Claude
from typical NYC recipes, exported to a review sheet (one dropdown per restriction), skimmed by
the LLM owner and accepted as a whole with no changes. That is a sanity check, not an
entry-by-entry verification: present it as "AI-drafted, team-reviewed typical recipes", and
keep `possible` components as staff questions.

**2026-10-09: free Gemini Developer API by default.** Menu photo reading and the name matcher
now default to `gemini-3.8-flash` on the free Gemini Developer API (`GEMINI_API_KEY` from AI
Studio) instead of `gemini-2.5-pro` on Vertex AI, which needs billing. Vertex stays available
with `MICHELIN_GEMINI_BACKEND=vertex`. Earlier stored matches keep their recorded model. A 429
pauses calls and falls back to the non-LLM path (OCR or pasted text; knowledge base only).

**2026-10-09: the LLM recommends; the rules only validate.** `/api/plan` asks the LLM
(OpenRouter `google/gemini-2.5-flash` when `OPENROUTER_API_KEY` is set, else the free Gemini
key) for the order, using a brief with per-diner eligibility already computed. Each order
goes through `validate_order` plus a per-diner safety check. Violations go back to the model
for up to 3 retries. There is no optimizer fallback. If no model answers, or no order
passes, the response is an explained conflict (`ai_unavailable` or `ai_no_valid_order`).
The model's own "no fit" answer carries its suggested budget or coverage change, which is
range-checked before it is shown.

**2026-10-09: no portion math; the LLM decides how many dishes.** Portion units, dish-count
targets, the "dishes each person can eat" setting and the old optimizer/relaxation code are
removed. The prompt suggests roughly one dish per person plus rice; the validator does not
check counts. Hard checks stay deterministic: allergies and diets, budget with tax and tip,
dish ids on the menu, kept/removed dishes, quantity limits, and every diner can eat at least one
chosen non-staple dish. `plan/hints.py` computes the cheapest valid order (branch and bound);
the brief says whether an order fits and names a diner's only option, retries repeat that, and
when nothing fits the conflict always offers "Raise the budget to $X per person", where X is
the lowest budget with a valid order (or the model's own figure if it validates). Every dish
count in the UI is `plan.items.length`; the model's one-line summary explains the count.

**2026-10-09: wording moved to the planner's single LLM call.** The model now writes one server
question per chosen dish (who and why) and the plan summary. Rule-detected risks are sent as
facts; any risk the model's question does not cover gets the rule question appended, merged into
one line per dish. Safety labels, budget arithmetic, conflict titles and the budget figure stay
deterministic. Menu photos and the name matcher use OpenRouter whenever `OPENROUTER_API_KEY` is
set (`MICHELIN_OPENROUTER_VISION_MODEL` overrides the photo model); the free Gemini key is the
fallback.

**2026-10-09: swaps change one dish only.** "AI swap" asks the planner's model once (one retry)
for a replacement; picking from the menu makes no model call. Both keep every other dish exactly
as it is and run the whole order through the plan checks; a pick that breaks the budget or
someone's diet is refused with the reason instead of rebalancing the table. Undo restores the
previous plan. Why: users asked to change one dish without the rest of the table moving.

**2026-10-09: adds are single-dish too; plainer server questions; honest progress.** Adding a
dish no longer re-plans the table: it is checked like a swap and refused with the reason if it
breaks a rule. Server questions are one plain sentence; rule fallbacks use the same style and
menu notes nobody at the table cares about are dropped. The planner cache key now includes the
prompt. While the AI works the UI lists the real stages on a timer with elapsed seconds, never
a percentage, because the server does not stream progress.

**2026-10-09: QA round 3 fixes.** Server questions (plan and swap) only ask about diners who can
eat the dish and about concerns the rules flag on it: a model question that names a "Not for"
diner, a diner the dish flags nothing for, or an allergen/diet nobody's risk involves is dropped
for the rule question. Raw ids ("no_pork") are humanised everywhere the model or user sees them.
The AI swap reason is one short clause that may only name diners who can eat the new dish;
otherwise the rule line is used. If the model's swap covers fewer diners than a similar-priced
valid alternative, it is asked once more and the better-covering valid pick wins. When the AI's
budget figure is more than 1.25x the rules minimum, the conflict offers the minimum first and the
AI figure as "a fuller meal". The menu sheet disables picks that would break the budget, with
the amount, and gives one plain reason per diner ("Ben: has pork"). After a swap the summary
stays (rewritten by the rules if it named the swapped dish), and the choices bar says which
dishes are kept or won't be suggested again.
