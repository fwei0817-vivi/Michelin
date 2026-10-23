import { useState } from "react";
import { Save } from "lucide-react";
import { CATEGORY_LABEL, dishName } from "../lib/format";
import type { Dish } from "../types";
import { Sheet } from "./Sheet";

const BLANK = { spice_level: null, portion: null, main_ingredients: [], allergens: [], is_vegetarian: null, is_vegan: null, contains_pork: null, contains_beef: null, confirm_with_staff: [] };

/** A menu row is only what the menu prints: name, price and category. Likely ingredients and
 * allergens come from the AI when the menu is checked, so they are not edited here. */
export function DishEditor({ dish, onSave, onClose }: { dish?: Dish; onSave: (d: Dish) => void; onClose: () => void }) {
  const [draft, setDraft] = useState<Dish>(dish ?? { id: `dish_${crypto.randomUUID()}`, name_en: "", price: null, category: "other", ...BLANK });
  const set = (key: keyof Dish, value: unknown) => setDraft(prev => ({ ...prev, [key]: value }));
  const renamed = !dish || dish.name_en?.trim() !== draft.name_en?.trim() || dish.category !== draft.category;
  return <Sheet title={dish ? `Edit ${dishName(dish)}` : "Add a dish"} onClose={onClose}><form className="editor-form" onSubmit={e => { e.preventDefault(); onSave({ ...draft, name_en: draft.name_en?.trim(), ...(renamed ? BLANK : {}) }); }}>
    <label className="field-label">English dish name<input className="field" required value={draft.name_en ?? ""} onChange={e => set("name_en", e.target.value)}/></label>
    <div className="field-grid"><label className="field-label">Menu price<input className="field" required type="number" min="0" step="0.01" value={draft.price ?? ""} onChange={e => set("price", e.target.value === "" ? null : Number(e.target.value))}/></label><label className="field-label">Category<select className="field" value={draft.category} onChange={e => set("category", e.target.value)}>{Object.entries(CATEGORY_LABEL).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label></div>
    <p className="helper">Only the name, price and category come from the menu. The AI works out likely ingredients and allergens from the name; anything uncertain becomes a question for your server.</p>
    <button className="btn btn-primary w-full" type="submit" disabled={!draft.name_en?.trim() || draft.price == null}><Save size={16}/>Save dish for review</button>
  </form></Sheet>;
}
