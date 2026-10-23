import { ChevronDown } from "lucide-react";
import { dinerSummary, dishName } from "../lib/format";
import type { DinerProfile, Menu, Plan } from "../types";

/** Per-person coverage: how many non-staple dishes each diner can eat by their recorded needs. */
export function Coverage({ menu, plan, diners }: { menu: Menu; plan: Plan; diners: DinerProfile[] }) {
  const byId = Object.fromEntries(menu.dishes.map((d) => [d.id, d]));
  const dishes = plan.items.filter((i) => byId[i.dish_id] && byId[i.dish_id].category !== "staple");
  return (
    <section className="sheet who" aria-labelledby="who-heading">
      <h2 id="who-heading">Who can eat what</h2>
      <p className="who-caption">
        Counted from recorded allergies and diets; dishes too spicy for someone who avoids heat are counted apart. Plain rice is not counted; fried rice and noodle dishes are.
      </p>
      <ul className="who-list">
        {diners.map((p) => {
          // QA r18: read only the backend's per-diner status ("ok" / "needs_confirm" / "no")
          const allowed = dishes.filter((i) => ["ok", "needs_confirm"].includes(i.status?.[p.id]?.status ?? "no"));
          // allergies and diets decide "can eat"; a too-spicy dish is shown apart (2026-10-10)
          const tooHot = allowed.filter((i) => i.status?.[p.id]?.taste === "too_spicy");
          const matching = allowed.filter((i) => i.status?.[p.id]?.taste !== "too_spicy");
          const toCheck = new Set(matching.filter((i) => i.status?.[p.id]?.status === "needs_confirm").map((i) => i.dish_id));
          const sure = matching.length - toCheck.size;
          const short = sure < 1; // no dish without asking the server (QA r18)
          return (
            <li key={p.id}>
              <details>
                <summary>
                  <span className="who-name">{p.name}</span>
                  <span className="who-needs">{dinerSummary(p) || "no restrictions recorded"}</span>
                  <span className={`who-count ${short ? "short" : ""}`}>
                    {sure} {sure === 1 ? "dish" : "dishes"}{toCheck.size > 0 ? ` + ${toCheck.size} to confirm` : ""}{tooHot.length > 0 ? ` + ${tooHot.length} too spicy` : ""}
                    <ChevronDown size={14} />
                  </span>
                </summary>
                <div className="who-detail">
                  {toCheck.size > 0 && (
                    <p>
                      {toCheck.size === matching.length
                        ? `${matching.length === 1 ? "This dish needs" : "All of these need"} a check with the server first.`
                        : `${toCheck.size} of these ${toCheck.size === 1 ? "needs" : "need"} a check with the server first.`}
                    </p>
                  )}
                  {matching.length ? (
                    <ul>
                      {matching.map((i) => (
                        <li key={i.dish_id}>
                          {dishName(byId[i.dish_id])}
                          {toCheck.has(i.dish_id) ? " (ask the server first)" : ""}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p>No matching dishes besides plain rice.</p>
                  )}
                  {tooHot.length > 0 && (
                    <p>Too spicy for {p.name}: {tooHot.map((i) => dishName(byId[i.dish_id])).join(", ")}.</p>
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
