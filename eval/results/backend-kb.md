# Bad-case eval: backend-kb

## Summary

| Metric | Value |
|---|---|
| Scenarios passed (safety + money) | **22/22** |
| Scenarios with a severe violation | 0 |
| Severe violations (diner x dish) | 0 |
| Unflagged possible risks | 0 |
| Over budget | 0 |
| Wrong arithmetic | 0 |
| False "no order works" | 5 |
| Menu level: unsafe dishes allowed | 0 |
| Menu level: safe dishes refused | 38 |
| Menu level: possible-only dishes refused | 52 |

## By trap type

Counts are diner x dish pairs; a pair counts under every trap type among its conflicts.

| Trap | Severe in plan | Unsafe allowed (menu) | Safe refused (menu) |
|---|---|---|---|
| explicit | 0 | 0 | 7 |
| hidden | 0 | 0 | 6 |
| name_inference | 0 | 0 | 3 |
| ambiguous | 0 | 0 | 19 |
| compound_sauce | 0 | 0 | 8 |
| false_alarm | 0 | 0 | 0 |
| negative_control | 0 | 0 | 0 |

## Scenarios

| Scenario | Category | Result | Expected | Pass | Usable | Severe | False coverage | Unflagged | Total / limit | Portions |
|---|---|---|---|---|---|---|---|---|---|---|
| B01 | budget | plan | any | ✅ | ✅ | 0 | 0 | 0 | 79.67 / 100.00 | ok |
| B02 | budget | plan | any | ✅ | ✅ | 0 | 0 | 0 | 48.02 / 52.05 | ok |
| B03 | budget | plan | any | ✅ | ✅ | 0 | 0 | 0 | 99.42 / 110.00 | ok |
| B04 | budget | plan | any | ✅ | ✅ | 0 | 0 | 0 | 111.27 / 360.00 | ok |
| B05 | budget | plan | any | ✅ | ✅ | 0 | 0 | 0 | 27.78 / 30.00 | ok |
| C01 | infeasible | conflict | conflict | ✅ | ✅ | 0 | 0 | 0 |  |  |
| C02 | infeasible | conflict | conflict | ✅ | ✅ | 0 | 0 | 0 |  |  |
| C03 | infeasible | plan | any | ✅ | ✅ | 0 | 0 | 0 | 66.99 / 120.00 | ok |
| H01 | hidden_ingredient | conflict | any | ✅ | ❌ refused | 0 | 0 | 0 |  |  |
| H02 | hidden_ingredient | conflict | any | ✅ | ❌ refused | 0 | 0 | 0 |  |  |
| H03 | hidden_ingredient | plan | any | ✅ | ✅ | 0 | 0 | 0 | 56.90 / 90.00 | ok |
| H04 | hidden_ingredient | conflict | any | ✅ | ❌ refused | 0 | 0 | 0 |  |  |
| H05 | hidden_ingredient | plan | any | ✅ | ✅ | 0 | 0 | 0 | 86.02 / 120.00 | ok |
| H06 | hidden_ingredient | plan | plan | ✅ | ✅ | 0 | 0 | 0 | 75.93 / 90.00 | ok |
| H07 | hidden_ingredient | plan | any | ✅ | ✅ | 0 | 0 | 0 | 73.33 / 120.00 | ok |
| H08 | hidden_ingredient | plan | any | ✅ | ✅ | 0 | 0 | 0 | 56.90 / 90.00 | ok |
| H09 | hidden_ingredient | plan | any | ✅ | ✅ | 0 | 0 | 0 | 97.32 / 210.00 | ok |
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
| in knowledge base | 360 | 0 | 0 | 12 | 5 | 95% |
| not in knowledge base (holdout) | 14 | 0 | 16 | 0 | 48 | 18% |
| all | 374 | 0 | 16 | 12 | 53 | 82% |

Missed or weakened, by trap: hidden 13, name_inference 3

- weakened: trap:ants_climbing_tree / soy (reference block, label ask, hidden)
- weakened: trap:ants_climbing_tree / vegetarian (reference block, label ask, name_inference)
- weakened: trap:ants_climbing_tree / vegan (reference block, label ask, name_inference)
- weakened: trap:ants_climbing_tree / no_pork (reference block, label ask, name_inference)
- weakened: trap:xo_green_beans / soy (reference block, label ask, hidden)
- weakened: trap:xo_green_beans / wheat (reference block, label ask, hidden)
- weakened: trap:dry_pot_cauliflower / soy (reference block, label ask, hidden)
- weakened: trap:dry_pot_cauliflower / wheat (reference block, label ask, hidden)
- weakened: trap:dry_pot_cauliflower / vegetarian (reference block, label ask, hidden)
- weakened: trap:dry_pot_cauliflower / vegan (reference block, label ask, hidden)
- weakened: trap:dry_pot_cauliflower / no_pork (reference block, label ask, hidden)
- weakened: sample_sichuan:dry_pot_cauliflower / soy (reference block, label ask, hidden)
- weakened: sample_sichuan:dry_pot_cauliflower / wheat (reference block, label ask, hidden)
- weakened: sample_sichuan:dry_pot_cauliflower / vegetarian (reference block, label ask, hidden)
- weakened: sample_sichuan:dry_pot_cauliflower / vegan (reference block, label ask, hidden)
- weakened: sample_sichuan:dry_pot_cauliflower / no_pork (reference block, label ask, hidden)

## Details

**C01**
- menu: safe refused: v0 <- smashed_cucumber
- menu: safe refused: v1 <- smashed_cucumber
- menu: safe refused: v2 <- smashed_cucumber
- menu: safe refused: v3 <- smashed_cucumber
- menu: safe refused: v4 <- smashed_cucumber
- menu: safe refused: v5 <- smashed_cucumber
- menu: safe refused: v0 <- sesame_cold_noodles
- menu: safe refused: v1 <- sesame_cold_noodles
- menu: safe refused: v2 <- sesame_cold_noodles
- menu: safe refused: v3 <- sesame_cold_noodles
- menu: safe refused: v4 <- sesame_cold_noodles
- menu: safe refused: v5 <- sesame_cold_noodles
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
- detail: A validated order was not found and some dietary evidence is unresolved; confirm with staff. No order meets the current budget, portions, dietary coverage, and kept dishes. Review the options below, or change your kept dishes or menu.

**C02**
- detail: No order meets the current budget, portions, dietary coverage, and kept dishes. Review the options below, or change your kept dishes or menu.

**C03**
- menu: safe refused: soy <- vegetable_spring_rolls
- menu: safe refused: soy <- salt_pepper_shrimp
- menu: safe refused: soy <- cashew_shrimp
- menu: possible-only refused: soy <- smashed_cucumber

**H01**
- refused although a safe order exists
- menu: safe refused: veg <- smashed_cucumber
- detail: A validated order was not found and some dietary evidence is unresolved; confirm with staff. No order meets the current budget, portions, dietary coverage, and kept dishes. Review the options below, or change your kept dishes or menu.

**H02**
- refused although a safe order exists
- menu: safe refused: shell <- beef_chow_fun
- menu: possible-only refused: shell <- garlic_bok_choy
- menu: possible-only refused: shell <- vegetable_lo_mein
- menu: possible-only refused: shell <- dry_fried_beans
- detail: A validated order was not found and some dietary evidence is unresolved; confirm with staff. No order meets the current budget, portions, dietary coverage, and kept dishes. Review the options below, or change your kept dishes or menu.

**H04**
- refused although a safe order exists
- menu: safe refused: vegan <- smashed_cucumber
- menu: possible-only refused: vegan <- vegetable_spring_rolls
- menu: possible-only refused: vegan <- buddhas_delight
- menu: possible-only refused: vegan <- garlic_bok_choy
- detail: A validated order was not found and some dietary evidence is unresolved; confirm with staff. No order meets the current budget, portions, dietary coverage, and kept dishes. Review the options below, or change your kept dishes or menu.

**H05**
- menu: possible-only refused: nopork <- yuxiang_eggplant

**H08**
- menu: possible-only refused: sesame <- smashed_cucumber

**H09**
- menu: safe refused: shell <- ants_climbing_tree
- menu: safe refused: peanut <- ants_climbing_tree
- menu: safe refused: veg <- smashed_cucumber
- menu: safe refused: shell <- smashed_cucumber
- menu: safe refused: peanut <- smashed_cucumber
- menu: safe refused: nopork <- smashed_cucumber
- menu: safe refused: peanut <- xo_green_beans
- menu: safe refused: shell <- dry_pot_cauliflower
- menu: safe refused: peanut <- dry_pot_cauliflower
- menu: safe refused: peanut <- salt_pepper_shrimp
- menu: safe refused: nopork <- salt_pepper_shrimp
- menu: safe refused: shell <- beef_chow_fun
- menu: possible-only refused: veg <- yuxiang_eggplant
- menu: possible-only refused: nopork <- yuxiang_eggplant
- menu: possible-only refused: shell <- dry_fried_beans
- menu: possible-only refused: veg <- garlic_bok_choy
- menu: possible-only refused: shell <- garlic_bok_choy
- menu: possible-only refused: veg <- buddhas_delight
- menu: possible-only refused: shell <- buddhas_delight
- menu: possible-only refused: veg <- vegetable_lo_mein
- menu: possible-only refused: shell <- vegetable_lo_mein

**H10**
- refused although a safe order exists
- menu: safe refused: amy <- dry_pot_cauliflower
- menu: possible-only refused: amy <- dry_fried_string_beans
- menu: possible-only refused: david <- garlic_seasonal_greens
- menu: possible-only refused: amy <- garlic_seasonal_greens
- menu: possible-only refused: david <- di_san_xian
- menu: possible-only refused: amy <- di_san_xian
- detail: A validated order was not found and some dietary evidence is unresolved; confirm with staff. No order meets the current budget, portions, dietary coverage, and kept dishes. Review the options below, or change your kept dishes or menu.

**H11**
- refused although a safe order exists
- menu: safe refused: amy <- dry_pot_cauliflower
- menu: possible-only refused: amy <- dry_fried_string_beans
- menu: possible-only refused: david <- garlic_seasonal_greens
- menu: possible-only refused: amy <- garlic_seasonal_greens
- menu: possible-only refused: david <- di_san_xian
- menu: possible-only refused: amy <- di_san_xian
- detail: A validated order was not found and some dietary evidence is unresolved; confirm with staff. No order meets the current budget, portions, dietary coverage, and kept dishes. Review the options below, or change your kept dishes or menu.

**L01**
- menu: safe refused: peanut <- ants_climbing_tree
- menu: safe refused: peanut <- smashed_cucumber
- menu: safe refused: peanut <- xo_green_beans
- menu: safe refused: peanut <- dry_pot_cauliflower
- menu: safe refused: peanut <- salt_pepper_shrimp

**L02**
- menu: safe refused: veg <- smashed_cucumber
- detail: A validated order was not found and some dietary evidence is unresolved; confirm with staff. No order meets the current budget, portions, dietary coverage, and kept dishes. Review the options below, or change your kept dishes or menu.

**L03**
- detail: No order meets the current budget, portions, dietary coverage, and kept dishes. Review the options below, or change your kept dishes or menu.

