import type { DinerProfile, Dish } from "../types";
import { ALLERGEN_LABEL, avoidsHeat, listNames } from "./format";

// Which allergies and diets an ingredient word can matter to.
const CONCERN: [RegExp, string[]][] = [
  [/pork|lard|bacon|ham\b/i, ["no_pork", "vegetarian", "vegan"]],
  [/beef/i, ["no_beef", "vegetarian", "vegan"]],
  [/chicken|duck|lamb|meat|broth|stock|gelatin/i, ["vegetarian", "vegan"]],
  [/shrimp|prawn|crab|oyster|scallop|shellfish|lobster|clam|mussel/i, ["shellfish", "vegetarian", "vegan"]],
  [/fish|anchov/i, ["fish", "vegetarian", "vegan"]],
  [/egg/i, ["egg", "vegan"]],
  [/milk|butter|cream|cheese|dairy/i, ["dairy", "vegan"]],
  [/peanut/i, ["peanut"]],
  [/sesame/i, ["sesame"]],
  [/cashew|almond|walnut|pecan|pistachio|tree nut/i, ["tree_nut"]],
  [/soy|tofu/i, ["soy"]],
  [/wheat|flour|gluten|noodle/i, ["wheat"]],
];

/** The diners an ingredient (e.g. "pork fat", "bamboo shoots") matters to; [] for nobody. */
export function concernedBy(ingredient: string, diners: DinerProfile[]): DinerProfile[] {
  const tags = CONCERN.filter(([re]) => re.test(ingredient)).flatMap(([, t]) => t);
  return diners.filter(p => [...p.allergies, ...p.diets].some(t => tags.includes(t)));
}

/** Open questions are not confirmations. Keep them visible alongside eligibility, but only
 * the ones that matter to someone at this table ("uses bamboo shoots" asks nobody). */
export function dishQuestions(dish: Dish, diners: DinerProfile[]): string[] {
  const questions = dish.confirm_with_staff.filter(q => {
    const m = /uses (.+?)\.?$/.exec(q);
    return !m || !diners.length || concernedBy(m[1], diners).length > 0;
  });
  for (const flag of dish.allergens) {
    if (flag.tier !== "unknown") continue;
    const affected = diners.filter(p => p.allergies.includes(flag.allergen));
    const what = ALLERGEN_LABEL[flag.allergen].toLowerCase();
    // A sentence a diner could say to the server, not an internal note (QA r6).
    if (affected.length) questions.push(`${dish.name_en || dish.name_zh || "This dish"} (for ${affected.map(p => p.name).join(", ")}): Is there any ${what} in it, including the sauce, and is it kept apart from ${what}?`);
  }
  return [...new Set(questions)];
}

// Names that usually mean heat, for imported dishes with no recorded spice level.
const HOT_NAME = /chil(i|li)|spicy|hot (?!and sour)|sichuan|szechuan|kung ?pao|ma ?po|dan ?dan|ma ?la|numbing|麻辣|辣/i;

export function heatNote(dish: Dish, diners: DinerProfile[]): string | null {
  const likelyHot = dish.spice_level == null && HOT_NAME.test(`${dish.name_en ?? ""} ${dish.name_zh ?? ""} ${dish.description_raw ?? ""}`);
  const affected = diners.filter(p => avoidsHeat(p) && (dish.spice_level != null ? dish.spice_level >= 2 : likelyHot));
  if (!affected.length) return null;
  const names = listNames(affected.map(p => p.name));
  return dish.spice_level != null ? `Spicier than ${names} ${affected.length === 1 ? "prefers" : "prefer"}` : `Likely spicier than ${names} ${affected.length === 1 ? "prefers" : "prefer"}`;
}

// Ingredients that would break a vegetarian, no-pork or no-beef diet if the kitchen uses them.
const ANIMAL = /pork|lard|bacon|ham\b|beef|chicken|duck|meat|fish|anchov|shrimp|prawn|oyster|crab|broth|stock|gelatin|egg/i;

/** The dish may hide an animal ingredient (e.g. minced pork in yu-xiang eggplant, lard in a
 * pancake): a "Vegan"/"Matches all" chip must then say it still needs asking. */
export function mayHideMeat(dish: Dish): boolean {
  return dish.main_ingredients.some(i => i.tier !== "menu" && ANIMAL.test(i.name));
}
