import { useState } from "react";
import { ArrowLeftRight, ArrowRight, CircleHelp, Flame, Leaf, LockKeyhole, Plus, RefreshCw, Trash2, Users } from "lucide-react";
import { CATEGORY_LABEL, currencySymbol, dishName, flagWording, money } from "../lib/format";
import { dishQuestions, heatNote } from "../lib/dietary";
import { Coverage } from "./Coverage";
import type { DinerProfile, DiningSettings, Menu, Plan } from "../types";

export function Ticket({ menu, plan, diners, settings, locked, stale, loading, onLock, onSwap, onRemove, onAdd, onPlan, onOrder, canOrder, onParty }: {
  menu: Menu; plan: Plan; diners: DinerProfile[]; settings: DiningSettings; locked: string[];
  stale: boolean; loading: boolean; onLock: (id: string) => void; onSwap: (id: string) => void;
  onRemove: (id: string) => void; onAdd: () => void; onPlan: () => void; onOrder: () => void;
  canOrder: boolean; onParty: () => void;
}) {
  const [filter, setFilter] = useState("all");
  const byId = Object.fromEntries(menu.dishes.map(d => [d.id, d]));
  const items = plan.items.filter(i => byId[i.dish_id]);
  const cur = currencySymbol(menu.currency);
  const remaining = settings.budget * diners.length - plan.total;
  const categories = [...new Set(items.map(i => byId[i.dish_id].category))];
  const actualFilter = filter === "all" || categories.includes(filter) ? filter : "all";
  const visible = items.filter(i => actualFilter === "all" || byId[i.dish_id].category === actualFilter);
  const failed = plan.checks.filter(c => !c.passed);
  return <div className="dashboard" aria-busy={loading}>
    <div className="plan-heading"><div><div className="eyebrow">YOUR SHARED TABLE <span> / STEP 3 OF 3</span></div><h1>A little of everything.<br className="mobile-break"/><em> Something for everyone.</em></h1><p>{menu.restaurant_name} <span>·</span> {diners.length} diners <span>·</span> {items.length} dishes to share</p></div><button className="btn btn-outline" onClick={onPlan} disabled={loading}><RefreshCw size={16} className={loading ? "spin" : ""}/>{loading ? "Finding ideas…" : "Refresh suggestions"}</button></div>
    {failed.length > 0 && <div className="notice error-notice" role="status"><CircleHelp size={18}/><div>{failed.map(c => <p key={c.name}>{c.detail}</p>)}</div></div>}
    <div className="plan-layout"><div className="course-column">
      <div className="courses-toolbar"><div className="course-tabs" role="group" aria-label="Filter recommended dishes"><button className={actualFilter === "all" ? "active" : ""} aria-pressed={actualFilter === "all"} onClick={() => setFilter("all")}>All dishes <span>{items.length}</span></button>{categories.map(c => <button key={c} aria-pressed={actualFilter === c} className={actualFilter === c ? "active" : ""} onClick={() => setFilter(c)}>{CATEGORY_LABEL[c] ?? c}<span>{items.filter(i => byId[i.dish_id].category === c).length}</span></button>)}</div></div>
      <p className="course-hint"><LockKeyhole size={13}/>Keep a dish to hold onto it when suggestions refresh.</p>
      <div className="dish-grid">{visible.map(item => {
        const d = byId[item.dish_id], kept = locked.includes(d.id);
        const notFor = diners.filter(p => !item.edible_by.includes(p.id));
        const questions = dishQuestions(d, diners);
        const heat = heatNote(d, diners.filter(p => item.edible_by.includes(p.id)));
        return <article key={d.id} className={`dish-card ${kept ? "dish-kept" : ""}`} aria-label={dishName(d)}>
          <div className="dish-topline"><span className="dish-category">{CATEGORY_LABEL[d.category] ?? d.category}</span>{kept && <span className="kept-label"><LockKeyhole size={12}/>Kept</span>}<span className="dish-number">{String(items.findIndex(i=>i.dish_id===d.id)+1).padStart(2,"0")}</span></div>
          <div className="dish-card-heading"><div><h2>{dishName(d)}</h2>{d.name_zh && <p className="dish-chinese" lang="zh">{d.name_zh}</p>}</div><div className="dish-price">{money((d.price ?? 0)*item.quantity,cur)}<small>{item.quantity > 1 ? `${item.quantity} × ${money(d.price,cur)}` : "1 plate"}</small></div></div>
          <div className="dish-tags">{d.is_vegetarian === true && <span className="tag-green"><Leaf size={13}/>{d.is_vegan ? "Vegan" : "Vegetarian"}</span>}{d.spice_level > 0 && <span className="tag-heat"><Flame size={13}/>{["","Mild","Medium","Hot"][d.spice_level]}</span>}{d.cooking_method && <span>{d.cooking_method.replaceAll("_"," ")}</span>}</div>
          <div className="dish-suitability"><p className="matched-line"><Users size={14}/>{item.edible_by.length}/{diners.length} match recorded requirements</p>{notFor.length > 0 && <p className="excluded-line">Not for {notFor.map(p=>p.name).join(", ")}</p>}{questions.length > 0 && <div className="kitchen-flag"><CircleHelp size={15}/><span><strong>Kitchen check needed</strong><small>{questions[0]}</small></span></div>}{heat && <p className="heat-note"><Flame size={13}/>{heat}</p>}</div>
          <details className="dish-details"><summary>Why this dish & ingredient notes</summary><p>{item.reason || "Adds another option to your shared table."}</p>{d.allergens.length > 0 && <p>{d.allergens.map(flagWording).join(" · ")}</p>}{questions.slice(1).map(q=><p key={q}>{q}</p>)}</details>
          <div className="dish-actions"><button className={`dish-action ${kept ? "kept" : ""}`} aria-label={`${kept ? "Unkeep" : "Keep"} ${dishName(d)}`} aria-pressed={kept} onClick={()=>onLock(d.id)} disabled={loading||stale}><LockKeyhole size={15}/>{kept ? "Kept" : "Keep dish"}</button><div><button className="dish-action swap-action" aria-label={`Swap ${dishName(d)}`} onClick={()=>onSwap(d.id)} disabled={loading||stale}><ArrowLeftRight size={15}/>Swap</button><button className="dish-action remove-action" aria-label={`Remove ${dishName(d)}`} title={`Remove ${dishName(d)}`} onClick={()=>onRemove(d.id)} disabled={loading||stale}><Trash2 size={16}/></button></div></div>
        </article>;
      })}<button className="add-course-card" onClick={onAdd} disabled={loading||stale}><span><Plus size={24}/></span><strong>Something else in mind?</strong><small>Find another dish on the menu</small></button></div>
      <section id="staff-questions" className="staff-section"><div><CircleHelp size={21}/><h2>Before the first bite</h2><span>{plan.confirm_with_staff.length} TO CHECK</span></div><p>Ask the restaurant about these ingredients. Matching the recorded preferences does not confirm how a dish is prepared.</p>{plan.confirm_with_staff.length ? <ol>{plan.confirm_with_staff.map(q=><li key={q}>{q}</li>)}</ol> : <p>No specific questions were recorded. Confirm dietary needs with the restaurant.</p>}</section>
    </div><aside className="order-sidebar"><section className="order-summary" aria-label="Order summary"><div className="summary-heading"><h2>Your order</h2><span>{items.length} dishes</span></div><div className="summary-total"><strong>{money(plan.total,cur)}</strong><span>estimated total</span></div><p className="summary-per-person">{money(plan.per_person,cur)} per person <span>· incl. tax & tip</span></p><div className={`budget-status ${remaining < 0 ? "over-budget" : ""}`}><span>{remaining >= 0 ? `${money(remaining,cur)} within budget` : `${money(-remaining,cur)} over budget`}</span><div className="budget-track"><span style={{width:`${Math.max(0,Math.min(100,100*plan.total/(settings.budget*diners.length)))}%`}}/></div><small>Budget for the table: {money(settings.budget*diners.length,cur)}</small></div><details className="cost-details"><summary>Price breakdown</summary><dl><dt>Menu subtotal</dt><dd>{money(plan.subtotal,cur)}</dd><dt>Tax ({Number((settings.tax*100).toFixed(3))}%)</dt><dd>{money(plan.tax,cur)}</dd><dt>Tip ({Number((settings.tip*100).toFixed(2))}%)</dt><dd>{money(plan.tip,cur)}</dd></dl></details>{plan.confirm_with_staff.length > 0 && <a className="summary-check" href="#staff-questions"><CircleHelp size={17}/><span>{plan.confirm_with_staff.length} kitchen questions to review</span><ArrowRight size={15}/></a>}<button className="btn btn-primary order-cta" onClick={onOrder} disabled={!canOrder}>View order ticket <ArrowRight size={17}/></button><p className="ticket-note">A list to share with your server. No order is placed.</p><button className="text-button edit-table" onClick={onParty}><Users size={15}/>Edit people & budget</button></section><Coverage menu={menu} plan={plan} diners={diners} minDishes={settings.minDishes}/><details className="plan-details"><summary>How this plan was balanced</summary><p>{items.length} dishes against a target of {settings.dishCount}. Variety score: {Math.round(plan.variety_score*100)}/100, based on categories, ingredients and cooking methods.</p></details></aside></div>
    <div className="mobile-order-bar"><div><strong>{money(plan.total,cur)}</strong><small>{money(plan.per_person,cur)} / person</small></div><button className="btn btn-primary" disabled={!canOrder} onClick={onOrder}>Order ticket <ArrowRight size={16}/></button></div>
  </div>;
}
