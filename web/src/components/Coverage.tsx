import { Check, ChevronDown, Users } from "lucide-react";
import { dinerSummary, dishName } from "../lib/format";
import type { DinerProfile, Menu, Plan } from "../types";
export function Coverage({ menu, plan, diners, minDishes }: { menu: Menu; plan: Plan; diners: DinerProfile[]; minDishes: number }) {
  const byId = Object.fromEntries(menu.dishes.map(d => [d.id, d]));
  const dishes = plan.items.filter(i => byId[i.dish_id]?.category !== "staple");
  return <section className="coverage-section"><div className="coverage-heading"><div><div className="section-label"><Users size={15}/>A PLACE FOR EVERYONE</div><h2>Who eats what</h2></div><p>At least {minDishes} dishes each, excluding staples.</p></div>
    <div className="coverage-grid">{diners.map(p => { const can = dishes.filter(i => i.edible_by.includes(p.id)); const met = can.length >= minDishes;
      return <article className="coverage-card" key={p.id}><div className="coverage-card-top"><span className="avatar">{p.name.charAt(0).toUpperCase()}</span><span className={`coverage-badge ${met ? "met" : ""}`}>{met && <Check size={12}/>} {can.length}/{dishes.length} dishes</span></div><h3>{p.name}</h3><p>{dinerSummary(p) || "No recorded restrictions"}</p><div className="coverage-progress" aria-hidden="true">{dishes.map(i => <span key={i.dish_id} className={i.edible_by.includes(p.id) ? "filled" : ""}/>)}</div><details><summary>View {p.name}'s dishes <ChevronDown size={13}/></summary><ul>{can.map(i => <li key={i.dish_id}>{byId[i.dish_id] ? dishName(byId[i.dish_id]) : i.dish_id}</li>)}</ul>{!can.length && <p>No eligible non-staple dishes.</p>}</details></article>;
    })}</div></section>;
}
