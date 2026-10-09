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
| `cafe-mandarin.jpg` | Cafe Mandarin, 1st Ave at 67th St | Sichuan / Chinese-American | Upper East Side | <https://cafemandarinnyc.com/wp-content/uploads/2026/07/Menu0707.pdf> | 45 | **Real menu**: pages 1–2 of the restaurant's PDF |
| `cafe-mandarin.pdf` | Cafe Mandarin | | | same as above | 74 (4 pages) | **Original PDF** for reference. The app's photo step takes images only, so upload the JPG. |
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

## Results from the live run (2026-10-09)

These results used gemini-2.5-flash, $40 per person, and the four-person table above.

| Menu | Dishes read / in image | Plan | Notes |
|---|---|---|---|
| Nom Wah | 48 / 49 | valid | Before the fix, the 40-dish cap silently dropped dishes. The menu has no plain rice, and before the fix that meant there was no plan at all. |
| Cafe Mandarin | 35 / 45 | valid | 10 dishes were missed on the dense two-page scan. The restaurant name was not printed. Hot & Sour Soup is marked "V" on the menu, but the app treats it as possible pork (stricter than it needs to be). |
| Hwa Yuan | 53 / 53 | valid | Before the fix, the dishes above 40 were cut off and there was no plan without rice. "Chinese Eggplant in Garlic Sauce with Pork" was offered to the vegetarian and the no-pork diner (fixed). |
| Shanghai 21 | 45 / 45 | valid | Before the fix, the dishes above 40 were cut off. |
| Hunan Slurp | 36 / 36 | valid | "Soft Tofu" is printed as "Pork and bean paste bolognese…" but was offered to the vegetarian and the no-pork diner (fixed). |
| Wo Hop | 48 / 48 | valid | Goon Bo dishes are correctly kept away from the peanut diner. |
