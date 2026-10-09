import type { DinerProfile, Dish } from "../types";
import { ALLERGEN_LABEL, listNames } from "./format";

/** Open questions are not confirmations. Keep them visible alongside eligibility. */
export function dishQuestions(dish: Dish, diners: DinerProfile[]): string[] {
  const questions = [...dish.confirm_with_staff];
  if (dish.spice_level == null && diners.some(p => p.max_spice != null)) questions.push("Spice level unknown; confirm with staff.");
  for (const flag of dish.allergens) {
    if (flag.tier !== "unknown") continue;
    const affected = diners.filter(p => p.allergies.includes(flag.allergen));
    if (affected.length) questions.push(`Confirm ${ALLERGEN_LABEL[flag.allergen]} with the kitchen for ${affected.map(p => p.name).join(", ")}: ${flag.reason}`);
  }
  return [...new Set(questions)];
}

// Names that usually mean heat, for imported dishes with no recorded spice level.
const HOT_NAME = /chil(i|li)|spicy|hot (?!and sour)|sichuan|szechuan|kung ?pao|ma ?po|dan ?dan|ma ?la|numbing|麻辣|辣/i;

export function heatNote(dish: Dish, diners: DinerProfile[]): string | null {
  const likelyHot = dish.spice_level == null && HOT_NAME.test(`${dish.name_en ?? ""} ${dish.name_zh ?? ""} ${dish.description_raw ?? ""}`);
  const affected = diners.filter(p => p.max_spice != null && (dish.spice_level != null ? dish.spice_level > p.max_spice : likelyHot && p.max_spice < 2));
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
