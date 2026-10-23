import type { DinerProfile, DinerStatusMap, Dish, VegTag } from "../types";
import { ALLERGEN_LABEL, avoidsHeat, listNames } from "./format";

import KEYWORDS from "./keywords.json";

// The one shared keyword list (src/michelin/data/keywords.json; this copy is kept identical by
// tests/test_keywords.py): squid is shellfish, satay peanut, soy sauce soy and wheat, 五花肉 pork.
type Entry = { en?: string[]; zh?: string[]; negatable?: boolean };
const NOT = "(?<!no )(?<!w/o )(?<!without )(?<!vegetarian )(?<!vegan )(?<!mock )(?<!faux )(?<!imitation )";
export function keyword(concept: string): RegExp {
  const e = (KEYWORDS as unknown as Record<string, Entry>)[concept];
  const parts: string[] = [];
  if (e.en?.length) parts.push(`${e.negatable ? NOT : ""}\\b(?:${e.en.join("|")})\\b`);
  if (e.zh?.length) parts.push(e.zh.join("|"));
  return new RegExp(parts.join("|"), "i");
}
const VEG = ["vegetarian", "vegan"];
// Which allergies and diets an ingredient word can matter to.
const CONCERN: [RegExp, string[]][] = [
  [keyword("pork"), ["no_pork", ...VEG]],
  [keyword("beef"), ["no_beef", ...VEG]],
  [keyword("meat"), VEG],
  [keyword("stock"), VEG],
  [keyword("shellfish"), ["shellfish", ...VEG]],
  [keyword("fish"), ["fish", ...VEG]],
  [keyword("egg"), ["egg", "vegan"]],
  [keyword("dairy"), ["dairy", "vegan"]],
  [keyword("peanut"), ["peanut"]],
  [keyword("sesame"), ["sesame"]],
  [keyword("tree_nut"), ["tree_nut"]],
  [keyword("soy"), ["soy"]],
  [keyword("wheat"), ["wheat"]],
  [/tree nut/i, ["tree_nut"]],
  [/dairy/i, ["dairy", "vegan"]],
  [/noodle/i, ["wheat"]],
];

/** The diners an ingredient (e.g. "pork fat", "bamboo shoots") matters to; [] for nobody. */
export function concernedBy(ingredient: string, diners: DinerProfile[]): DinerProfile[] {
  const tags = CONCERN.filter(([re]) => re.test(ingredient)).flatMap(([, t]) => t);
  const low = ingredient.toLowerCase();
  return diners.filter(p => [...p.allergies, ...p.diets].some(t => tags.includes(t)) || (p.other_allergies ?? []).some(t => low.includes(t)));
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
/** The vegetarian/vegan tag, decided by the backend (veg_tag, QA r16): no keyword guessing
 * here, and another diner's halal or allergy check never turns it into "Ask". */
export function vegTag(tag: VegTag | null | undefined): { label: string; ask: boolean } | null {
  if (!tag) return null;
  const ask = tag.startsWith("ask_");
  const diet = tag.replace("ask_", "");
  return { label: ask ? `Ask if ${diet}` : diet === "vegan" ? "Vegan" : "Vegetarian", ask };
}
export function fitsChip(n: number, unsure: boolean): string {
  return unsure ? `Fits all ${n} only if the server confirms` : `Matches all ${n}`;
}

/** "Only if the server confirms": read from the backend's per-diner status only (QA r15). */
export function needsConfirm(status: DinerStatusMap | undefined, dinerIds: string[]): boolean {
  return dinerIds.some((id) => status?.[id]?.status === "needs_confirm");
}
