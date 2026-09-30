import { Plus, RefreshCw } from "lucide-react";
import { currencySymbol, dinerSummary, money, subtotalCap } from "../lib/format";
import type { DinerProfile, DiningSettings } from "../types";
import { NumberField } from "./NumberField";

const STYLES = [
  ["balanced", "Varied", "A mix of ingredients and cooking methods."],
  ["lighter", "Less fried", "More vegetables, fewer fried dishes."],
  ["favorites", "Favorites", "Extra weight on everyone's likes."],
] as const;
const pct = (x: number) => `${Number((x * 100).toFixed(3))}%`;

interface Props {
  diners: DinerProfile[];
  settings: DiningSettings;
  currency: string;
  onChange: (s: DiningSettings) => void;
  onEdit: (d: DinerProfile) => void;
  onAdd: () => void;
  onPreset: (preset: string) => void;
  onPlan: () => void;
  loading: boolean;
  initial?: boolean;
}

export function TableSetup({ diners, settings, currency, onChange, onEdit, onAdd, onPreset, onPlan, loading, initial = false }: Props) {
  const cur = currencySymbol(currency);
  const set = (key: keyof DiningSettings, value: number | string) => onChange({ ...settings, [key]: value });
  const valid =
    settings.budget >= 1 && settings.budget <= 500 &&
    Number.isInteger(settings.minDishes) && settings.minDishes >= 1 && settings.minDishes <= 10 &&
    Number.isInteger(settings.dishCount) && settings.dishCount >= 1 && settings.dishCount <= 20 &&
    settings.tax >= 0 && settings.tax <= 0.3 && settings.tip >= 0 && settings.tip <= 0.4;
  return (
    <div className="setup-content">
      <section className="setup-section" aria-labelledby="people-heading">
        <div className="setup-section-head">
          <h3 id="people-heading">
            People <span>{diners.length}</span>
          </h3>
          <select className="field preset" aria-label="Load a group" value="" onChange={(e) => { if (e.target.value) onPreset(e.target.value); }}>
            <option value="">Load a group…</option>
            <option value="synthetic-three">Three synthetic diners (no restrictions)</option>
            <option value="saved">Example group</option>
            <option value="two">Example dinner for two</option>
            <option value="new">Start empty</option>
          </select>
        </div>
        <ul className="people-list">
          {diners.map((d, i) => (
            <li key={d.id}>
              <button className="person-row" onClick={() => onEdit(d)} aria-label={`Edit ${d.name}`}>
                <span className="avatar">{d.name.charAt(0).toUpperCase() || i + 1}</span>
                <span className="person-text">
                  <strong>{d.name}</strong>
                  <small>{dinerSummary(d) || "No restrictions recorded"}</small>
                </span>
                <span className="person-edit">Edit</span>
              </button>
            </li>
          ))}
        </ul>
        <button className="text-button add-person" onClick={onAdd}>
          <Plus size={16} />
          Add a person
        </button>
      </section>

      <section className="setup-section" aria-labelledby="budget-heading">
        <h3 id="budget-heading">Budget and dishes</h3>
        <div className="field-row">
          <label className="field-label">
            Budget per person
            <span className="input-affix">
              <span aria-hidden="true">{cur.trim()}</span>
              <NumberField className="field" min={1} max={500} step={1} value={settings.budget} onChange={(n) => set("budget", n)} />
            </span>
            <small>Tax and tip included</small>
          </label>
          <label className="field-label">
            Dishes to order
            <NumberField className="field" min={1} max={20} step={1} inputMode="numeric" value={settings.dishCount} onChange={(n) => set("dishCount", n)} />
            <small>A target, rice included</small>
          </label>
          <label className="field-label">
            Dishes each person can eat
            <NumberField className="field" min={1} max={10} step={1} inputMode="numeric" value={settings.minDishes} onChange={(n) => set("minDishes", n)} />
            <small>At least; rice and noodles don't count</small>
          </label>
        </div>
        <div className="field-label style-label" id="style-label">
          Style
        </div>
        <div className="segmented" role="group" aria-labelledby="style-label">
          {STYLES.map(([id, name]) => (
            <button key={id} aria-pressed={settings.style === id} className={settings.style === id ? "selected" : ""} onClick={() => set("style", id)}>
              {name}
            </button>
          ))}
        </div>
        <p className="helper style-hint">{STYLES.find((s) => s[0] === settings.style)?.[2]}</p>
        <details className="tax-settings">
          <summary>
            Tax {pct(settings.tax)} · tip {pct(settings.tip)}
          </summary>
          <div className="field-grid">
            <label className="field-label">
              Sales tax (%)
              <NumberField className="field" min={0} max={30} step={0.125} value={Number((settings.tax * 100).toFixed(3))} onChange={(n) => set("tax", n / 100)} />
            </label>
            <label className="field-label">
              Tip (%)
              <NumberField className="field" min={0} max={40} step={1} value={Number((settings.tip * 100).toFixed(3))} onChange={(n) => set("tip", n / 100)} />
            </label>
          </div>
        </details>
      </section>

      {!valid && (
        <p className="field-error" role="status">
          Use a budget from 1–500, 1–20 whole dishes, a minimum of 1–10 dishes, tax up to 30% and tip up to 40%.
        </p>
      )}
      {!diners.length && <p className="helper">Add at least one person to plan your meal.</p>}
      <div className="drawer-footer setup-footer">
        <p className="footer-total">
          <strong>{money(settings.budget * diners.length, cur)}</strong> for the table
          <small>About {money(subtotalCap(settings.budget, diners.length, settings.tax, settings.tip), cur)} in menu prices</small>
        </p>
        <button className="btn btn-primary" onClick={onPlan} disabled={loading || !diners.length || !valid}>
          <RefreshCw size={16} className={loading ? "spin" : ""} />
          {loading ? "Planning…" : initial ? "Find dishes" : "Update dishes"}
        </button>
      </div>
    </div>
  );
}
