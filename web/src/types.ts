// Mirrors src/michelin/schemas.py and the wire types in api.py. Change those first.

export type EvidenceTier = "menu" | "inferred" | "unknown";

export type Allergen =
  | "shellfish"
  | "fish"
  | "peanut"
  | "tree_nut"
  | "egg"
  | "dairy"
  | "soy"
  | "wheat"
  | "sesame";

export type Diet = "vegetarian" | "vegan" | "no_pork" | "no_beef";

export interface IngredientClaim {
  name: string;
  tier: EvidenceTier;
  note?: string | null;
}

export interface AllergenFlag {
  allergen: Allergen;
  tier: EvidenceTier;
  confidence: number;
  reason: string;
}

export interface Dish {
  id: string;
  name_zh?: string | null;
  name_en?: string | null;
  price?: number | null;
  description_raw?: string | null;
  category: string;
  cooking_method?: string | null;
  spice_level: number | null;
  portion: string | null;
  main_ingredients: IngredientClaim[];
  allergens: AllergenFlag[];
  is_vegetarian: boolean | null;
  is_vegan: boolean | null;
  contains_pork: boolean | null;
  contains_beef: boolean | null;
  confirm_with_staff: string[];
}

export interface Menu {
  restaurant_id: string;
  restaurant_name: string;
  cuisine: string;
  source: string;
  preparation_mode?: "prepared_replay" | "live" | null;
  currency: string;
  verified: boolean;
  dishes: Dish[];
}

export interface MenuSummary {
  slug: string;
  restaurant_name: string;
  cuisine: string;
  verified: boolean;
  n_dishes: number;
}

export interface DinerProfile {
  id: string;
  name: string;
  allergies: Allergen[];
  diets: Diet[];
  /** Tastes and preferences in their own words; the AI reads it, the rules don't. */
  notes: string;
}

export interface PlanItem {
  dish_id: string;
  quantity: number;
  edible_by: string[];
  reason: string | null;
  server_question?: string | null; // AI plans: one question for the server, rule-checked
}

export interface Check {
  name: string;
  passed: boolean;
  detail: string;
}

export interface Plan {
  items: PlanItem[];
  subtotal: number;
  tax: number;
  tip: number;
  total: number;
  per_person: number;
  variety_score: number;
  checks: Check[];
  confirm_with_staff: string[];
  summary?: string | null;
}

export interface Relaxation {
  kind: "budget" | "allergy" | "diet" | "coverage" | string;
  description: string;
  diner_id: string | null;
  new_value: number | null;
}

export interface Conflict {
  code?: string;
  message: string;
  relaxations: Relaxation[];
}

export interface PlanRequest {
  menu_id: string;
  diner_ids?: string[];
  diners?: DinerProfile[];
  budget_per_person: number;
  budget_total?: number;
  tax_rate?: number;
  tip_rate?: number;
  locked_dish_ids?: string[];
  excluded_dish_ids?: string[];
  menu_override?: Menu;
  style_preference?: string;
  explain?: boolean;
}

/** AI single-dish swap: only that dish changes; "failed" offers the manual pick. */
export interface SwapResponse {
  kind: "plan" | "failed";
  plan?: Plan | null;
  new_dish_id?: string | null;
  message: string;
  source_note?: string | null;
}

export interface PlanResponse {
  kind: "plan" | "conflict";
  plan?: Plan | null;
  conflict?: Conflict | null;
  subtotal_cap: number;
  source?: "ai" | "rules" | "mock";
  source_note?: string | null;
}

export interface DiningSettings {
  budget: number;
  tax: number;
  tip: number;
  style: "balanced" | "lighter" | "favorites";
}

export interface DishEligibility {
  edible_by: string[];
  blocked_for: Record<string, string[]>;
  questions: string[];
  assessments?: Record<string, {status: "conflict" | "requires_confirmation" | "validated_under_known_data"; reasons: string[]}>;
}
export type Eligibility = Record<string, DishEligibility>;

export interface PreparedInput {
  menu_id: string; input_text: string; input_sha256: string; source_url: string;
  retrieved_at: string; preparation: string;
}
export interface ExtractionResponse {
  menu: Menu; provider: string; mode: "prepared_replay" | "live";
  input_sha256: string; source_url: string | null; retrieved_at: string | null; notice: string;
}
export interface ProfileSnapshot { profile: DinerProfile; revision: number; created_at?: string }
