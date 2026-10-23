import { photoFor, type DishPhotoInput } from "./dishPhotos";

let fails = 0;
function eq(a: unknown, b: unknown, what: string) {
  if (JSON.stringify(a) !== JSON.stringify(b)) { fails++; console.error("FAIL", what, a, "!=", b); } else console.log("ok", what);
}

function shown(dish: DishPhotoInput): string | null {
  const src = photoFor(dish)?.src ?? "";
  const m = src.match(/dishes\/([a-z0-9_]+)\.webp$/);
  return m?.[1] ?? null;
}

function d(name_en: string, extra: Partial<DishPhotoInput> = {}): DishPhotoInput {
  return { id: "x", name_en, ...extra };
}

const yx = "yuxiang_shredded_pork";
const kp = "kung_pao_chicken";
const cases: [string, DishPhotoInput, string | null][] = [
  ["Yu Xiang Eggplant", d("Yu Xiang Eggplant", { name_zh: "鱼香茄子", menu_marks: ["vegetarian"], is_vegetarian: true }), null],
  ["Fish-Fragrant Eggplant", d("Fish-Fragrant Eggplant", { name_zh: "鱼香茄子" }), null],
  ["鱼香茄子 alone", { id: "x", name_zh: "鱼香茄子" }, null],
  ["Yu Xiang Pork", d("Yu Xiang Pork"), yx],
  ["Yu Xiang Shredded Pork", d("Yu Xiang Shredded Pork", { name_zh: "鱼香肉丝" }), yx],
  ["鱼香肉丝", { id: "x", name_zh: "鱼香肉丝" }, yx],
  ["魚香肉絲", { id: "x", name_zh: "魚香肉絲" }, yx],
  ["fish-fragrant shredded pork", d("Fish-Fragrant Shredded Pork"), yx],
  ["Shredded Pork in Garlic Sauce is 鱼香肉丝", d("Shredded Pork in Garlic Sauce", { name_zh: "鱼香肉丝" }), yx],
  ["Yu Xiang (Pork)", d("Yu Xiang (Pork)", { variant: "Pork", name_zh: "猪肉", menu_marks: ["vegetarian_possible"] }), yx],
  ["Yu Xiang (Chicken)", d("Yu Xiang (Chicken)", { variant: "Chicken", name_zh: "鸡" }), null],
  ["Yu Xiang (Beef)", d("Yu Xiang (Beef)", { variant: "Beef", name_zh: "牛" }), null],
  ["Yu Xiang (Shrimp)", d("Yu Xiang (Shrimp)", { variant: "Shrimp", name_zh: "虾" }), null],
  ["Yu Xiang (Tofu)", d("Yu Xiang (Tofu)", { variant: "Tofu", name_zh: "豆腐", family_name: "Yu Xiang Pork" }), null],
  ["family line Yu Xiang Pork is not the version", d("Yu Xiang", { family_name: "Yu Xiang Pork" }), null],
  ["Yu Xiang Pork marked vegetarian", d("Yu Xiang Pork", { is_vegetarian: true }), null],
  ["Kung Pao Tofu", d("Kung Pao Tofu", { name_zh: "宫保豆腐" }), null],
  ["Kung Pao Shrimp", d("Kung Pao Shrimp", { id: "kung_pao_shrimp", name_zh: "宫保虾仁" }), null],
  ["Kung Pao (Beef)", d("Kung Pao (Beef)", { variant: "Beef", name_zh: "宫保（牛）" }), null],
  ["Kung Pao (Shrimp)", d("Kung Pao (Shrimp)", { variant: "Shrimp" }), null],
  ["Kung Pao (Tofu)", d("Kung Pao (Tofu)", { variant: "Tofu", name_zh: "宫保（豆腐）", family_name: "Kung Pao Chicken" }), null],
  ["variant Tofu overrides a chicken name", d("Kung Pao Chicken", { variant: "Tofu" }), null],
  ["family line Kung Pao Chicken is not the version", d("Kung Pao", { family_name: "Kung Pao Chicken" }), null],
  ["Kung Pao Chicken", d("Kung Pao Chicken", { name_zh: "宫保鸡丁" }), kp],
  ["Kung Pao Chicken (Spicy)", d("Kung Pao Chicken (Spicy)", { id: "kung_pao_chicken_spicy" }), kp],
  ["Kung Pao (Chicken)", d("Kung Pao (Chicken)", { variant: "Chicken", name_zh: "宫保（鸡）", menu_marks: ["vegetarian_possible"] }), kp],
  ["Gong Bao Chicken", d("Gong Bao Chicken"), kp],
  ["宫保鸡丁", { id: "x", name_zh: "宫保鸡丁" }, kp],
  ["宮保雞丁", { id: "x", name_zh: "宮保雞丁" }, kp],
  ["Mongolian (Chicken)", d("Mongolian (Chicken)", { variant: "Chicken", family_name: "Mongolian Beef" }), null],
  ["Mapo Tofu", d("Mapo Tofu", { name_zh: "麻婆豆腐" }), "mapo_tofu"],
  ["Mapo Tofu marked vegetarian", d("Mapo Tofu", { name_zh: "麻婆豆腐", menu_marks: ["vegetarian"], is_vegetarian: true }), "mapo_tofu"],
  ["Ma Po Tofu", d("Ma Po Tofu"), "mapo_tofu"],
  ["麻婆茄子", d("Mapo Eggplant", { name_zh: "麻婆茄子" }), null],
  ["Dan Dan Noodles", d("Dan Dan Noodles", { name_zh: "担担面" }), "dan_dan_noodles"],
  ["Dan Dan Noodle", d("Dan Dan Noodle", { name_zh: "会稽山担担面" }), "dan_dan_noodles"],
  ["vegetarian Dan Dan Noodles", d("Dan Dan Noodles", { menu_marks: ["vegetarian"] }), null],
  ["Hot and Sour Soup", d("Hot and Sour Soup", { name_zh: "酸辣汤" }), "hot_and_sour_soup"],
  ["Hot & Sour Soup", d("Hot & Sour Soup", { name_zh: "酸辣汤" }), "hot_and_sour_soup"],
  ["Steamed Rice", d("Steamed Rice", { name_zh: "白饭" }), "steamed_rice"],
  ["White Rice", d("White Rice"), "steamed_rice"],
  ["Steamed White Rice", d("Steamed White Rice"), "steamed_rice"],
  ["Eight Treasure Sticky Rice", d("Eight Treasure Sticky Rice", { name_zh: "八宝糯米饭" }), null],
  ["Vegetable Fried Rice", d("Vegetable Fried Rice", { name_zh: "炒饭" }), null],
  ["Dry-Fried String Beans", d("Dry-Fried String Beans", { name_zh: "干煸四季豆" }), "dry_fried_string_beans"],
  ["string beans with pork", d("String Beans with Minced Pork"), "dry_fried_string_beans"],
  ["sautéed string beans flagged pork", d("Sautéed String Beans", { contains_pork: true }), "dry_fried_string_beans"],
  ["sautéed string beans, pork unknown", d("Sautéed String Beans"), null],
  ["vegetarian dry-fried string beans", d("Wok Fried String Bean", { name_zh: "干煸四季豆", menu_marks: ["vegetarian"] }), null],
  ["eggplants and string beans", d("Eggplants and String Beans", { name_zh: "四川双素" }), null],
  ["string beans with no pork", d("Stir-Fried String Beans", { contains_pork: false, name_zh: "干煸四季豆" }), null],
  ["Boiled Fish in Chili Oil", d("Boiled Fish in Chili Oil", { name_zh: "水煮鱼" }), "boiled_fish_chili_oil"],
  ["Fish Filet in Chili Oil", d("Fish Filet in Chili Oil", { name_zh: "江北水煮鱼" }), "boiled_fish_chili_oil"],
  ["Fluke Fish Filet (Hunan Fermented Chili)", d("Fluke Fish Filet (Hunan Fermented Chili)", { variant: "Hunan Fermented Chili", name_zh: "龙利鱼片" }), null],
  ["Spicy Fish Fillets", d("Spicy Fish Fillets", { name_zh: "香辣鱼片" }), null],
  ["Sichuan Boiled Beef in Chili Oil", d("Sichuan Boiled Beef in Chili Oil", { name_zh: "水煮牛" }), null],
  ["boiled fish variant beef", d("Boiled Fish in Chili Oil", { variant: "Beef" }), null],
  ["Garlic Seasonal Greens", d("Garlic Seasonal Greens", { name_zh: "蒜蓉时蔬" }), "garlic_seasonal_greens"],
  ["Bok Choy with Garlic", d("Bok Choy with Garlic"), "garlic_seasonal_greens"],
  ["Beef with Garlic Broccoli", d("Beef with Garlic Broccoli"), null],
  ["鱼香芥兰 is not garlic greens or yu xiang pork", d("Broccoli with Garlic Sauce", { name_zh: "鱼香芥兰" }), null],
  ["cauliflower stir fry", d("Organic Cauliflower Stir Fry", { name_zh: "清炒花菜", menu_marks: ["vegetarian"] }), "dry_pot_cauliflower"],
  ["cauliflower with pork belly", d("Wok Organic Cauliflower with Pork Belly", { name_zh: "干锅花菜" }), null],
  ["Dry Pot Cauliflower", d("Dry Pot Cauliflower", { name_zh: "干锅花菜" }), "dry_pot_cauliflower"],
  ["garlic pork belly", d("Sliced Pork Belly in Garlic Sauce", { name_zh: "蒜泥白肉" }), "garlic_pork_belly"],
  ["地三鲜", d("Sautéed Potato, Green Pepper & Eggplant", { name_zh: "地三鲜" }), "di_san_xian"],
];

for (const [what, dish, expect] of cases) eq(shown(dish), expect, what);

const sampleIds = [
  "garlic_pork_belly", "mapo_tofu", "yuxiang_shredded_pork", "kung_pao_chicken",
  "dry_fried_string_beans", "garlic_seasonal_greens", "di_san_xian", "dry_pot_cauliflower",
  "boiled_fish_chili_oil", "hot_and_sour_soup", "dan_dan_noodles", "steamed_rice",
];
for (const id of sampleIds) eq(shown({ id, name_en: "not the dish in the photo" }), id, `sample id ${id}`);

if (fails) throw new Error(`${fails} photoFor test(s) failed`);
