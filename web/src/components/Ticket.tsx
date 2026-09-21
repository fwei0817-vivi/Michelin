import { useState } from "react";
import { ArrowLeftRight, Check, CheckCircle2, CircleHelp, Flame, Leaf, LockKeyhole, Plus, RefreshCw, Trash2, UnlockKeyhole, Users, Utensils } from "lucide-react";
import { CATEGORY_LABEL, currencySymbol, dishName, flagWording, money } from "../lib/format";
import type { DinerProfile, DiningSettings, Menu, Plan } from "../types";

export function Ticket({ menu, plan, diners, settings, locked, stale, loading, onLock, onSwap, onRemove, onAdd, onPlan }: {
  menu: Menu; plan: Plan; diners: DinerProfile[]; settings: DiningSettings; locked: string[];
  stale: boolean; loading: boolean; onLock: (id: string) => void; onSwap: (id: string) => void;
  onRemove: (id: string) => void; onAdd: () => void; onPlan: () => void;
}) {
  const [filter, setFilter] = useState("all");
  const [ticked, setTicked] = useState<string[]>([]);
  const byId = Object.fromEntries(menu.dishes.map(d => [d.id, d]));
  const items = plan.items.filter(i => byId[i.dish_id]);
  const cur = currencySymbol(menu.currency);
  const n = diners.length;
  const remaining = settings.budget * n - plan.total;
  const categories = [...new Set(items.map(i => byId[i.dish_id].category))];
  const actualFilter = filter === "all" || categories.includes(filter) ? filter : "all";
  const visible = items.filter(i => actualFilter === "all" || byId[i.dish_id].category === actualFilter);
  const failed = plan.checks.filter(c => !c.passed);
  const nonStaples = items.filter(i => byId[i.dish_id].category !== "staple");
  const covered = diners.filter(d => nonStaples.filter(i => i.edible_by.includes(d.id)).length >= settings.minDishes).length;
  const tableAllergies = new Set(diners.flatMap(d => d.allergies));
  return <div className="dashboard" aria-busy={loading}>
    <section className="overview" aria-label="Table overview">
      <div className="overview-heading"><div><div className="eyebrow">TABLE ORDER <span>· {n} DINERS</span></div><h1>Your table, planned.</h1></div><button className="btn btn-primary" onClick={onPlan} disabled={loading}><RefreshCw size={16} className={loading ? "spin" : ""}/>{loading ? "Replanning…" : "Replan table"}</button></div>
      <p className="plan-rationale">{items.length} courses with {nonStaples.filter(i => byId[i.dish_id].is_vegetarian === true).length} vegetarian options. {covered} of {n} diners meet the minimum of {settings.minDishes} non-staple dishes.{plan.confirm_with_staff.length > 0 && ` ${plan.confirm_with_staff.length} questions to check with staff.`}</p>
      <div className="metrics"><div className="metric"><span>TABLE TOTAL</span><strong>{money(plan.total, cur)}<small> / {money(settings.budget * n, cur)}</small></strong><p className={remaining < 0 ? "metric-warning" : ""}>{remaining >= 0 ? `${money(remaining, cur)} left in budget` : `${money(-remaining, cur)} over budget`}</p></div>
        <div className="metric"><span>PER PERSON</span><strong>{money(plan.per_person, cur)}</strong><p>Includes tax & tip</p></div>
        <div className="metric"><span>ON THE TABLE</span><strong>{items.length}<small> courses / {settings.dishCount} target</small></strong><p>{categories.length} categories · {items.reduce((sum, i) => sum + i.quantity, 0)} servings</p></div>
        <div className="metric"><span>DINER COVERAGE</span><strong>{covered}<small> / {n} diners</small></strong><p>{stale ? "From the previous plan" : `At least ${settings.minDishes} dishes each`}</p></div></div>
      <div className="overview-foot"><span><Utensils size={13}/>Variety {Math.round(plan.variety_score * 100)}/100<span className="muted-dot">·</span>Categories, ingredients & methods</span><details><summary>Cost breakdown</summary><dl><dt>Menu subtotal</dt><dd>{money(plan.subtotal, cur)}</dd><dt>Sales tax</dt><dd>{money(plan.tax, cur)}</dd><dt>Tip</dt><dd>{money(plan.tip, cur)}</dd></dl></details></div>
    </section>
    {failed.length > 0 && <div className="notice error-notice" role="status"><CircleHelp size={18}/><div>{failed.map(c => <p key={c.name}>{c.detail}</p>)}</div></div>}
    <div className="courses-toolbar"><div className="course-tabs" role="group" aria-label="Filter recommended courses"><button className={actualFilter === "all" ? "active" : ""} aria-pressed={actualFilter === "all"} onClick={() => setFilter("all")}>All courses <span>{items.length}</span></button>{categories.map(c => <button key={c} aria-pressed={actualFilter === c} className={actualFilter === c ? "active" : ""} onClick={() => setFilter(c)}>{CATEGORY_LABEL[c] ?? c}<span>{items.filter(i => byId[i.dish_id].category === c).length}</span></button>)}</div><span className="courses-hint">Keep your favorites. Make it your table.</span></div>
    <div className="dish-grid">{visible.map(item => {
      const d = byId[item.dish_id]; const kept = locked.includes(d.id);
      const notFor = diners.filter(p => !item.edible_by.includes(p.id)).map(p => p.name);
      const pending = d.confirm_with_staff.length > 0 || d.allergens.some(f => f.tier === "unknown" && tableAllergies.has(f.allergen));
      return <article key={d.id} className={`dish-card ${kept ? "dish-kept" : ""}`} aria-label={dishName(d)}>
        <div className="dish-card-heading"><span className="dish-number">{String(items.findIndex(i => i.dish_id === d.id) + 1).padStart(2, "0")}</span><h3>{dishName(d)}</h3><div className="dish-price">{money((d.price ?? 0) * item.quantity, cur)}{item.quantity > 1 && <small>{item.quantity} × {money(d.price, cur)}</small>}</div></div>
        <div className="dish-tags"><span>{CATEGORY_LABEL[d.category] ?? d.category}</span>{d.is_vegetarian === true && <span className="tag-green"><Leaf size={11}/>{d.is_vegan ? "Vegan" : "Vegetarian"}</span>}{d.spice_level > 0 && <span className="tag-heat"><Flame size={11}/>{["", "Mild", "Medium", "Hot"][d.spice_level]}</span>}</div>
        <p className="dish-reason">{item.reason || `Adds a ${CATEGORY_LABEL[d.category]?.toLowerCase() ?? "shared"} option to the table.`}</p>
        <div className="dish-suitability"><div className={notFor.length ? "suitability-partial" : "suitability-all"}>{notFor.length ? <Users size={14}/> : <CheckCircle2 size={14}/>}<strong>{item.edible_by.length} of {n} diners can eat this{pending ? "*" : ""}</strong></div>{notFor.length > 0 && <p>Not for {notFor.join(", ")}.</p>}{pending && <p className="staff-hint">*Check ingredients with staff.</p>}
          {d.allergens.length > 0 && <details className="allergen-details"><summary>Ingredient notes</summary><p>{d.allergens.map(flagWording).join(" · ")}</p></details>}</div>
        <div className="dish-actions"><button className={`dish-action ${kept ? "kept" : ""}`} aria-label={`${kept ? "Unlock" : "Keep"} ${dishName(d)}`} aria-pressed={kept} onClick={() => onLock(d.id)} disabled={loading || stale}>{kept ? <LockKeyhole size={15}/> : <UnlockKeyhole size={15}/>} {kept ? "Kept" : "Keep"}</button><div><button className="dish-action swap-action" aria-label={`Swap ${dishName(d)}`} onClick={() => onSwap(d.id)} disabled={loading || stale}><ArrowLeftRight size={15}/>Swap</button><button className="dish-action remove-action" aria-label={`Remove ${dishName(d)}`} title={`Remove ${dishName(d)}`} onClick={() => onRemove(d.id)} disabled={loading || stale}><Trash2 size={16}/></button></div></div>
      </article>;
    })}<button className="add-course-card" onClick={onAdd} disabled={loading || stale}><span><Plus size={25}/></span><strong>Add a course</strong><small>Find something else on the menu</small></button></div>
    <section className="staff-section" aria-label="Questions for staff"><div><CircleHelp size={19}/><h2>Before you order</h2><span>{plan.confirm_with_staff.length} QUESTIONS</span></div><p>Recorded requirements guide this plan. Confirm sauces, stocks, and preparation with the restaurant.</p>{plan.confirm_with_staff.length ? <ul>{plan.confirm_with_staff.map(q => <li key={q}><label><input type="checkbox" checked={ticked.includes(q)} onChange={() => setTicked(prev => prev.includes(q) ? prev.filter(x => x !== q) : [...prev, q])}/><span className={ticked.includes(q) ? "checked-question" : ""}>{q}</span>{ticked.includes(q) && <Check size={15}/>}</label></li>)}</ul> : <p className="no-questions">No specific questions were recorded for these dishes.</p>}</section>
  </div>;
}
