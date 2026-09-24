import { Check, Leaf, Plus, RefreshCw, SlidersHorizontal, Sparkles, UserRound, Users } from "lucide-react";
import { currencySymbol, dinerSummary, money, subtotalCap } from "../lib/format";
import type { DinerProfile, DiningSettings } from "../types";

export function TableSetup({ diners, settings, currency, onChange, onEdit, onAdd, onPreset, onPlan, loading, initial = false }: {
  diners: DinerProfile[]; settings: DiningSettings; currency: string;
  onChange: (s: DiningSettings) => void; onEdit: (d: DinerProfile) => void; onAdd: () => void;
  onPreset: (preset: string) => void; onPlan: () => void; loading: boolean; initial?: boolean;
}) {
  const cur = currencySymbol(currency);
  const set = (key: keyof DiningSettings, value: number | string) => onChange({ ...settings, [key]: value });
  const valid = settings.budget >= 1 && settings.budget <= 500 && Number.isInteger(settings.minDishes) && settings.minDishes >= 1 && settings.minDishes <= 10 && Number.isInteger(settings.dishCount) && settings.dishCount >= 1 && settings.dishCount <= 20 && settings.tax >= 0 && settings.tax <= .3 && settings.tip >= 0 && settings.tip <= .4;
  return <div className="setup-content">
    <div className="section-label"><Users size={15}/>THE PARTY<span>{diners.length} DINERS</span></div>
    <label className="field-label">Start with a group<select className="field" value="" onChange={e => { if (e.target.value) onPreset(e.target.value); }}><option value="">Choose a group…</option><option value="saved">Example group</option><option value="two">Example dinner for two</option><option value="new">Create my own group</option></select></label>
    <div className="party-list">{diners.map((d, i) => <button key={d.id} className="party-member" onClick={() => onEdit(d)}><span className="avatar">{d.name.charAt(0).toUpperCase() || i + 1}</span><span><strong>{d.name}</strong><small>{dinerSummary(d) || "No recorded restrictions"}</small></span><span className="edit-word">Edit</span></button>)}</div>
    <button className="btn btn-outline w-full" onClick={onAdd}><Plus size={16}/>Add a diner</button>
    <div className="section-label section-gap"><SlidersHorizontal size={15}/>TABLE PREFERENCES</div>
    <div className="field-grid"><label className="field-label">Budget per person ({currency})<input className="field" type="number" min="1" max="500" step="1" value={settings.budget} onChange={e => set("budget", Number(e.target.value))}/><small>Tax and tip included</small></label>
      <label className="field-label">Target courses<input className="field" type="number" min="1" max="20" value={settings.dishCount} onChange={e => set("dishCount", Number(e.target.value))}/><small>A preference, including staples</small></label></div>
    <label className="field-label mt-4">Minimum dishes per diner<input className="field" type="number" min="1" max="10" value={settings.minDishes} onChange={e => set("minDishes", Number(e.target.value))}/><small>A requirement, excluding rice and noodles</small></label>
    <div className="field-label mt-5">Dining style</div><div className="style-options">{([
      ["balanced", "Varied table", "A mix of ingredients and cooking styles.", Sparkles],
      ["lighter", "Less fried", "Favor vegetables and fewer fried dishes.", Leaf],
      ["favorites", "Personal favorites", "Give extra weight to everyone's likes.", UserRound],
    ] as const).map(([id, name, detail, Icon]) => <button key={id} aria-pressed={settings.style === id} className={`style-option ${settings.style === id ? "selected" : ""}`} onClick={() => set("style", id)}><Icon size={18}/><span><strong>{name}</strong><small>{detail}</small></span>{settings.style === id && <Check size={16}/>}</button>)}</div>
    <details className="tax-settings"><summary>Tax & tip</summary><div className="field-grid mt-3"><label className="field-label">Sales tax (%)<input className="field" type="number" min="0" max="30" step="0.125" value={Number((settings.tax * 100).toFixed(3))} onChange={e => set("tax", Number(e.target.value) / 100)}/></label><label className="field-label">Tip (%)<input className="field" type="number" min="0" max="40" value={Number((settings.tip * 100).toFixed(3))} onChange={e => set("tip", Number(e.target.value) / 100)}/></label></div></details>
    <div className="budget-note"><div><span>Table budget</span><strong>{money(settings.budget * diners.length, cur)}</strong></div><small>About {money(subtotalCap(settings.budget, diners.length, settings.tax, settings.tip), cur)} in menu prices.</small></div>
    {!valid && <p className="field-error" role="status">Use a budget from 1–500, 1–20 whole dishes, a minimum of 1–10 dishes, tax up to 30% and tip up to 40%.</p>}
    {!diners.length && <p className="helper">Add at least one diner to plan your meal.</p>}
    <div className="drawer-footer"><button className="btn btn-primary w-full" onClick={onPlan} disabled={loading || !diners.length || !valid}><RefreshCw size={16} className={loading ? "spin" : ""}/>{loading ? "Planning the table…" : initial ? "Find dishes for our table" : "Update our table"}</button></div>
  </div>;
}
