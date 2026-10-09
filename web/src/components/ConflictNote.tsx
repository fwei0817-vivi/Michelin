import { currencySymbol, money, subtotalCap } from "../lib/format";
import type { Conflict, DinerProfile, DiningSettings, Menu, Relaxation } from "../types";

interface Props {
  conflict: Conflict;
  menu: Menu;
  diners: DinerProfile[];
  settings: DiningSettings;
  onRelax: (r: Relaxation) => void;
}

const opensSettings = (r: Relaxation) => r.kind === "diet" || r.kind === "allergy";

/** Plain wording with formatted numbers for the relaxations we know; the backend text otherwise. */
function optionLabel(r: Relaxation, cur: string): string {
  if (r.kind === "budget" && r.new_value != null) return `Raise the budget to ${money(r.new_value, cur)} per person`;
  if (r.kind === "coverage" && r.new_value != null) return `Ask for ${r.new_value} ${r.new_value === 1 ? "dish" : "dishes"} per person instead`;
  return r.description;
}

export function ConflictNote({ conflict, menu, diners, settings, onRelax }: Props) {
  const cur = currencySymbol(menu.currency);
  const n = diners.length;
  const cap = subtotalCap(settings.budget, n, settings.tax, settings.tip);
  return (
    <section className="sheet conflict" aria-labelledby="conflict-heading">
      <h2 id="conflict-heading">No order fits yet</h2>
      <p className="conflict-context">
        {menu.restaurant_name}, {n} {n === 1 ? "diner" : "diners"} at {money(settings.budget, cur)} each with tax and tip, so about {money(cap, cur)} in
        menu prices for the table. Everyone needs {settings.minDishes} {settings.minDishes === 1 ? "dish" : "dishes"} they can eat.
      </p>
      <p className="conflict-message">{conflict.message}</p>
      {conflict.relaxations.length > 0 && (
        <>
          <h3>Change one thing</h3>
          <ul>
            {conflict.relaxations.map((r, i) => (
              <li key={i}>
                <button type="button" className="conflict-option" onClick={() => onRelax(r)}>
                  <span>
                    <strong>{optionLabel(r, cur)}</strong>
                    {opensSettings(r) && <small>Opens their settings so they decide.</small>}
                  </span>
                  <span>{opensSettings(r) ? "Open" : "Apply"}</span>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
