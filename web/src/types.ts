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
  spice_level: number;
  portion: string;
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
  max_spice: number | null;
  dislikes: string[];
  likes: string[];
}

export interface PlanItem {
  dish_id: string;
  quantity: number;
  edible_by: string[];
  reason: string | null;
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
}

export interface Relaxation {
  kind: "budget" | "allergy" | "diet" | "coverage" | "portions" | string;
  description: string;
  diner_id: string | null;
  new_value: number | null;
}

export interface Conflict {
  message: string;
  relaxations: Relaxation[];
}

export interface PlanRequest {
  menu_id: string;
  diner_ids?: string[];
  diners?: DinerProfile[];
  budget_per_person: number;
  tax_rate?: number;
  tip_rate?: number;
  min_dishes_per_person?: number;
  locked_dish_ids?: string[];
  excluded_dish_ids?: string[];
  menu_override?: Menu;
  dish_count_target?: number;
  style_preference?: string;
  explain?: boolean;
}

export interface PlanResponse {
  kind: "plan" | "conflict";
  plan?: Plan | null;
  conflict?: Conflict | null;
  subtotal_cap: number;
}

export interface DiningSettings {
  budget: number;
  tax: number;
  tip: number;
  minDishes: number;
  dishCount: number;
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
