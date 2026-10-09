# Bad-case eval: planner-oracle

## Summary

| Metric | Value |
|---|---|
| Scenarios passed (safety + money) | **22/22** |
| Scenarios with a severe violation | 0 |
| Severe violations (diner x dish) | 0 |
| Unflagged possible risks | 0 |
| Over budget | 0 |
| Wrong arithmetic | 0 |
| False "no order works" | 0 |

## By trap type

Counts are diner x dish pairs; a pair counts under every trap type among its conflicts.

| Trap | Severe in plan | Unsafe allowed (menu) | Safe refused (menu) |
|---|---|---|---|
| explicit | 0 | 0 | 0 |
| hidden | 0 | 0 | 0 |
| name_inference | 0 | 0 | 0 |
| ambiguous | 0 | 0 | 0 |
| compound_sauce | 0 | 0 | 0 |
| false_alarm | 0 | 0 | 0 |
| negative_control | 0 | 0 | 0 |

## Scenarios

| Scenario | Category | Result | Expected | Pass | Usable | Severe | False coverage | Unflagged | Total / limit | Portions |
|---|---|---|---|---|---|---|---|---|---|---|
| B01 | budget | plan | any | ✅ | ✅ | 0 | 0 | 0 | 66.99 / 100.00 | ok |
| B02 | budget | plan | any | ✅ | ✅ | 0 | 0 | 0 | 46.75 / 52.05 | ok |
| B03 | budget | plan | any | ✅ | ✅ | 0 | 0 | 0 | 85.53 / 110.00 | ok |
| B04 | budget | plan | any | ✅ | ✅ | 0 | 0 | 0 | 97.32 / 360.00 | ok |
| B05 | budget | plan | any | ✅ | ✅ | 0 | 0 | 0 | 27.78 / 30.00 | ok |
| C01 | infeasible | conflict | conflict | ✅ | ✅ | 0 | 0 | 0 |  |  |
| C02 | infeasible | conflict | conflict | ✅ | ✅ | 0 | 0 | 0 |  |  |
| C03 | infeasible | plan | any | ✅ | ✅ | 0 | 0 | 0 | 79.67 / 120.00 | ok |
| H01 | hidden_ingredient | plan | any | ✅ | ✅ | 0 | 0 | 0 | 60.64 / 90.00 | ok |
| H02 | hidden_ingredient | plan | any | ✅ | ✅ | 0 | 0 | 0 | 78.40 / 120.00 | ok |
| H03 | hidden_ingredient | plan | any | ✅ | ✅ | 0 | 0 | 0 | 56.90 / 90.00 | ok |
| H04 | hidden_ingredient | plan | any | ✅ | ✅ | 0 | 0 | 0 | 66.99 / 120.00 | ok |
| H05 | hidden_ingredient | plan | any | ✅ | ✅ | 0 | 0 | 0 | 86.02 / 120.00 | ok |
| H06 | hidden_ingredient | plan | plan | ✅ | ✅ | 0 | 0 | 0 | 75.93 / 90.00 | ok |
| H07 | hidden_ingredient | plan | any | ✅ | ✅ | 0 | 0 | 0 | 73.33 / 120.00 | ok |
| H08 | hidden_ingredient | plan | any | ✅ | ✅ | 0 | 0 | 0 | 56.90 / 90.00 | ok |
| H09 | hidden_ingredient | plan | any | ✅ | ✅ | 0 | 0 | 0 | 94.78 / 210.00 | ok |
| H10 | hidden_ingredient | plan | any | ✅ | ✅ | 0 | 0 | 0 | 54.36 / 90.00 | ok |
| H11 | hidden_ingredient | plan | any | ✅ | ✅ | 0 | 0 | 0 | 131.57 / 180.00 | ok |
| L01 | lock_exclude | plan | any | ✅ | ✅ | 0 | 0 | 0 | 84.75 / 120.00 | ok |
| L02 | lock_exclude | conflict | conflict | ✅ | ✅ | 0 | 0 | 0 |  |  |
| L03 | lock_exclude | conflict | conflict | ✅ | ✅ | 0 | 0 | 0 |  |  |

## Label accuracy

Every dish x restriction (9 allergens, 4 diets) on both eval menus: does the label say
block / ask staff / clear, as the reference does? **missed** = reference blocks, label
clears (dangerous). **weakened** = reference blocks, label only asks. **unflagged** =
reference asks, label clears. **stricter** = label more cautious than the reference.

| Dishes | correct | missed | weakened | unflagged | stricter | accuracy |
|---|---|---|---|---|---|---|
| in knowledge base | 363 | 0 | 0 | 13 | 1 | 96% |
| not in knowledge base (holdout) | 78 | 0 | 0 | 0 | 0 | 100% |
| all | 441 | 0 | 0 | 13 | 1 | 97% |

## Details

**C01**
- detail: No order meets the current budget, portions, dietary coverage, and kept dishes. Review the options below, or change your kept dishes or menu.

**C02**
- detail: No order meets the current budget, portions, dietary coverage, and kept dishes. Review the options below, or change your kept dishes or menu.

**L02**
- detail: No order meets the current budget, portions, dietary coverage, and kept dishes. Review the options below, or change your kept dishes or menu.

**L03**
- detail: No order meets the current budget, portions, dietary coverage, and kept dishes. Review the options below, or change your kept dishes or menu.

