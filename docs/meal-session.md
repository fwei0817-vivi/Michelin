# Current meal workflow (offline)

Start with an empty table. Import a prepared menu response, review it, add named
people, enter restrictions for this meal and an exact total meal budget, then
recommend. Editing a person or removing them after a recommendation regenerates
the entire order. Budget, group preset and menu changes invalidate the displayed
result until updated; invalid results cannot become order tickets. Swaps pin the
replacement and exclude the old dish before full replanning/validation; Undo
restores the previous dish constraints and replans. Restrictions never relax silently.
The UI supports 1–6 people; the project target remains shared meals for 3–6.

## Current meal versus remembered people

New people receive random stable IDs independent of display names. Same names do
not merge identities. “Use for this meal” changes browser session state only.
“Save for future meals” explicitly writes a complete profile snapshot/revision.
Loading saved preferences matches IDs, keeps existing people's current allergies,
diets and names, replaces only likes/dislikes/spice, and adds saved people absent
from the table. It never removes other current participants. Loading over six
people is rejected atomically. For a new meal, start empty and load saved people.
A save conflict requires loading/viewing the current revision before intentional
replacement. No natural-language interpretation or conversation memory exists.

Browser meal/menu/plan state resets on page reload. Explicit profile snapshots
survive a server restart when `MICHELIN_PROFILE_DB` points to the same retained
SQLite file. The default local file is ignored by Git. Ephemeral workspace deletion
can erase it. `X-Profile-Scope` is a caller-provided namespace, NOT authentication
or a secure tenant boundary. Use synthetic people; production access control,
backups and retained volumes are separate future work.

## Shared validated action boundary for a future chat adapter

`POST /api/meal/people` accepts `{diners, action, ...}`:

- `add` / `update`: `person` is a complete DinerProfile. Add requires a new ID;
  update requires an existing ID.
- `remove`: `person_id` must already exist.
- `load_preferences`: `saved` contains explicitly fetched profile snapshots.

The response is `{diners, recommendation_invalidated: true}`; invalid or ambiguous
actions return 422 without partial changes or profile writes. Empty tables are
allowed during setup; recommendation still requires at least one participant.
This is stateless validation, not a server session store. A future chat adapter
must propose these typed actions and send them through validation. It must not
write profile history implicitly or manufacture IDs based on names.
Budget/menu changes use the existing full `/api/plan` request. Swaps use its
`locked_dish_ids`/`excluded_dish_ids`; `/api/order/validate` independently validates
an explicit whole order. Persistent saves remain the existing scoped profile CRUD.

`budget_total` is additive in PlanRequest/TableRequest, exact USD cents and
positive. When supplied it overrides `budget_per_person * diner_count`; the
legacy required `budget_per_person` field is retained for old callers. The new
UI sends both, with total authoritative. Adding people does not increase the
budget. Tax/tip follow the selected rates with separate cent rounding; unlisted
fees remain unknown. Budget relaxation suggestions retain the legacy per-person
format; the UI converts them to a total before the user explicitly applies them.

## Evidence consistency and estimates

Explicit/inferred meat and incompatible allergen evidence overrides positive
vegetarian/vegan labels. A small ingredient vocabulary catches contradictions
such as minced pork, shrimp or sesame paste even if separate flags omit them.
It is not an exhaustive ingredient parser; unrecognized words do not establish
absence. Unknown or substitution claims prompt confirmation. Evidence review
never erases contradictory or unknown flags.

Missing `spice_level` and `portion` now serialize as null, rather than silently
becoming zero/medium. Existing explicit numeric/class values remain accepted;
consumers must handle null. Menu editing, scoring and UI handle both. Unknown
non-staple portions use an explicitly disclosed 1-unit search estimate, while
unknown heat gets a staff question and no invented heat score. Neither estimated
coverage nor portion units prove individual serving allocation or allergy safety.

## Verification

`uv run pytest` and `uv run ruff check src tests scripts`; frontend
`npm --prefix web run lint` and `npm --prefix web run build`.
`uv run python scripts/evaluate_offline.py` writes an offline regression report.
With local Chromium/Playwright installed, `python scripts/browser_offline_qa.py`
starts a loopback-only server with a temporary database, blocks external requests,
and checks import/review, cancel/back, explicit history, meal-only edits, adding
and removing a diner after recommendation, repeated swaps, current restrictions
over saved history, budget failure, Undo and actual server restart. Screenshots
and JSON results go to `/tmp`, never the repository.

Live model/OCR accuracy and production deployment are NOT tested or enabled.
