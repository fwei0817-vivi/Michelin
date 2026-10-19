/** Illustrative photos from Wikimedia Commons. They are not the restaurant's food and are never
 *  evidence of ingredients (docs/decisions.md). Files live in web/public/dishes/; credits in
 *  web/public/dishes/CREDITS.md.
 *
 *  A photo is used only when the dish is the one in the picture, including its main ingredient.
 *  `family_name` is the printed line ("Yu Xiang Pork") and can name a different version's
 *  protein, so it is ignored. `variant` ("Tofu", "Chicken") wins when it names one protein.
 *  Known sample ids still map even if the printed name would not. */
export type DishPhoto = { src: string; author: string; license: string; source: string };

export type DishPhotoInput = {
  id: string;
  name_en?: string | null;
  name_zh?: string | null;
  /** The chosen version: "Chicken", "Tofu", "Pork", or a preparation such as "Spicy". */
  variant?: string | null;
  /** Printed line for a choice family. Not read: it can name a protein this version is not. */
  family_name?: string | null;
  is_vegetarian?: boolean | null;
  is_vegan?: boolean | null;
  contains_pork?: boolean | null;
  contains_beef?: boolean | null;
  menu_marks?: readonly string[] | null;
};

const assetBase = import.meta.env?.BASE_URL || "/";
const photo = (id: string, author: string, license: string, source: string): DishPhoto =>
  ({ src: `${assetBase}dishes/${id}.webp`, author, license, source });

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

const SIMPLIFIED: Record<string, string> = {
  魚: "鱼", 雞: "鸡", 鷄: "鸡", 蝦: "虾", 麵: "面", 麪: "面", 絲: "丝",
  擔: "担", 湯: "汤", 飯: "饭", 蘭: "兰", 乾: "干", 鍋: "锅", 宮: "宫",
  葉: "叶", 鴨: "鸭", 紅: "红", 東: "东", 會: "会",
};

function normalize(raw: string): string {
  let out = "";
  for (const ch of raw) out += SIMPLIFIED[ch] ?? ch;
  return out.toLowerCase();
}

/** Proteins named in a label. "Fish-fragrant" / 鱼香 is a sauce, not fish. Beef is removed
 *  before 肉丝 so 牛肉丝 is beef only. */
function proteinsOf(raw: string): string[] {
  let text = normalize(raw).replace(/fish[-\s]?fragrant/g, " ").replace(/鱼香/g, " ");
  const rules: [string, RegExp][] = [
    ["eggplant", /eggplants?|茄子/],
    ["tofu", /\btofu\b|豆腐/],
    ["shrimp", /\bshrimps?\b|\bprawns?\b|虾/],
    ["chicken", /\bchickens?\b|鸡(?!蛋)/],
    ["beef", /\bbeef\b|牛肉|牛(?!奶|油)/],
    ["pork", /\bpork\b|猪肉|肉丝|肉末|五花|白肉/],
    ["lamb", /\blamb\b|羊肉/],
    ["duck", /\bducks?\b|鸭/],
    ["fish", /\bfish\b|鱼/],
    ["vegetable", /\bvegetables?\b/],
  ];
  const found: string[] = [];
  for (const [name, re] of rules) {
    if (!re.test(text)) continue;
    found.push(name);
    text = text.replace(new RegExp(re.source, "g"), " ");
  }
  return found;
}

function markedVegetarian(dish: DishPhotoInput): boolean {
  if (dish.is_vegetarian === true || dish.is_vegan === true) return true;
  return (dish.menu_marks ?? []).some((mark) => mark === "vegetarian" || mark === "vegan");
}

/** Variant ("Tofu") or a single "(Chicken)" / "（鸡）" is this version's protein. A style
 *  note such as "(Spicy)" is not, so the rest of the name is scanned. */
function dishProteins(dish: DishPhotoInput): string[] {
  const fromVariant = proteinsOf(dish.variant ?? "");
  if (fromVariant.length === 1) return fromVariant;
  const name = `${dish.name_en ?? ""} ${dish.name_zh ?? ""}`;
  const groups = [...name.matchAll(/[（(]([^）)]+)[）)]/g)].map((m) => proteinsOf(m[1]));
  const hits = groups.filter((ps) => ps.length > 0);
  if (hits.length === 1 && hits[0].length === 1) return hits[0];
  return proteinsOf(name);
}

function hasMeatProtein(dish: DishPhotoInput): boolean {
  if (dish.contains_pork === true || dish.contains_beef === true) return true;
  return dishProteins(dish).some((p) => p !== "vegetable" && p !== "eggplant");
}

type Rule = (dish: DishPhotoInput, text: string) => boolean;

// Mapo tofu, including vegetarian mapo. The photo is the tofu dish. Mapo eggplant is not.
const mapo: Rule = (dish, text) => {
  if (!/ma[\s-]*po|麻婆/.test(text) || !/\btofu\b|豆腐/.test(text)) return false;
  return dishProteins(dish).every((p) => p === "tofu" || p === "pork" || p === "beef");
};

// Kung Pao chicken (宫保鸡丁) only. Tofu, shrimp, beef and the rest get no photo.
const kungPao: Rule = (dish, text) => {
  if (markedVegetarian(dish) || !/kung[\s-]*pao|gong[\s-]*bao|宫保/.test(text)) return false;
  const proteins = dishProteins(dish);
  return proteins.length === 1 && proteins[0] === "chicken";
};

// Dan dan noodles. The photo shows minced meat, so a vegetarian bowl gets none.
const danDan: Rule = (dish, text) => {
  if (markedVegetarian(dish)) return false;
  return /dan[\s-]*dan|担担/.test(text) && /noodles?|面/.test(text);
};

// Dry-fried string beans with minced pork. Vegetarian beans, or beans with another
// main (eggplant, chicken), are a different dish. Dry-fried / 干煸 is that pork dish
// unless the menu marks it vegetarian or says it has no pork.
const stringBeans: Rule = (dish, text) => {
  if (!/(?:string|green)\s*beans?|四季豆|干煸豆角/.test(text)) return false;
  if (markedVegetarian(dish) || dish.contains_pork === false) return false;
  const proteins = dishProteins(dish);
  if (proteins.some((p) => p !== "pork")) return false;
  if (proteins.includes("pork") || dish.contains_pork === true) return true;
  return /dry[-\s]?fried|干煸/.test(text);
};

// The photo is the bowl of soup; pork in the recipe does not make it a different dish.
const hotAndSour: Rule = (dish, text) =>
  /hot\s+(?:and|&)\s+sour\s+soup|酸辣汤/.test(text + normalize(dish.name_zh ?? ""));

// Potato, eggplant and pepper. A meat or tofu version is not the photo.
const diSanXian: Rule = (dish, text) => {
  if (!/di[\s-]*san[\s-]*xian|地三鲜/.test(text)) return false;
  const blocked = ["pork", "chicken", "beef", "shrimp", "fish", "lamb", "duck", "tofu"];
  return !dishProteins(dish).some((p) => blocked.includes(p));
};

// Plain stir-fried cauliflower. Pork belly, beef, or another main is a different dish.
const cauliflower: Rule = (dish, text) => {
  if (!/cauliflower|花菜|菜花/.test(text)) return false;
  if (dish.contains_pork === true || dish.contains_beef === true) return false;
  return dishProteins(dish).every((p) => p === "vegetable");
};

// Boiled fish in chili oil (水煮鱼), not any spicy fish and not boiled beef.
const boiledFish: Rule = (dish, text) => {
  if (markedVegetarian(dish)) return false;
  const style = /水煮鱼|boiled\s+fish|fish(?:\s+(?:filets?|fillets?))?\s+in\s+(?:hot\s+)?(?:chilli|chili)\s+oil/;
  if (!style.test(text)) return false;
  const proteins = dishProteins(dish);
  return proteins.length === 0 || (proteins.length === 1 && proteins[0] === "fish");
};

const garlicPorkBelly: Rule = (dish, text) => {
  if (markedVegetarian(dish)) return false;
  return /pork\s+belly.*garlic|garlic.*pork\s+belly|蒜泥白肉/.test(text);
};

// Yu xiang / fish-fragrant shredded pork (鱼香肉丝) only. Eggplant, chicken, beef,
// shrimp and tofu share the sauce name and get no photo.
const yuXiang: Rule = (dish, text) => {
  if (markedVegetarian(dish) || dish.contains_pork === false) return false;
  if (!/yu[\s-]*xiang|fish[-\s]?fragrant|鱼香/.test(text)) return false;
  const proteins = dishProteins(dish);
  return proteins.length === 1 && proteins[0] === "pork";
};

const steamedRice: Rule = (dish, text) => {
  if (/fried|sticky|glutinous|noodles?|cakes?|rolls?|risotto|porridge|congee|糯|炒饭|肠粉|糕|粽/.test(text)) return false;
  // A choice of protein ("Fried Rice" is already excluded) means this is not plain rice.
  if (dishProteins(dish).some((p) => p !== "vegetable")) return false;
  return /(?:white|steamed)\s+rice|白米饭|白饭|米饭/.test(text);
};

// Garlic gai lan and the same plain garlic greens. Not a meat dish that mentions
// garlic and a vegetable, and not fish-fragrant (鱼香) greens.
const garlicGreens: Rule = (dish, text) => {
  if (/鱼香|yu[\s-]*xiang|fish[-\s]?fragrant/.test(text) || hasMeatProtein(dish)) return false;
  return /garlic.*(?:greens|choy|broccoli|pea\s*shoots?|spinach|gai[\s-]*lan)|(?:greens|bok\s*choy|pea\s*shoots?).*garlic|蒜蓉(?:青菜|菜心|芥兰|时蔬|菠菜|西兰花)/.test(text);
};

const BY_NAME: [Rule, string][] = [
  [mapo, "mapo_tofu"],
  [kungPao, "kung_pao_chicken"],
  [danDan, "dan_dan_noodles"],
  [stringBeans, "dry_fried_string_beans"],
  [hotAndSour, "hot_and_sour_soup"],
  [diSanXian, "di_san_xian"],
  [cauliflower, "dry_pot_cauliflower"],
  [boiledFish, "boiled_fish_chili_oil"],
  [garlicPorkBelly, "garlic_pork_belly"],
  [yuXiang, "yuxiang_shredded_pork"],
  [steamedRice, "steamed_rice"],
  [garlicGreens, "garlic_seasonal_greens"],
];

export function photoFor(dish: DishPhotoInput): DishPhoto | undefined {
  const known = DISH_PHOTOS[dish.id];
  if (known) return known;
  const text = normalize(`${dish.name_en ?? ""} ${dish.name_zh ?? ""} ${dish.variant ?? ""}`);
  const hit = BY_NAME.find(([test]) => test(dish, text));
  return hit ? DISH_PHOTOS[hit[1]] : undefined;
}
