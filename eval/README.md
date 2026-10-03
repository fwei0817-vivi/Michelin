# Bad-case evaluation

Measures the four claims the product has to win on against a general chat assistant:
no broken restriction, exact all-in budget, consistent hidden-ingredient flags, and a
correct "no order works" answer. Separate from `tests/` because it is a scored benchmark,
not a pass/fail gate, and baselines may come from live models.

```bash
uv run python eval/run_eval.py                    # planner, labels from printed menu text
uv run python eval/run_eval.py --labels kb        # planner, labels from the knowledge base
uv run python eval/run_eval.py --labels oracle    # planner, labels from ground truth
uv run python eval/run_eval.py --answers eval/baselines/<file>.json   # score a baseline
```

On Windows with a non-UTF-8 locale, set `PYTHONUTF8=1` first. Reports land in `eval/results/`.

## Layout

- `menus/trap_menu.json`: fictional 23-dish menu of known traps. Each dish has what the menu
  prints and a separate `truth` block (components, what they hit, `definite`/`likely`/`possible`).
- `menus/sample_sichuan_truth.json`: truth for the repo's own `data/menus/sample_sichuan.json`.
- `scenarios/*.json`: one table per file: diners, budget, rates, locks/exclusions, optional
  `dish_subset`, `expect` (`plan` | `conflict` | `any`) and the trap being tested.
- `labels.py`: builds the menu the planner sees. `current` labels only what is printed (today's
  pipeline without a knowledge base); `kb` runs `src/michelin/parse/knowledge.py` on the
  printed name and description; `oracle` labels from truth (perfect extraction);
  `reference` keeps only `definite`/`likely` truth and decides whether a safe order exists.
- `truth.py`: scoring, shared by the planner and every baseline.

## Scoring

| Metric | Meaning |
|---|---|
| severe | a diner is said to be able to eat a dish with a `definite`/`likely` conflict |
| false coverage | under truth, a diner has fewer than `min_dishes_per_person` safe dishes |
| unflagged | a `possible` conflict is served with no staff question naming that dish |
| over budget | all-in total, recomputed with cents and half-up rounding, exceeds the limit |
| math error | the answer's stated total differs from the recomputed one by more than 1 cent |
| lock/exclude | a kept dish is missing or a removed dish appears |
| false "no order works" | the answer refuses the table, but the planner on `reference` labels finds an order that passes this scorer |
| unsafe allowed (menu) | from `/api/menu/evaluate`: any dish x diner allowed despite a `definite`/`likely` conflict, served or not |
| safe refused (menu) | a dish x diner refused although truth has no conflict at all |
| possible-only refused (menu) | refused when truth has only `possible` conflicts: a policy choice, reported not judged |

A scenario **passes** (safety and money) with no severe, false coverage, lock, budget or math
problem, and the expected outcome. It is **usable** unless it falsely says no order works.
Unflagged risks and menu-level counts are reported but do not fail a scenario. Counts are
distinct diner x dish pairs.

## Label accuracy

Independent of scenarios: for every dish on both eval menus and every restriction (9
allergens, 4 diets), compare what the label tells the planner (block / ask staff / clear)
with the reference. `missed` (reference blocks, label clears) is the dangerous case.

Results are split by whether the knowledge base recognizes the dish. Holdout dishes
(`"holdout": true` in `trap_menu.json`) are deliberately left out of
`data/knowledge/`; the runner stops if one leaks in. Because the knowledge base and the
reference labels come from the same reviewers, in-KB accuracy measures lookup and
matching; holdouts measure what happens on a dish the system has never seen.

## Trap types

Each truth component has one `trap`; each dish lists `traps` for dish-level cases.

| Trap | The risk is... | Example |
|---|---|---|
| explicit | readable from the printed name or description | shrimp in Salt and Pepper Shrimp |
| hidden | left off a printed list that looks complete | egg in Hot and Sour Soup |
| name_inference | only knowable from what the dish name means | pork in Ants Climbing a Tree |
| ambiguous | in some versions only (`possible`) | oyster sauce in Garlic Bok Choy |
| compound_sauce | inside a named sauce | dried shrimp in XO sauce |
| false_alarm | (dish) suggested by the name but absent | no fish in Fish-Fragrant Eggplant |
| negative_control | (dish) nothing restricted at all | Hot and Sour Shredded Potato |

Component traps were derived by rule (explicit if every hit matches the printed text,
`possible` is ambiguous, soy sauce is hidden, then sauce/name/hidden by dish) and can be
edited by hand.

Truth labels describe typical NYC recipes and were reviewed by a person on 2026-10-02. Any
change to a `certainty` changes what counts as a violation, so re-review edits the same way.
