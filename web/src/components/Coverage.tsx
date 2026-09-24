import { ChevronDown } from "lucide-react";
import { dinerSummary, dishName } from "../lib/format";
import { dishQuestions } from "../lib/dietary";
import type { DinerProfile, Menu, Plan } from "../types";

/** Per-person coverage: how many non-staple dishes each diner can eat by their recorded needs. */
export function Coverage({ menu, plan, diners, minDishes }: { menu: Menu; plan: Plan; diners: DinerProfile[]; minDishes: number }) {
  const byId = Object.fromEntries(menu.dishes.map((d) => [d.id, d]));
  const dishes = plan.items.filter((i) => byId[i.dish_id] && byId[i.dish_id].category !== "staple");
  return (
    <section className="sheet who" aria-labelledby="who-heading">
      <h2 id="who-heading">Who can eat what</h2>
      <p className="who-caption">
        Counted from recorded allergies and diets, rice and noodles not included. Everyone needs at least {minDishes}.
      </p>
      <ul className="who-list">
        {diners.map((p) => {
          const matching = dishes.filter((i) => i.edible_by.includes(p.id));
          // Only this diner's unknown allergens count here; the dish's own staff questions apply to everyone.
          const toCheck = new Set(matching.filter((i) => dishQuestions(byId[i.dish_id], [p]).length > 0).map((i) => i.dish_id));
          const short = matching.length < minDishes;
          return (
            <li key={p.id}>
              <details>
                <summary>
                  <span className="who-name">{p.name}</span>
                  <span className="who-needs">{dinerSummary(p) || "no restrictions recorded"}</span>
                  <span className={`who-count ${short ? "short" : ""}`}>
                    {matching.length} {matching.length === 1 ? "dish" : "dishes"}
                    <ChevronDown size={14} />
                  </span>
                </summary>
                <div className="who-detail">
                  {toCheck.size > 0 && (
                    <p>
                      {toCheck.size} of these {toCheck.size === 1 ? "needs" : "need"} a check with the kitchen.
                    </p>
                  )}
                  {matching.length ? (
                    <ul>
                      {matching.map((i) => (
                        <li key={i.dish_id}>
                          {dishName(byId[i.dish_id])}
                          {toCheck.has(i.dish_id) ? " (check ingredients)" : ""}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p>No matching dishes besides rice and noodles.</p>
                  )}
                </div>
              </details>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
