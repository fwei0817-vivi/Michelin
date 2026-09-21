import type { Allergen, AllergenFlag, Diet, DinerProfile, Dish } from "../types";

export const ALLERGENS: Allergen[] = [
  "shellfish",
  "fish",
  "peanut",
  "tree_nut",
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
  dairy: "dairy",
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

export const SPICE_LABEL = ["no heat", "mild", "medium", "hot"];

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
    ...p.allergies.map((a) => `no ${ALLERGEN_LABEL[a]}`),
  ];
  if (p.max_spice === 0) parts.push("no heat");
  return parts.join(", ");
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
export const currencySymbol = (currency: string) => currency === "USD" ? "$" : currency === "CNY" ? "¥" : `${currency} `;
