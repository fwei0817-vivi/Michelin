/** Illustrative photos of similar dishes from Wikimedia Commons, keyed by Dish.id. They are not
 *  the restaurant's food and are never evidence of ingredients (docs/decisions.md). Files live in
 *  web/public/dishes/, cropped and resized; full credits in web/public/dishes/CREDITS.md. */
export type DishPhoto = { src: string; author: string; license: string; source: string };

const photo = (id: string, author: string, license: string, source: string): DishPhoto =>
  ({ src: `${import.meta.env.BASE_URL}dishes/${id}.webp`, author, license, source });

export const DISH_PHOTOS: Record<string, DishPhoto> = {
  garlic_pork_belly: photo("garlic_pork_belly", "Yunseul1118", "CC BY-SA 4.0", "https://commons.wikimedia.org/wiki/File:%E6%8B%9B%E7%89%8C%E8%92%9C%E6%B3%A5%E7%99%BD%E8%82%89.jpg"),
  mapo_tofu: photo("mapo_tofu", "Sichuanfoodlover", "CC BY-SA 4.0", "https://commons.wikimedia.org/wiki/File:Authentic_Mapo_Tofu.jpg"),
  yuxiang_shredded_pork: photo("yuxiang_shredded_pork", "Дмитрий Журавлев (dejur)", "CC BY-SA 3.0", "https://commons.wikimedia.org/wiki/File:%E9%B1%BC%E9%A6%99%E8%82%89%E4%B8%9D.jpg"),
  kung_pao_chicken: photo("kung_pao_chicken", "Steven G. Johnson", "CC BY-SA 3.0", "https://commons.wikimedia.org/wiki/File:Kung-pao-shanghai.jpg"),
  dry_fried_string_beans: photo("dry_fried_string_beans", "Andy Li", "CC0", "https://commons.wikimedia.org/wiki/File:Sichuan-style-dried_fried_Green_Beans_with_Minced_Pork_-_Aberdeen_Seafood,_Brighton_2026-07-19.jpg"),
  garlic_seasonal_greens: photo("garlic_seasonal_greens", "lazy fri13th", "CC BY 2.0", "https://commons.wikimedia.org/wiki/File:Garlic_gai-lan_stir-fry.jpg"),
  di_san_xian: photo("di_san_xian", "1700-talet", "CC BY 3.0", "https://commons.wikimedia.org/wiki/File:Di_san_xian_(home-made).jpg"),
  dry_pot_cauliflower: photo("dry_pot_cauliflower", "Tbatb", "CC BY-SA 4.0", "https://commons.wikimedia.org/wiki/File:Stir-fried_Cauliflower.jpg"),
  boiled_fish_chili_oil: photo("boiled_fish_chili_oil", "我乃野云鹤", "CC BY-SA 4.0", "https://commons.wikimedia.org/wiki/File:Sliced_Fish_in_Hot_Chili_Oil.jpg"),
  hot_and_sour_soup: photo("hot_and_sour_soup", "Evan-Amos", "Public domain", "https://commons.wikimedia.org/wiki/File:Hot-and-Sour-Soup-Bowl.jpg"),
  dan_dan_noodles: photo("dan_dan_noodles", "Daderot", "CC0", "https://commons.wikimedia.org/wiki/File:Dan_dan_noodles_-_Pasadena,_CA.jpg"),
  steamed_rice: photo("steamed_rice", "Douglas Perkins", "CC0", "https://commons.wikimedia.org/wiki/File:A_bowl_of_rice.jpg"),
};

/** Same-style dishes on other menus share an illustration, matched on the printed name. */
const BY_NAME: [RegExp, string][] = [
  [/ma ?po|麻婆/i, "mapo_tofu"],
  [/kung ?pao|gong ?bao|宫保/i, "kung_pao_chicken"],
  [/dan ?dan|担担/i, "dan_dan_noodles"],
  [/(string|green) beans?|四季豆|干煸豆角/i, "dry_fried_string_beans"],
  [/hot (and|&) sour soup|酸辣汤/i, "hot_and_sour_soup"],
  [/di ?san ?xian|地三鲜/i, "di_san_xian"],
  [/cauliflower|花菜|菜花/i, "dry_pot_cauliflower"],
  [/(fish|tilapia).*(chili|chilli|hot|spicy|sichuan)|boiled fish|水煮鱼/i, "boiled_fish_chili_oil"],
  [/pork belly.*garlic|garlic.*pork belly|蒜泥白肉/i, "garlic_pork_belly"],
  [/yu ?xiang|fish[- ]fragrant|鱼香肉丝/i, "yuxiang_shredded_pork"],
  [/(white|steamed) rice|米饭/i, "steamed_rice"],
  [/garlic.*(greens|choy|broccoli|pea shoots?|spinach|gai ?lan)|(greens|bok choy|pea shoots?).*garlic/i, "garlic_seasonal_greens"],
];

export function photoFor(dish: { id: string; name_en?: string | null; name_zh?: string | null }): DishPhoto | undefined {
  if (DISH_PHOTOS[dish.id]) return DISH_PHOTOS[dish.id];
  const text = `${dish.name_en ?? ""} ${dish.name_zh ?? ""}`;
  const hit = BY_NAME.find(([re]) => re.test(text));
  return hit ? DISH_PHOTOS[hit[1]] : undefined;
}
