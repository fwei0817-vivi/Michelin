import { Plus, RefreshCw, UserPlus, X } from "lucide-react";
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
  saved: DinerProfile[];
  onPick: (d: DinerProfile) => void;
  onRemove?: (id: string) => void;
  settings: DiningSettings;
  currency: string;
  onChange: (s: DiningSettings) => void;
  onEdit: (d: DinerProfile) => void;
  onAdd: () => void;
  onPreset: (preset: string) => void;
  onPlan: () => void;
  loading: boolean;
  initial?: boolean;
  current?: boolean;
}

export function TableSetup({ diners, saved, onPick, onRemove, settings, currency, onChange, onEdit, onAdd, onPreset, onPlan, loading, initial = false, current = false }: Props) {
  const cur = currencySymbol(currency);
  const set = (key: keyof DiningSettings, value: number | string) => onChange({ ...settings, [key]: value });
  const valid =
    settings.budget >= 1 && settings.budget <= 500 &&
    settings.tax >= 0 && settings.tax <= 0.3 && settings.tip >= 0 && settings.tip <= 0.4;
  return (
    <div className="setup-content">
      <section className="setup-section" aria-labelledby="people-heading">
        <div className="setup-section-head">
          <h3 id="people-heading">
            Tonight <span>{diners.length} of 6</span>
          </h3>
          <select className="field preset" aria-label="Quick fill" value="" onChange={(e) => { if (e.target.value) onPreset(e.target.value); }}>
            <option value="">Quick fill…</option>
            <option value="saved">Sample group of six</option>
            <option value="two">Sample dinner for two</option>
            <option value="new">Clear tonight's table</option>
          </select>
        </div>
        <ul className="people-list">
          {diners.map((d, i) => (
            <li key={d.id} className="person-item">
              <button className="person-row" onClick={() => onEdit(d)} aria-label={`Edit ${d.name}`}>
                <span className="avatar">{d.name.charAt(0).toUpperCase() || i + 1}</span>
                <span className="person-text">
                  <strong>{d.name}</strong>
                  <small>{dinerSummary(d) || "No restrictions recorded"}</small>
                </span>
                <span className="person-edit">Edit</span>
              </button>
              {onRemove && (
                <button type="button" className="person-remove" onClick={() => onRemove(d.id)} aria-label={`${d.name} is not eating tonight`} title="Not eating tonight (stays saved)">
                  <X size={15} />
                </button>
              )}
            </li>
          ))}
        </ul>
        <button className="text-button add-person" onClick={onAdd} disabled={diners.length >= 6}>
          <Plus size={16} />
          Add a new person
        </button>
        {diners.length >= 6 && (
          <p className="helper" role="status">
            Six people is the most per table. Remove someone to add another.
          </p>
        )}
        {(() => {
          const others = saved.filter((s) => !diners.some((d) => d.id === s.id));
          if (!others.length) return null;
          return (
            <div className="saved-people">
              <p className="saved-people-head">Saved people · tap to add for tonight</p>
              <div className="saved-chips">
                {others.map((p) => (
                  <button key={p.id} type="button" className="saved-chip" disabled={diners.length >= 6} onClick={() => onPick(p)} title={dinerSummary(p) || "No restrictions recorded"}>
                    <UserPlus size={13} />
                    {p.name}
                  </button>
                ))}
              </div>
            </div>
          );
        })()}
      </section>

      <section className="setup-section" aria-labelledby="budget-heading">
        <h3 id="budget-heading">Budget and style</h3>
        <div className="field-row">
          <label className="field-label">
            Budget per person
            <span className="input-affix">
              <span aria-hidden="true">{cur.trim()}</span>
              <NumberField className="field" min={1} max={500} step={0.01} value={settings.budget} onChange={(n) => set("budget", n)} />
            </span>
            <small>Includes tax and tip; other fees unknown</small>
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
          Use a budget from 1–500, tax up to 30% and tip up to 40%.
        </p>
      )}
      {!diners.length && <p className="helper">Add at least one person to plan your meal.</p>}
      <div className="drawer-footer setup-footer">
        <p className="footer-total">
          <strong>{money(settings.budget, cur)}</strong> per person
          <small>{diners.length ? `${money(settings.budget * diners.length, cur)} for ${diners.length}, about ${money(subtotalCap(settings.budget, diners.length, settings.tax, settings.tip), cur)} in menu prices` : "Tax and tip included"}</small>
        </p>
        <button className="btn btn-primary" onClick={onPlan} disabled={loading || !diners.length || !valid}>
          <RefreshCw size={16} className={loading ? "spin" : ""} />
          {loading ? "Planning…" : current ? "See your dishes" : initial ? "Find dishes" : "Update dishes"}
        </button>
      </div>
    </div>
  );
}
