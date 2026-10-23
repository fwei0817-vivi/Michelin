# Test menus: real NYC Chinese restaurants

Six real menus to stress the photo import and the safety rules. They are a mix of
Sichuan, Cantonese dim sum, Shanghainese dumplings, Hunan and Chinese-American takeout,
with plenty of dishes that are hard for allergies and diets: peanut, sesame, shellfish,
pork and lard, egg, and oyster or XO sauce.
Every dish and price comes from the restaurant's own menu. Nothing was made up.

All files were fetched on **2026-10-09**. Prices can change after that date.

| File | Restaurant | Style | Neighborhood | Source | Dishes in file | Kind |
|---|---|---|---|---|---|---|
| `nom-wah-tea-parlor.jpg` | Nom Wah Tea Parlor, 13 Doyers St | Cantonese dim sum | Chinatown | <https://www.nomwah.com/s/NYC-Menu-Legal-8_1.pdf> | 49 | **Real menu**: both pages of the restaurant's PDF, placed side by side as one JPEG (the 2.1 MB PDF is not committed) |
| `cafe-mandarin.jpg` | Cafe Mandarin, 1st Ave at 67th St | Sichuan / Chinese-American | Upper East Side | <https://cafemandarinnyc.com/wp-content/uploads/2026/07/Menu0707.pdf> | 35 lines (54 orderable versions: 7 lines offer a choice of protein) | **Real menu**: pages 1–2 of the restaurant's PDF |
| `cafe-mandarin.pdf` | Cafe Mandarin | | | same as above | 62 lines on 4 pages (93 orderable versions). An earlier count here said 74; a recount of the PDF gives 35 + 11 + 16 = 62 priced lines. | **Original PDF.** The photo step accepts it: the server renders each page to an image. |
| `cafe-mandarin-p1.jpg` … `-p4.jpg` | Cafe Mandarin | | | same as above | 18 / 17 / 11 / 16 lines | The PDF's 4 pages as JPEGs (`pdftoppm -r 110`, about 125 KB each), for testing several pages in one upload |
| `hwa-yuan.jpg` | Hwa Yuan Szechuan, 42 East Broadway | Sichuan | Chinatown | <https://www.hwayuannyc.com/menu> | 53 | **Rendered from the real HTML text** |
| `shanghai-21.jpg` | Shanghai 21, 21 Mott St | Shanghainese / soup dumplings | Chinatown | <https://shanghai21nyc.com/menu/> | 45 | **Rendered from the real HTML text** |
| `hunan-slurp.jpg` | Hunan Slurp, 112 First Ave | Hunan | East Village | <https://www.hunanslurp.com/menu> | 36 | **Rendered from the real HTML text** |
| `wo-hop.jpg` | Wo Hop, 17 Mott St | Chinese-American takeout | Chinatown | <https://www.wohop17.com/menu-1?menu=menu> | 48 | **Rendered from the real HTML text** |

## About the rendered menus

Four of the restaurants publish their menu only as text on a web page. For those, we copied
the names, Chinese names, prices and printed descriptions word for word and laid them out as
a plain menu image. Each image has a footer that says so: "Menu text as published at <url>
(fetched 2026-10-09). Typeset for testing; not the restaurant's own design." The layout is
ours, but every dish and price is the restaurant's.

To keep each menu in the 25–60 range, we used only some sections and left a few things out:

- **Hwa Yuan:** Hot and Cold Appetizers, Soups, Garden, and Poultry. Market-price items are left out.
- **Shanghai 21:** Dim Sum & Appetizers, Cold Dishes, and Noodles in Soup.
- **Hunan Slurp:** Cold Plate, Hot Plate, and Rice Noodle. Drinks are left out.
- **Wo Hop:** Appetizers and Sides, Szechuan Specialties, and the "Spicy w/Peanuts & Vegetables"
  (Goon Bo) section. On the site, the peanut information is in that section's header.
  "Mild" labels are left out.

Some other menus were left out on purpose:

- **Jing Fong:** its prices are S/M/L codes, not dollar amounts.
- **Shu Jiao Fu Zhou** (Fujianese): its site could not be reached.
- **Flushing restaurants:** their sites were blocked or timed out.

## How to use them locally

1. Start the app (see the main README). The web UI is at <http://localhost:8010>.
2. Add the diners. A hard test table has four people: one with a peanut allergy, one with a
   shellfish allergy, one vegetarian, and one who eats no pork.
3. In the **photo step**, upload one of the `.jpg` files. Check the dish list it reads
   against the image, then plan.

## Results from the live runs (2026-10-09)

The table: four people, $40 each all-in. One has a peanut allergy, one a shellfish allergy, one
is vegetarian and one eats no pork.

**Run A** was the first run: `google/gemini-2.5-flash`, before the photo step split menu
choices into separate dishes. **Run B** is the current code: `google/gemini-3.5-flash-lite`
with reasoning effort "low", and the photo step splits choices and reads the menu's marks.

| Menu | Dishes read, run A | Dishes read, run B | Read + facts time, A / B | Plan, A | Plan, B (first try) | Plan time, A / B |
|---|---|---|---|---|---|---|
| Cafe Mandarin | 35 / 35 lines; "Kung Pao" read as one $18 dish | 35 / 35 lines, giving **54 versions** with the right prices ($18 / $20 / $22 / $18); marks V, VP, GF, GP and peppers read | 30 s / 36 s | valid, 6 dishes, $109 | valid, 4 dishes, $81, ordered **Sesame (Tofu)**, **Cumin (Tofu)**, **Mongolian (Beef)** | 2.6 s / 2.6 s |
| Hunan Slurp | 36 / 36 | 36 / 36 | 8.5 s (facts cached) / 20 s | valid, $126 | valid, $118 | 0.1 s / 0.1 s (cached) |
| Hwa Yuan | 53 / 53 | 53 / 53 | 88 s / 31 s | valid, $134 | valid, $100 | 3.6 s / 2.0 s |
| Nom Wah | 48 / 49 ("Pork Siu Mal") | 48 / 49 ("Pork Siu Mai", correct) | 42 s / 31 s | valid, $65 | valid, $36 | 4.2 s / 2.0 s |
| Shanghai 21 | 45 / 45 | 45 / 45 | 62 s / 33 s | valid, $48 | valid, $53 | 4.0 s / 2.1 s |
| Wo Hop | 48 / 48, but five dishes read only as "Goon Bo", and others as plain "Beef" or "Squid" | 48 / 48, with full names ("Goon Bo w/Shrimp", "Beef w/Garlic Sauce") | 58 s / 33 s | valid, $85 | valid, $40 | 11 s / 1.7 s |

In both runs, every plan passed the checks on the first try.

**Safety checks after the fixes**

- No dish was offered to someone it is unsafe for. This was checked by script against the
  printed menus and the classic recipes.
- Shrimp versions are kept from the shellfish diner. Pork versions are kept from the
  vegetarian and the no-pork diner. Kung Pao is kept from the peanut diner, because the menu
  prints "Peanut" for the whole line.
- The tofu versions marked VP are offered to the vegetarian, with a question for the server:
  "order it vegetarian and ask whether it uses meat or meat stock".

**Where the model change mattered: hidden shellfish**

- 3.5 Flash Lite flagged hidden shellfish less often than 2.5 Flash. It missed shrimp in
  wonton soup and spring rolls, and oyster sauce on bok choy and Chinese broccoli.
- The code's own safety net now flags those dish types whatever the model says.
- Hunan Slurp's stir-fries are still less cautious with 3.5 Lite: the shellfish diner can eat
  35 of 36 dishes, against 27 with 2.5 Flash.

**Where the code change mattered**

- Choices now become separate dishes, and the menu's marks are read: V, VP, GF, GP and peppers.
  A printed "V" now counts as vegetarian (Hot & Sour Soup), unless the dish's own words
  say meat.
- "w/" is now read as "with". Before, "Hunan Wild Mushroom (w/ Pork Belly)" was treated as a
  choice of pork belly.
- Words for the choice no longer stay in the name of each version: the tofu version is
  "Yu Xiang (Tofu)", not "Yu Xiang Pork (Tofu)".

## Several pages as one menu: all 4 pages of Cafe Mandarin

The four page JPEGs were uploaded together (`images_base64`) and read in **one** vision call
with `google/gemini-3.5-flash-lite`. We then planned for the same tricky table at $40 a head.

| Run | Lines read / printed | Versions | Sections | Duplicates | Read + facts | Plan | Cost |
|---|---|---|---|---|---|---|---|
| 1 | 62 / 62 | 91 | 9, all correct | none | 40 s (facts for about 40 new names) | valid, 4 dishes, $78.66, 2.3 s | $0.049 |
| 2 (prompt reminder about per-dish surcharges) | 62 / 62 | 90 | 9 | none | 17 s (facts cached) | valid, 4 dishes, $79.93, 2.2 s | $0.024 |

**Model slips, and how the code now handles them.** The fixes were checked by running the
code on run 2's rows offline, with no new model calls. That gives 93 versions.

- In run 2, "Yu Xiang Pork" lost its pork option. A dish named after one protein now keeps
  that version, at the printed price.
- "Sesame Chicken or Tofu" and "General Tso's Chicken or Tofu" were not split in run 2. A name
  of the form "X Chicken or Tofu" is now split into two versions at the printed price.
- Mongolian (Beef) was read as $20; the menu prints $18 with no surcharge for beef. The
  protein in the dish's name now costs the printed price.

**Choice prices are now computed in code.** The photo step copies each dish's choice line
as printed ("Choice of Pork | Chicken | Beef +$2 | Shrimp +$4 | Tofu") and each option's own
surcharge. The app then prices each version as the base price plus that option's surcharge.
When the printed line is available it always wins, so a list with surcharges moved onto the
wrong options is repaired; one local import showed "Chicken $20, Beef $22, Shrimp $18".
Paired prices ("水煮牛 / 鱼 $24 / $28") become one version each. A fresh read of the 4 pages
is saved as `tests/fixtures/cafe_mandarin_4p_read.json` (one call, $0.021), and the tests
price every Main Classics version from it:

| Dish | Versions and prices |
|---|---|
| Yu Xiang | Pork $18, Chicken $18, Beef $20, Shrimp $22, Tofu $18 |
| Sesame | Chicken $18, Tofu $18 |
| General Tso's | Chicken $18, Tofu $18 |
| Kung Pao | Chicken $18, Beef $20, Shrimp $22, Tofu $18 |
| Chicken Broccoli | Chicken $18, Beef $20, Shrimp $22, Tofu $18 |
| Cumin | Lamb $18, Chicken $18, Beef $18, Shrimp $22, Tofu $18 |
| Mongolian | Chicken $18, Beef $18, Shrimp $22, Tofu $18 |
| Twice Cooked Pork Belly | $18 |
| Country Style Pork & Chili | $21 |
| Hunan Wild Mushroom (w/ Pork Belly) | $21 |
| Hunan Beef | $23 |
| Sichuan Boiled in Chili Oil (Chef's Recommendation) | Beef $24, Fish $28 |

**Safety:** no shrimp, wonton or shumai dish was offered to the shellfish diner. No meat was
offered to the vegetarian, except the VP lines with a server question; with the split, only
the tofu versions are offered. No pork was offered to the no-pork diner. Chicken Truffle Soup
Dumplings are offered to that diner only with the question "Is there any pork in it?". No
peanut dish was offered to the peanut diner.

Uploading the PDF itself gives the same 4 JPEG pages: the server renders it with
`pdftoppm`, so the server needs poppler-utils, which is now in the Dockerfile.


## Allergy-safety recheck (2026-10-09, evening)

This is the same tricky table (peanut / shellfish / vegetarian / no pork, $40 a head), on the
saved photo reads. Facts were asked again with the new rules: every allergen has to be
answered, and the description and variant are sent too. The table counts the dishes each
person can eat, out of all non-rice dishes. "Before" means the facts saved from the earlier
live run, checked with the old code. For Cafe Mandarin, that is the count logged at 08:35.

| Menu | Dishes | Alice (peanut) before → after | Sam (shellfish) | Ben (vegetarian) | Cai (no pork) | Plan after |
|---|---|---|---|---|---|---|
| Cafe Mandarin | 54 | 45 → 48 | 36 → 37 | 18 → 16 | 43 → 37 | valid, 4 dishes, $81.20 |
| Hunan Slurp | 35 | 34 → 34 | 34 → 34 | 6 → 5 | 21 → 19 | valid, 4 dishes, $98.96 |
| Hwa Yuan | 53 | 46 → 46 | 42 → 28 | 13 → 12 | 39 → 38 | valid, 5 dishes, $115.46 |
| Nom Wah | 48 | 46 → 48 | 28 → 25 | 13 → 11 | 31 → 32 | valid, 3 dishes, $29.05 |
| Shanghai 21 | 45 | 40 → not run | 38 → not run | 14 → not run | 26 → not run | not run (budget) |
| Wo Hop | 48 | 41 → not run | 28 → not run | 6 → not run | 38 → not run | not run (budget) |

The 4 menus that were run cost $0.130 in all (OpenRouter, `google/gemini-3.5-flash-lite`).
Facts took 21–32 s per menu and each plan about 2 s. Shanghai 21 and Wo Hop were skipped to
stay under the $0.15 cap.
