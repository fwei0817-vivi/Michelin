import { ChevronDown, Users } from "lucide-react";
import { dinerSummary, dishName } from "../lib/format";
import { dishQuestions } from "../lib/dietary";
import type { DinerProfile, Menu, Plan } from "../types";
export function Coverage({ menu, plan, diners, minDishes }: { menu: Menu; plan: Plan; diners: DinerProfile[]; minDishes: number }) {
  const byId = Object.fromEntries(menu.dishes.map(d => [d.id, d]));
  const dishes = plan.items.filter(i => byId[i.dish_id] && byId[i.dish_id].category !== "staple");
  return <section className="coverage-section"><h3><Users size={17}/>A place for everyone</h3><p className="coverage-caption">Target: {minDishes} non-staple {minDishes === 1 ? "dish" : "dishes"} each. Based on recorded requirements.</p>
    <div className="coverage-list">{diners.map(p => { const matching = dishes.filter(i => i.edible_by.includes(p.id)); const pending = matching.filter(i => dishQuestions(byId[i.dish_id], diners).length > 0).length;
      return <details className="diner-row" key={p.id}><summary><span className="avatar">{p.name.charAt(0)}</span><span><strong>{p.name}</strong><small>{dinerSummary(p) || "No recorded restrictions"}</small></span><span className="diner-count">{matching.length} options<ChevronDown size={13}/></span></summary><div className="diner-detail">{pending > 0 && <p>{pending} {pending === 1 ? "option needs" : "options need"} a kitchen check.</p>}<ul>{matching.map(i => <li key={i.dish_id}>{dishName(byId[i.dish_id])}{dishQuestions(byId[i.dish_id], diners).length > 0 ? " · check ingredients" : ""}</li>)}</ul>{!matching.length && <p>No matching non-staple dishes.</p>}</div></details>;
    })}</div>
  </section>;
}
