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
| False "no order works" | 2 |
| Menu level: unsafe dishes allowed | 0 |
| Menu level: safe dishes refused | 0 |
| Menu level: possible-only dishes refused | 37 |

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
| B04 | budget | plan | any | ✅ | ✅ | 0 | 0 | 0 | 111.27 / 360.00 | ok |
| B05 | budget | plan | any | ✅ | ✅ | 0 | 0 | 0 | 27.78 / 30.00 | ok |
| C01 | infeasible | conflict | conflict | ✅ | ✅ | 0 | 0 | 0 |  |  |
| C02 | infeasible | conflict | conflict | ✅ | ✅ | 0 | 0 | 0 |  |  |
| C03 | infeasible | plan | any | ✅ | ✅ | 0 | 0 | 0 | 79.67 / 120.00 | ok |
| H01 | hidden_ingredient | plan | any | ✅ | ✅ | 0 | 0 | 0 | 60.64 / 90.00 | ok |
| H02 | hidden_ingredient | plan | any | ✅ | ✅ | 0 | 0 | 0 | 78.40 / 120.00 | ok |
| H03 | hidden_ingredient | plan | any | ✅ | ✅ | 0 | 0 | 0 | 56.90 / 90.00 | ok |
| H04 | hidden_ingredient | plan | any | ✅ | ✅ | 0 | 0 | 0 | 68.25 / 120.00 | ok |
| H05 | hidden_ingredient | plan | any | ✅ | ✅ | 0 | 0 | 0 | 86.02 / 120.00 | ok |
| H06 | hidden_ingredient | plan | plan | ✅ | ✅ | 0 | 0 | 0 | 75.93 / 90.00 | ok |
| H07 | hidden_ingredient | plan | any | ✅ | ✅ | 0 | 0 | 0 | 73.33 / 120.00 | ok |
| H08 | hidden_ingredient | plan | any | ✅ | ✅ | 0 | 0 | 0 | 56.90 / 90.00 | ok |
| H09 | hidden_ingredient | plan | any | ✅ | ✅ | 0 | 0 | 0 | 94.78 / 210.00 | ok |
| H10 | hidden_ingredient | conflict | any | ✅ | ❌ refused | 0 | 0 | 0 |  |  |
| H11 | hidden_ingredient | conflict | any | ✅ | ❌ refused | 0 | 0 | 0 |  |  |
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
| in knowledge base | 376 | 0 | 0 | 0 | 1 | 100% |
| not in knowledge base (holdout) | 78 | 0 | 0 | 0 | 0 | 100% |
| all | 454 | 0 | 0 | 0 | 1 | 100% |

## Details

**C01**
- menu: possible-only refused: v0 <- yuxiang_eggplant
- menu: possible-only refused: v1 <- yuxiang_eggplant
- menu: possible-only refused: v2 <- yuxiang_eggplant
- menu: possible-only refused: v3 <- yuxiang_eggplant
- menu: possible-only refused: v4 <- yuxiang_eggplant
- menu: possible-only refused: v5 <- yuxiang_eggplant
- menu: possible-only refused: v0 <- garlic_bok_choy
- menu: possible-only refused: v1 <- garlic_bok_choy
- menu: possible-only refused: v2 <- garlic_bok_choy
- menu: possible-only refused: v3 <- garlic_bok_choy
- menu: possible-only refused: v4 <- garlic_bok_choy
- menu: possible-only refused: v5 <- garlic_bok_choy
- menu: possible-only refused: v0 <- buddhas_delight
- menu: possible-only refused: v1 <- buddhas_delight
- menu: possible-only refused: v2 <- buddhas_delight
- menu: possible-only refused: v3 <- buddhas_delight
- menu: possible-only refused: v4 <- buddhas_delight
- menu: possible-only refused: v5 <- buddhas_delight
- menu: possible-only refused: v0 <- vegetable_spring_rolls
- menu: possible-only refused: v1 <- vegetable_spring_rolls
- menu: possible-only refused: v2 <- vegetable_spring_rolls
- menu: possible-only refused: v3 <- vegetable_spring_rolls
- menu: possible-only refused: v4 <- vegetable_spring_rolls
- menu: possible-only refused: v5 <- vegetable_spring_rolls
- detail: No order meets the current budget, portions, dietary coverage, and kept dishes. Review the options below, or change your kept dishes or menu.

**C02**
- detail: No order meets the current budget, portions, dietary coverage, and kept dishes. Review the options below, or change your kept dishes or menu.

**H04**
- menu: possible-only refused: vegan <- vegetable_spring_rolls
- menu: possible-only refused: vegan <- buddhas_delight
- menu: possible-only refused: vegan <- garlic_bok_choy

**H05**
- menu: possible-only refused: nopork <- yuxiang_eggplant

**H09**
- menu: possible-only refused: veg <- yuxiang_eggplant
- menu: possible-only refused: nopork <- yuxiang_eggplant
- menu: possible-only refused: veg <- garlic_bok_choy
- menu: possible-only refused: veg <- buddhas_delight
- menu: possible-only refused: veg <- vegetable_lo_mein

**H10**
- refused although a safe order exists
- menu: possible-only refused: david <- garlic_seasonal_greens
- menu: possible-only refused: david <- di_san_xian
- detail: No order meets the current budget, portions, dietary coverage, and kept dishes. Review the options below, or change your kept dishes or menu.

**H11**
- refused although a safe order exists
- menu: possible-only refused: david <- garlic_seasonal_greens
- menu: possible-only refused: david <- di_san_xian
- detail: No order meets the current budget, portions, dietary coverage, and kept dishes. Review the options below, or change your kept dishes or menu.

**L02**
- detail: No order meets the current budget, portions, dietary coverage, and kept dishes. Review the options below, or change your kept dishes or menu.

**L03**
- detail: No order meets the current budget, portions, dietary coverage, and kept dishes. Review the options below, or change your kept dishes or menu.

