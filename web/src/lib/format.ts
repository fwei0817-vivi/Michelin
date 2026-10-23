import type { Allergen, AllergenFlag, Diet, DinerProfile, Dish, Preference } from "../types";

export const ALLERGENS: Allergen[] = [
  "peanut",
  "tree_nut",
  "shellfish",
  "fish",
  "egg",
  "dairy",
  "soy",
  "wheat",
  "sesame",
];

export const ALLERGEN_LABEL: Record<Allergen, string> = {
  shellfish: "shellfish",
  fish: "fish",
  peanut: "peanuts",
  tree_nut: "tree nuts",
  egg: "egg",
  dairy: "milk",
  soy: "soy",
  wheat: "wheat",
  sesame: "sesame",
};

export const DIETS: Diet[] = ["vegetarian", "vegan", "no_pork", "no_beef"];

export const DIET_LABEL: Record<Diet, string> = {
  vegetarian: "vegetarian",
  vegan: "vegan",
  no_pork: "no pork",
  no_beef: "no beef",
};


export const PREFERENCES: Preference[] = ["no_spicy", "mild", "loves_spicy", "likes_seafood", "likes_meat", "light", "no_offal"];
export const SPICE_PREFS: Preference[] = ["no_spicy", "mild", "loves_spicy"]; // pick at most one

export const PREFERENCE_LABEL: Record<Preference, string> = {
  no_spicy: "No spicy",
  mild: "Mild",
  loves_spicy: "Loves spicy",
  likes_seafood: "Likes seafood",
  likes_meat: "Likes meat",
  light: "Light / 清淡",
  no_offal: "No offal / 内脏",
};

/** "Mango " -> "mango"; same cleaning as the server. */
export function cleanTerm(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9 '\-]+/g, " ").replace(/\s+/g, " ").trim().slice(0, 40).trim();
}

export function money(n: number | null | undefined, currency = "$"): string {
  if (n == null) return "—";
  return `${currency}${n.toFixed(2)}`;
}

export function subtotalCap(budget: number, n: number, tax: number, tip: number): number {
  return (budget * n) / (1 + tax + tip);
}

/** "peanuts, on the menu" / "pork, usually" / "shellfish? ask" — the evidence tier in plain words. */
export function flagWording(f: AllergenFlag): string {
  const label = ALLERGEN_LABEL[f.allergen] ?? f.allergen;
  if (f.tier === "menu") return `${label}, on the menu`;
  if (f.tier === "inferred") return `${label}, usually`;
  return `${label}? ask`;
}

export function dietWording(d: Dish): string | null {
  if (d.is_vegan === true) return "vegan";
  if (d.is_vegetarian === true) return "vegetarian";
  if (d.is_vegetarian === null) return "vegetarian? ask";
  return null;
}

/** Short restriction summary for a diner chip: "vegetarian, no shellfish, no fish". */
export function dinerSummary(p: DinerProfile): string {
  const parts = [
    ...p.diets.map((d) => DIET_LABEL[d]),
    ...(p.other_diets ?? []),
    ...p.allergies.map((a) => `no ${ALLERGEN_LABEL[a]}`),
    ...(p.other_allergies ?? []).map((a) => `no ${a}`),
  ];
  if (avoidsHeat(p)) parts.push("no heat");
  return parts.join(", ");
}

/** The diner's own note says they avoid spicy food ("no spicy food", "mild only"). */
export function avoidsHeat(p: DinerProfile): boolean {
  if (p.preferences?.some((x) => x === "no_spicy" || x === "mild")) return true;
  return /\b(no|not|avoids?|hates?|without|can't|cannot|don't)\b[^.;]*\b(spic|heat|hot|chil)|\bmild\b/i.test(p.notes ?? "");
}

/** "David", "David and Tom", "David, Amy and Tom". */
export function listNames(names: string[]): string {
  if (names.length <= 1) return names.join("");
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

export const MARK_LABEL: Record<string, { short: string; title: string }> = {
  vegetarian: { short: "V", title: "The menu marks it vegetarian" },
  vegan: { short: "Vegan", title: "The menu marks it vegan" },
  vegetarian_possible: { short: "VP", title: "The menu says it can be made vegetarian: order it that way and ask" },
  gluten_free: { short: "GF", title: "The menu marks it gluten free (shown only; a wheat allergy still asks)" },
  gluten_free_possible: { short: "GP", title: "The menu says it can be made gluten free" },
};

/** "Menu: VP, GF": the marks printed next to the dish. */
export function markWording(d: Dish): string | null {
  const marks = (d.menu_marks ?? []).map((m) => MARK_LABEL[m]?.short ?? m);
  return marks.length ? `Menu: ${marks.join(", ")}` : null;
}

/** Versions of one printed line ("Kung Pao (Chicken)", "Kung Pao (Tofu)") side by side,
 * where the first of them falls; everything else keeps its order. */
export function groupFamilies<T extends Dish>(dishes: T[]): T[] {
  const out: T[] = [];
  const done = new Set<string>();
  for (const d of dishes) {
    if (!d.family_id) { out.push(d); continue; }
    if (done.has(d.family_id)) continue;
    done.add(d.family_id);
    out.push(...dishes.filter((x) => x.family_id === d.family_id));
  }
  return out;
}

/** "Kung Pao (Tofu)" and its siblings on this menu. */
export function siblings(d: Dish, dishes: Dish[]): Dish[] {
  return d.family_id ? dishes.filter((x) => x.family_id === d.family_id && x.id !== d.id) : [];
}

export function dishName(d: Dish): string {
  return d.name_en || d.id.replaceAll("_", " ");
}

export function slug(s: string): string {
  return s
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "") || `diner_${Date.now()}`;
}

export function splitList(s: string): string[] {
  return s
    .split(/[,，、]/)
    .map((x) => x.trim())
    .filter(Boolean);
}

export const CATEGORY_LABEL: Record<string, string> = {
  cold_appetizer: "Cold dishes", stir_fry: "From the wok", braise_or_stew: "Braises & stews",
  soup: "Soup", staple: "Rice & noodles", dessert: "Dessert", drink: "Drinks", other: "Other",
};
/** Short pass / fail labels for Plan.checks. Allergy and diet wording stays at "recorded": a pass
 *  means no recorded conflict, never that a dish is free of something. */
export function checkLabel(name: string, passed: boolean): string {
  const labels: Record<string, [string, string]> = {
    allergies: ["No recorded allergy conflicts", "Allergy conflict"],
    diets: ["Recorded diets met", "Diet conflict"],
    coverage: ["Each diner has a dish (see who can eat what)", "Someone has nothing to eat"], // Ticket uses coverageLabel (QA r18)
    budget: ["Within budget", "Over budget"],
    enough: ["Enough food for everyone", "Not enough food for everyone"],
    ai: ["Menu ids and safety rules verified", "AI choice failed the checks"],
  };
  return labels[name]?.[passed ? 0 : 1] ?? name;
}
export const currencySymbol = (currency: string) => currency === "USD" ? "$" : currency === "CNY" ? "¥" : `${currency} `;

const KEEP_CAPS = new Set(["BBQ", "XO", "NYC", "USA", "UK", "LA", "NY", "II", "III"]);

/** "SKY PAVILION 天阁" -> "Sky Pavilion 天阁"; names that are not all caps stay as typed. */
export function niceName(name: string): string {
  const letters = name.match(/[A-Za-z]/g) ?? [];
  if (letters.length < 4 || letters.some((c) => c !== c.toUpperCase())) return name;
  return name.replace(/[A-Za-z][A-Za-z']*/g, (w) => (KEEP_CAPS.has(w) ? w : w[0] + w.slice(1).toLowerCase()));
}
