# Bad-case eval: planner-current

## Summary

| Metric | Value |
|---|---|
| Scenarios passed (safety + money) | **13/22** |
| Scenarios with a severe violation | 9 |
| Severe violations (diner x dish) | 14 |
| Unflagged possible risks | 12 |
| Over budget | 0 |
| Wrong arithmetic | 0 |
| False "no order works" | 0 |
| Menu level: unsafe dishes allowed | 103 |
| Menu level: safe dishes refused | 1 |
| Menu level: possible-only dishes refused | 7 |

## By trap type

Counts are diner x dish pairs; a pair counts under every trap type among its conflicts.

| Trap | Severe in plan | Unsafe allowed (menu) | Safe refused (menu) |
|---|---|---|---|
| explicit | 0 | 0 | 0 |
| hidden | 9 | 56 | 0 |
| name_inference | 4 | 33 | 0 |
| ambiguous | 0 | 0 | 1 |
| compound_sauce | 1 | 14 | 0 |
| false_alarm | 0 | 0 | 1 |
| negative_control | 0 | 0 | 0 |

## Scenarios

| Scenario | Category | Result | Expected | Pass | Usable | Severe | False coverage | Unflagged | Total / limit | Portions |
|---|---|---|---|---|---|---|---|---|---|---|
| B01 | budget | plan | any | ✅ | ✅ | 0 | 0 | 0 | 75.87 / 100.00 | ok |
| B02 | budget | plan | any | ✅ | ✅ | 0 | 0 | 0 | 44.21 / 52.05 | ok |
| B03 | budget | plan | any | ✅ | ✅ | 0 | 0 | 0 | 96.90 / 110.00 | ok |
| B04 | budget | plan | any | ✅ | ✅ | 0 | 0 | 0 | 111.27 / 360.00 | ok |
| B05 | budget | plan | any | ✅ | ✅ | 0 | 0 | 0 | 27.78 / 30.00 | ok |
| C01 | infeasible | conflict | conflict | ✅ | ✅ | 0 | 0 | 0 |  |  |
| C02 | infeasible | conflict | conflict | ✅ | ✅ | 0 | 0 | 0 |  |  |
| C03 | infeasible | plan | any | ❌ | ✅ | 2 | 1 | 0 | 75.87 / 120.00 | ok |
| H01 | hidden_ingredient | plan | any | ❌ | ✅ | 4 | 1 | 1 | 49.29 / 90.00 | ok |
| H02 | hidden_ingredient | plan | any | ❌ | ✅ | 1 | 0 | 1 | 82.21 / 120.00 | ok |
| H03 | hidden_ingredient | plan | any | ✅ | ✅ | 0 | 0 | 0 | 56.90 / 90.00 | ok |
| H04 | hidden_ingredient | plan | any | ✅ | ✅ | 0 | 0 | 2 | 70.79 / 120.00 | ok |
| H05 | hidden_ingredient | plan | any | ❌ | ✅ | 2 | 0 | 1 | 83.48 / 120.00 | ok |
| H06 | hidden_ingredient | plan | plan | ❌ | ✅ | 1 | 1 | 0 | 77.20 / 90.00 | ok |
| H07 | hidden_ingredient | plan | any | ❌ | ✅ | 1 | 0 | 0 | 66.99 / 120.00 | ok |
| H08 | hidden_ingredient | plan | any | ✅ | ✅ | 0 | 0 | 0 | 56.90 / 90.00 | ok |
| H09 | hidden_ingredient | plan | any | ❌ | ✅ | 3 | 0 | 2 | 111.27 / 210.00 | ok |
| H10 | hidden_ingredient | plan | any | ✅ | ✅ | 0 | 0 | 3 | 54.36 / 90.00 | ok |
| H11 | hidden_ingredient | plan | any | ✅ | ✅ | 0 | 0 | 3 | 118.89 / 180.00 | ok |
| L01 | lock_exclude | plan | any | ❌ | ✅ | 1 | 0 | 0 | 82.21 / 120.00 | ok |
| L02 | lock_exclude | plan | conflict | ❌ | ✅ | 3 | 1 | 1 | 63.24 / 90.00 | ok |
| L03 | lock_exclude | conflict | conflict | ✅ | ✅ | 0 | 0 | 0 |  |  |

## Label accuracy

Every dish x restriction (9 allergens, 4 diets) on both eval menus: does the label say
block / ask staff / clear, as the reference does? **missed** = reference blocks, label
clears (dangerous). **weakened** = reference blocks, label only asks. **unflagged** =
reference asks, label clears. **stricter** = label more cautious than the reference.

| Dishes | correct | missed | weakened | unflagged | stricter | accuracy |
|---|---|---|---|---|---|---|
| in knowledge base | 301 | 45 | 9 | 19 | 3 | 80% |
| not in knowledge base (holdout) | 53 | 17 | 3 | 5 | 0 | 68% |
| all | 354 | 62 | 12 | 24 | 3 | 78% |

Missed or weakened, by trap: hidden 52, name_inference 16, compound_sauce 6

- missed: trap:ants_climbing_tree / soy (reference block, label clear, hidden)
- missed: trap:ants_climbing_tree / vegetarian (reference block, label clear, name_inference)
- missed: trap:ants_climbing_tree / vegan (reference block, label clear, name_inference)
- missed: trap:ants_climbing_tree / no_pork (reference block, label clear, name_inference)
- missed: trap:yuxiang_eggplant / soy (reference block, label clear, hidden)
- missed: trap:yuxiang_eggplant / wheat (reference block, label clear, hidden)
- missed: trap:mapo_tofu / wheat (reference block, label clear, name_inference)
- missed: trap:mapo_tofu / vegetarian (reference block, label clear, name_inference)
- missed: trap:mapo_tofu / vegan (reference block, label clear, name_inference)
- missed: trap:mapo_tofu / no_pork (reference block, label clear, name_inference)
- missed: trap:hot_sour_soup / egg (reference block, label clear, hidden)
- missed: trap:hot_sour_soup / wheat (reference block, label clear, hidden)
- missed: trap:hot_sour_soup / vegetarian (reference block, label clear, hidden)
- missed: trap:hot_sour_soup / vegan (reference block, label clear, hidden)
- missed: trap:hot_sour_soup / no_pork (reference block, label clear, hidden)
- missed: trap:kung_pao_chicken / peanut (reference block, label clear, hidden)
- missed: trap:kung_pao_chicken / soy (reference block, label clear, hidden)
- missed: trap:kung_pao_chicken / wheat (reference block, label clear, hidden)
- missed: trap:dan_dan_noodles / peanut (reference block, label clear, name_inference)
- missed: trap:dan_dan_noodles / sesame (reference block, label clear, name_inference)
- missed: trap:dan_dan_noodles / soy (reference block, label clear, hidden)
- missed: trap:dan_dan_noodles / vegetarian (reference block, label clear, name_inference)
- missed: trap:dan_dan_noodles / vegan (reference block, label clear, name_inference)
- missed: trap:dan_dan_noodles / no_pork (reference block, label clear, name_inference)
- missed: trap:dry_fried_beans / soy (reference block, label clear, hidden)
- missed: trap:dry_fried_beans / wheat (reference block, label clear, hidden)
- missed: trap:dry_fried_beans / vegetarian (reference block, label clear, hidden)
- missed: trap:dry_fried_beans / vegan (reference block, label clear, hidden)
- missed: trap:dry_fried_beans / no_pork (reference block, label clear, hidden)
- missed: trap:xo_green_beans / fish (reference block, label clear, compound_sauce)
- missed: trap:xo_green_beans / shellfish (reference block, label clear, compound_sauce)
- missed: trap:xo_green_beans / soy (reference block, label clear, hidden)
- missed: trap:xo_green_beans / wheat (reference block, label clear, hidden)
- missed: trap:xo_green_beans / vegetarian (reference block, label clear, compound_sauce)
- missed: trap:xo_green_beans / vegan (reference block, label clear, compound_sauce)
- missed: trap:xo_green_beans / no_pork (reference block, label clear, compound_sauce)
- missed: trap:buddhas_delight / wheat (reference block, label clear, hidden)
- missed: trap:vegetable_lo_mein / soy (reference block, label clear, hidden)
- missed: trap:vegetable_spring_rolls / wheat (reference block, label clear, hidden)
- missed: trap:house_fried_rice / egg (reference block, label clear, hidden)
- missed: trap:house_fried_rice / shellfish (reference block, label clear, hidden)
- missed: trap:house_fried_rice / soy (reference block, label clear, hidden)
- missed: trap:house_fried_rice / wheat (reference block, label clear, hidden)
- missed: trap:house_fried_rice / vegetarian (reference block, label clear, hidden)
- missed: trap:house_fried_rice / vegan (reference block, label clear, hidden)
- missed: trap:house_fried_rice / no_pork (reference block, label clear, hidden)
- missed: trap:dry_pot_cauliflower / soy (reference block, label clear, hidden)
- missed: trap:dry_pot_cauliflower / wheat (reference block, label clear, hidden)
- missed: trap:dry_pot_cauliflower / vegetarian (reference block, label clear, hidden)
- missed: trap:dry_pot_cauliflower / vegan (reference block, label clear, hidden)
- missed: trap:dry_pot_cauliflower / no_pork (reference block, label clear, hidden)
- missed: trap:sesame_cold_noodles / peanut (reference block, label clear, compound_sauce)
- missed: trap:sesame_cold_noodles / soy (reference block, label clear, hidden)
- missed: trap:boiled_fish / soy (reference block, label clear, hidden)
- missed: trap:boiled_fish / wheat (reference block, label clear, hidden)
- missed: trap:beef_chow_fun / soy (reference block, label clear, hidden)
- missed: sample_sichuan:garlic_pork_belly / wheat (reference block, label clear, hidden)
- weakened: sample_sichuan:mapo_tofu / wheat (reference block, label ask, name_inference)
- weakened: sample_sichuan:mapo_tofu / vegetarian (reference block, label ask, name_inference)
- weakened: sample_sichuan:mapo_tofu / vegan (reference block, label ask, name_inference)
- weakened: sample_sichuan:mapo_tofu / no_pork (reference block, label ask, name_inference)
- missed: sample_sichuan:dry_fried_string_beans / wheat (reference block, label clear, hidden)
- weakened: sample_sichuan:dry_fried_string_beans / vegetarian (reference block, label ask, hidden)
- weakened: sample_sichuan:dry_fried_string_beans / vegan (reference block, label ask, hidden)
- weakened: sample_sichuan:dry_fried_string_beans / no_pork (reference block, label ask, hidden)
- missed: sample_sichuan:di_san_xian / wheat (reference block, label clear, hidden)
- missed: sample_sichuan:dry_pot_cauliflower / wheat (reference block, label clear, hidden)
- weakened: sample_sichuan:dry_pot_cauliflower / vegetarian (reference block, label ask, hidden)
- weakened: sample_sichuan:dry_pot_cauliflower / vegan (reference block, label ask, hidden)
- weakened: sample_sichuan:dry_pot_cauliflower / no_pork (reference block, label ask, hidden)
- missed: sample_sichuan:boiled_fish_chili_oil / wheat (reference block, label clear, hidden)
- weakened: sample_sichuan:hot_and_sour_soup / vegetarian (reference block, label ask, hidden)
- weakened: sample_sichuan:hot_and_sour_soup / no_pork (reference block, label ask, hidden)
- missed: sample_sichuan:dan_dan_noodles / soy (reference block, label clear, hidden)

## Details

**C01**
- menu: unsafe allowed: v0 <- ants_climbing_tree: minced pork (pork, definite)
- menu: unsafe allowed: v1 <- ants_climbing_tree: minced pork (pork, definite)
- menu: unsafe allowed: v2 <- ants_climbing_tree: minced pork (pork, definite)
- menu: unsafe allowed: v3 <- ants_climbing_tree: minced pork (pork, definite)
- menu: unsafe allowed: v4 <- ants_climbing_tree: minced pork (pork, definite)
- menu: unsafe allowed: v5 <- ants_climbing_tree: minced pork (pork, definite)
- menu: unsafe allowed: v0 <- mapo_tofu: minced meat (meat, definite)
- menu: unsafe allowed: v0 <- mapo_tofu: minced pork (pork, likely)
- menu: unsafe allowed: v1 <- mapo_tofu: minced meat (meat, definite)
- menu: unsafe allowed: v1 <- mapo_tofu: minced pork (pork, likely)
- menu: unsafe allowed: v2 <- mapo_tofu: minced meat (meat, definite)
- menu: unsafe allowed: v2 <- mapo_tofu: minced pork (pork, likely)
- menu: unsafe allowed: v3 <- mapo_tofu: minced meat (meat, definite)
- menu: unsafe allowed: v3 <- mapo_tofu: minced pork (pork, likely)
- menu: unsafe allowed: v4 <- mapo_tofu: minced meat (meat, definite)
- menu: unsafe allowed: v4 <- mapo_tofu: minced pork (pork, likely)
- menu: unsafe allowed: v5 <- mapo_tofu: minced meat (meat, definite)
- menu: unsafe allowed: v5 <- mapo_tofu: minced pork (pork, likely)
- menu: unsafe allowed: v0 <- hot_sour_soup: egg ribbons (egg, likely)
- menu: unsafe allowed: v0 <- hot_sour_soup: shredded pork (pork, likely)
- menu: unsafe allowed: v0 <- hot_sour_soup: chicken stock (meat_stock, likely)
- menu: unsafe allowed: v1 <- hot_sour_soup: egg ribbons (egg, likely)
- menu: unsafe allowed: v1 <- hot_sour_soup: shredded pork (pork, likely)
- menu: unsafe allowed: v1 <- hot_sour_soup: chicken stock (meat_stock, likely)
- menu: unsafe allowed: v2 <- hot_sour_soup: egg ribbons (egg, likely)
- menu: unsafe allowed: v2 <- hot_sour_soup: shredded pork (pork, likely)
- menu: unsafe allowed: v2 <- hot_sour_soup: chicken stock (meat_stock, likely)
- menu: unsafe allowed: v3 <- hot_sour_soup: egg ribbons (egg, likely)
- menu: unsafe allowed: v3 <- hot_sour_soup: shredded pork (pork, likely)
- menu: unsafe allowed: v3 <- hot_sour_soup: chicken stock (meat_stock, likely)
- menu: unsafe allowed: v4 <- hot_sour_soup: egg ribbons (egg, likely)
- menu: unsafe allowed: v4 <- hot_sour_soup: shredded pork (pork, likely)
- menu: unsafe allowed: v4 <- hot_sour_soup: chicken stock (meat_stock, likely)
- menu: unsafe allowed: v5 <- hot_sour_soup: egg ribbons (egg, likely)
- menu: unsafe allowed: v5 <- hot_sour_soup: shredded pork (pork, likely)
- menu: unsafe allowed: v5 <- hot_sour_soup: chicken stock (meat_stock, likely)
- menu: unsafe allowed: v0 <- dan_dan_noodles: minced pork (pork, likely)
- menu: unsafe allowed: v1 <- dan_dan_noodles: minced pork (pork, likely)
- menu: unsafe allowed: v2 <- dan_dan_noodles: minced pork (pork, likely)
- menu: unsafe allowed: v3 <- dan_dan_noodles: minced pork (pork, likely)
- menu: unsafe allowed: v4 <- dan_dan_noodles: minced pork (pork, likely)
- menu: unsafe allowed: v5 <- dan_dan_noodles: minced pork (pork, likely)
- menu: unsafe allowed: v0 <- dry_fried_beans: minced pork (pork, likely)
- menu: unsafe allowed: v1 <- dry_fried_beans: minced pork (pork, likely)
- menu: unsafe allowed: v2 <- dry_fried_beans: minced pork (pork, likely)
- menu: unsafe allowed: v3 <- dry_fried_beans: minced pork (pork, likely)
- menu: unsafe allowed: v4 <- dry_fried_beans: minced pork (pork, likely)
- menu: unsafe allowed: v5 <- dry_fried_beans: minced pork (pork, likely)
- menu: unsafe allowed: v0 <- xo_green_beans: dried scallop and shrimp (XO sauce) (shellfish, definite)
- menu: unsafe allowed: v0 <- xo_green_beans: dried fish (XO sauce) (fish, likely)
- menu: unsafe allowed: v0 <- xo_green_beans: cured ham (XO sauce) (pork, likely)
- menu: unsafe allowed: v1 <- xo_green_beans: dried scallop and shrimp (XO sauce) (shellfish, definite)
- menu: unsafe allowed: v1 <- xo_green_beans: dried fish (XO sauce) (fish, likely)
- menu: unsafe allowed: v1 <- xo_green_beans: cured ham (XO sauce) (pork, likely)
- menu: unsafe allowed: v2 <- xo_green_beans: dried scallop and shrimp (XO sauce) (shellfish, definite)
- menu: unsafe allowed: v2 <- xo_green_beans: dried fish (XO sauce) (fish, likely)
- menu: unsafe allowed: v2 <- xo_green_beans: cured ham (XO sauce) (pork, likely)
- menu: unsafe allowed: v3 <- xo_green_beans: dried scallop and shrimp (XO sauce) (shellfish, definite)
- menu: unsafe allowed: v3 <- xo_green_beans: dried fish (XO sauce) (fish, likely)
- menu: unsafe allowed: v3 <- xo_green_beans: cured ham (XO sauce) (pork, likely)
- menu: unsafe allowed: v4 <- xo_green_beans: dried scallop and shrimp (XO sauce) (shellfish, definite)
- menu: unsafe allowed: v4 <- xo_green_beans: dried fish (XO sauce) (fish, likely)
- menu: unsafe allowed: v4 <- xo_green_beans: cured ham (XO sauce) (pork, likely)
- menu: unsafe allowed: v5 <- xo_green_beans: dried scallop and shrimp (XO sauce) (shellfish, definite)
- menu: unsafe allowed: v5 <- xo_green_beans: dried fish (XO sauce) (fish, likely)
- menu: unsafe allowed: v5 <- xo_green_beans: cured ham (XO sauce) (pork, likely)
- menu: unsafe allowed: v0 <- house_fried_rice: egg (egg, definite)
- menu: unsafe allowed: v0 <- house_fried_rice: shrimp (shellfish, likely)
- menu: unsafe allowed: v0 <- house_fried_rice: char siu pork (pork, likely)
- menu: unsafe allowed: v1 <- house_fried_rice: egg (egg, definite)
- menu: unsafe allowed: v1 <- house_fried_rice: shrimp (shellfish, likely)
- menu: unsafe allowed: v1 <- house_fried_rice: char siu pork (pork, likely)
- menu: unsafe allowed: v2 <- house_fried_rice: egg (egg, definite)
- menu: unsafe allowed: v2 <- house_fried_rice: shrimp (shellfish, likely)
- menu: unsafe allowed: v2 <- house_fried_rice: char siu pork (pork, likely)
- menu: unsafe allowed: v3 <- house_fried_rice: egg (egg, definite)
- menu: unsafe allowed: v3 <- house_fried_rice: shrimp (shellfish, likely)
- menu: unsafe allowed: v3 <- house_fried_rice: char siu pork (pork, likely)
- menu: unsafe allowed: v4 <- house_fried_rice: egg (egg, definite)
- menu: unsafe allowed: v4 <- house_fried_rice: shrimp (shellfish, likely)
- menu: unsafe allowed: v4 <- house_fried_rice: char siu pork (pork, likely)
- menu: unsafe allowed: v5 <- house_fried_rice: egg (egg, definite)
- menu: unsafe allowed: v5 <- house_fried_rice: shrimp (shellfish, likely)
- menu: unsafe allowed: v5 <- house_fried_rice: char siu pork (pork, likely)
- menu: unsafe allowed: v0 <- dry_pot_cauliflower: pork belly (pork, likely)
- menu: unsafe allowed: v1 <- dry_pot_cauliflower: pork belly (pork, likely)
- menu: unsafe allowed: v2 <- dry_pot_cauliflower: pork belly (pork, likely)
- menu: unsafe allowed: v3 <- dry_pot_cauliflower: pork belly (pork, likely)
- menu: unsafe allowed: v4 <- dry_pot_cauliflower: pork belly (pork, likely)
- menu: unsafe allowed: v5 <- dry_pot_cauliflower: pork belly (pork, likely)
- menu: possible-only refused: v0 <- yuxiang_eggplant
- menu: possible-only refused: v1 <- yuxiang_eggplant
- menu: possible-only refused: v2 <- yuxiang_eggplant
- menu: possible-only refused: v3 <- yuxiang_eggplant
- menu: possible-only refused: v4 <- yuxiang_eggplant
- menu: possible-only refused: v5 <- yuxiang_eggplant
- detail: No order meets the current budget, portions, dietary coverage, and kept dishes. Review the options below, or change your kept dishes or menu.

**C02**
- detail: No order meets the current budget, portions, dietary coverage, and kept dishes. Review the options below, or change your kept dishes or menu.

**C03**
- severe: soy <- vegetable_lo_mein: soy sauce (soy, definite)
- severe: soy <- boiled_fish: doubanjiang (soy, likely)
- false coverage: soy: 1 truly safe dishes, needs 2
- menu: unsafe allowed: soy <- ants_climbing_tree: soy sauce (soy, likely)
- menu: unsafe allowed: soy <- yuxiang_eggplant: soy sauce (soy, likely)
- menu: unsafe allowed: soy <- kung_pao_chicken: soy sauce (soy, definite)
- menu: unsafe allowed: soy <- dan_dan_noodles: soy sauce (soy, definite)
- menu: unsafe allowed: soy <- dry_fried_beans: soy sauce (soy, likely)
- menu: unsafe allowed: soy <- xo_green_beans: soy sauce (soy, likely)
- menu: unsafe allowed: soy <- vegetable_lo_mein: soy sauce (soy, definite)
- menu: unsafe allowed: soy <- house_fried_rice: soy sauce (soy, likely)
- menu: unsafe allowed: soy <- dry_pot_cauliflower: soy sauce (soy, likely)
- menu: unsafe allowed: soy <- sesame_cold_noodles: soy sauce (soy, likely)
- menu: unsafe allowed: soy <- boiled_fish: doubanjiang (soy, likely)
- menu: unsafe allowed: soy <- beef_chow_fun: soy sauce (soy, definite)

**H01**
- severe: veg <- hot_sour_soup: shredded pork (pork, likely)
- severe: veg <- hot_sour_soup: chicken stock (meat_stock, likely)
- severe: veg <- mapo_tofu: minced meat (meat, definite)
- severe: veg <- mapo_tofu: minced pork (pork, likely)
- false coverage: veg: 1 truly safe dishes, needs 2
- unflagged: veg <- mapo_tofu: minced beef (beef, possible)
- menu: unsafe allowed: veg <- ants_climbing_tree: minced pork (pork, definite)
- menu: unsafe allowed: veg <- mapo_tofu: minced meat (meat, definite)
- menu: unsafe allowed: veg <- mapo_tofu: minced pork (pork, likely)
- menu: unsafe allowed: veg <- hot_sour_soup: shredded pork (pork, likely)
- menu: unsafe allowed: veg <- hot_sour_soup: chicken stock (meat_stock, likely)

**H02**
- severe: shell <- house_fried_rice: shrimp (shellfish, likely)
- unflagged: shell <- vegetable_lo_mein: oyster sauce (shellfish, possible)
- menu: unsafe allowed: shell <- xo_green_beans: dried scallop and shrimp (XO sauce) (shellfish, definite)
- menu: unsafe allowed: shell <- house_fried_rice: shrimp (shellfish, likely)

**H03**
- menu: unsafe allowed: peanut <- kung_pao_chicken: peanuts (peanut, definite)
- menu: unsafe allowed: peanut <- sesame_cold_noodles: peanut butter (peanut, likely)
- menu: unsafe allowed: peanut <- dan_dan_noodles: crushed peanuts (peanut, likely)

**H04**
- unflagged: vegan <- vegetable_spring_rolls: egg wash (egg, possible)
- unflagged: vegan <- buddhas_delight: oyster sauce (shellfish, possible)
- menu: unsafe allowed: vegan <- hot_sour_soup: egg ribbons (egg, likely)
- menu: unsafe allowed: vegan <- hot_sour_soup: shredded pork (pork, likely)
- menu: unsafe allowed: vegan <- hot_sour_soup: chicken stock (meat_stock, likely)

**H05**
- severe: nopork <- house_fried_rice: char siu pork (pork, likely)
- severe: nopork <- mapo_tofu: minced pork (pork, likely)
- unflagged: nopork <- yuxiang_eggplant: minced pork (pork, possible)
- menu: unsafe allowed: nopork <- mapo_tofu: minced pork (pork, likely)
- menu: unsafe allowed: nopork <- dry_fried_beans: minced pork (pork, likely)
- menu: unsafe allowed: nopork <- dry_pot_cauliflower: pork belly (pork, likely)
- menu: unsafe allowed: nopork <- house_fried_rice: char siu pork (pork, likely)

**H06**
- severe: fish <- xo_green_beans: dried fish (XO sauce) (fish, likely)
- false coverage: fish: 1 truly safe dishes, needs 2
- menu: unsafe allowed: fish <- xo_green_beans: dried fish (XO sauce) (fish, likely)
- menu: safe refused: fish <- yuxiang_eggplant

**H07**
- severe: egg <- hot_sour_soup: egg ribbons (egg, likely)
- menu: unsafe allowed: egg <- house_fried_rice: egg (egg, definite)
- menu: unsafe allowed: egg <- hot_sour_soup: egg ribbons (egg, likely)

**H08**
- menu: unsafe allowed: sesame <- dan_dan_noodles: sesame paste (sesame, likely)

**H09**
- severe: veg <- hot_sour_soup: shredded pork (pork, likely)
- severe: veg <- hot_sour_soup: chicken stock (meat_stock, likely)
- severe: nopork <- hot_sour_soup: shredded pork (pork, likely)
- unflagged: veg <- vegetable_lo_mein: oyster sauce (shellfish, possible)
- unflagged: shell <- vegetable_lo_mein: oyster sauce (shellfish, possible)
- menu: unsafe allowed: veg <- ants_climbing_tree: minced pork (pork, definite)
- menu: unsafe allowed: nopork <- ants_climbing_tree: minced pork (pork, definite)
- menu: unsafe allowed: veg <- mapo_tofu: minced meat (meat, definite)
- menu: unsafe allowed: veg <- mapo_tofu: minced pork (pork, likely)
- menu: unsafe allowed: nopork <- mapo_tofu: minced pork (pork, likely)
- menu: unsafe allowed: veg <- hot_sour_soup: shredded pork (pork, likely)
- menu: unsafe allowed: veg <- hot_sour_soup: chicken stock (meat_stock, likely)
- menu: unsafe allowed: nopork <- hot_sour_soup: shredded pork (pork, likely)
- menu: unsafe allowed: peanut <- kung_pao_chicken: peanuts (peanut, definite)
- menu: unsafe allowed: veg <- dan_dan_noodles: minced pork (pork, likely)
- menu: unsafe allowed: peanut <- dan_dan_noodles: crushed peanuts (peanut, likely)
- menu: unsafe allowed: nopork <- dan_dan_noodles: minced pork (pork, likely)
- menu: unsafe allowed: veg <- dry_fried_beans: minced pork (pork, likely)
- menu: unsafe allowed: nopork <- dry_fried_beans: minced pork (pork, likely)
- menu: unsafe allowed: veg <- xo_green_beans: dried scallop and shrimp (XO sauce) (shellfish, definite)
- menu: unsafe allowed: veg <- xo_green_beans: dried fish (XO sauce) (fish, likely)
- menu: unsafe allowed: veg <- xo_green_beans: cured ham (XO sauce) (pork, likely)
- menu: unsafe allowed: shell <- xo_green_beans: dried scallop and shrimp (XO sauce) (shellfish, definite)
- menu: unsafe allowed: nopork <- xo_green_beans: cured ham (XO sauce) (pork, likely)
- menu: unsafe allowed: veg <- house_fried_rice: shrimp (shellfish, likely)
- menu: unsafe allowed: veg <- house_fried_rice: char siu pork (pork, likely)
- menu: unsafe allowed: shell <- house_fried_rice: shrimp (shellfish, likely)
- menu: unsafe allowed: nopork <- house_fried_rice: char siu pork (pork, likely)
- menu: unsafe allowed: veg <- dry_pot_cauliflower: pork belly (pork, likely)
- menu: unsafe allowed: nopork <- dry_pot_cauliflower: pork belly (pork, likely)
- menu: unsafe allowed: peanut <- sesame_cold_noodles: peanut butter (peanut, likely)
- menu: possible-only refused: veg <- yuxiang_eggplant

**H10**
- unflagged: david <- garlic_seasonal_greens: oyster sauce (shellfish, possible)
- unflagged: david <- garlic_seasonal_greens: chicken broth or powder (meat_stock, possible)
- unflagged: amy <- garlic_seasonal_greens: oyster sauce (shellfish, possible)

**H11**
- unflagged: david <- garlic_seasonal_greens: oyster sauce (shellfish, possible)
- unflagged: david <- garlic_seasonal_greens: chicken broth or powder (meat_stock, possible)
- unflagged: amy <- garlic_seasonal_greens: oyster sauce (shellfish, possible)

**L01**
- severe: peanut <- kung_pao_chicken: peanuts (peanut, definite)
- menu: unsafe allowed: peanut <- kung_pao_chicken: peanuts (peanut, definite)
- menu: unsafe allowed: peanut <- dan_dan_noodles: crushed peanuts (peanut, likely)
- menu: unsafe allowed: peanut <- sesame_cold_noodles: peanut butter (peanut, likely)

**L02**
- severe: veg <- ants_climbing_tree: minced pork (pork, definite)
- severe: veg <- mapo_tofu: minced meat (meat, definite)
- severe: veg <- mapo_tofu: minced pork (pork, likely)
- false coverage: veg: 0 truly safe dishes, needs 2
- outcome plan, expected conflict
- unflagged: veg <- mapo_tofu: minced beef (beef, possible)
- menu: unsafe allowed: veg <- ants_climbing_tree: minced pork (pork, definite)
- menu: unsafe allowed: veg <- mapo_tofu: minced meat (meat, definite)
- menu: unsafe allowed: veg <- mapo_tofu: minced pork (pork, likely)

**L03**
- detail: No order meets the current budget, portions, dietary coverage, and kept dishes. Review the options below, or change your kept dishes or menu.

