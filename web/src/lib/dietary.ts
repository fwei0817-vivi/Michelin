import type { DinerProfile, Dish } from "../types";
import { ALLERGEN_LABEL, listNames } from "./format";

/** Open questions are not confirmations. Keep them visible alongside eligibility. */
export function dishQuestions(dish: Dish, diners: DinerProfile[]): string[] {
  const questions = [...dish.confirm_with_staff];
  for (const flag of dish.allergens) {
    if (flag.tier !== "unknown") continue;
    const affected = diners.filter(p => p.allergies.includes(flag.allergen));
    if (affected.length) questions.push(`Confirm ${ALLERGEN_LABEL[flag.allergen]} with the kitchen for ${affected.map(p => p.name).join(", ")}: ${flag.reason}`);
  }
  return [...new Set(questions)];
}

export function heatNote(dish: Dish, diners: DinerProfile[]): string | null {
  const affected = diners.filter(p => p.max_spice != null && dish.spice_level > p.max_spice);
  return affected.length ? `Spicier than ${listNames(affected.map(p => p.name))} ${affected.length === 1 ? "prefers" : "prefer"}` : null;
}
