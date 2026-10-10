import { useState } from "react";
import { ArrowLeftRight, Check, ChevronDown, CircleHelp, Flame, Leaf, ListChecks, LockKeyhole, Plus, RefreshCw, Sparkles, Trash2, UnlockKeyhole, UserX, Users, X } from "lucide-react";
import { CATEGORY_LABEL, MARK_LABEL, checkLabel, currencySymbol, dishName, flagWording, listNames, money } from "../lib/format";
import { coverageLabel } from "../lib/coverage";
import { dishQuestions, fitsChip, heatNote, needsConfirm, vegTag } from "../lib/dietary";
import { photoFor } from "../lib/dishPhotos";
import { Coverage } from "./Coverage";
import type { DinerProfile, DiningSettings, Dish, FeedbackChip, Menu, Plan, PlanItem } from "../types";

const FEEDBACK_CHIPS: [FeedbackChip, string][] = [
  ["less_spicy", "Less spicy"],
  ["more_seafood", "More seafood"],
  ["more_veggies", "More veggies"],
  ["cheaper", "Cheaper"],
  ["more_filling", "More filling"],
  ["something_different", "Something different"],
];

/** "What should change?": quick chips plus free text, sent with the current order. */
function RefineBox({ loading, onSubmit, onCancel }: { loading: boolean; onSubmit: (chips: FeedbackChip[], text: string) => void; onCancel: () => void }) {
  const [chips, setChips] = useState<FeedbackChip[]>([]);
  const [text, setText] = useState("");
  const ready = chips.length > 0 || text.trim().length > 0;
  return (
    <form className="refine-box" aria-label="What should change?" onSubmit={(e) => { e.preventDefault(); if (ready) onSubmit(chips, text.trim()); }}>
      <label htmlFor="refine-text"><strong>What should change?</strong></label>
      <div className="check-grid">
        {FEEDBACK_CHIPS.map(([id, label]) => (
          <label key={id} className={`check-chip ${chips.includes(id) ? "on" : ""}`}>
            <input type="checkbox" checked={chips.includes(id)} onChange={() => setChips(chips.includes(id) ? chips.filter((c) => c !== id) : [...chips, id])} />
            {label}
          </label>
        ))}
      </div>
      <input id="refine-text" className="field" maxLength={200} value={text} onChange={(e) => setText(e.target.value)} placeholder="Anything else, e.g. one more noodle dish" />
      <div className="refine-actions">
        <button type="submit" className="btn btn-primary btn-small" disabled={!ready || loading}>Update the order</button>
        <button type="button" className="btn btn-outline btn-small" onClick={onCancel}>Cancel</button>
      </div>
      <small className="text-xs text-fg-3">Kept dishes stay. Every change is checked against allergies, diets and the budget.</small>
    </form>
  );
}

interface Props {
  menu: Menu;
  plan: Plan;
  diners: DinerProfile[];
  settings: DiningSettings;
  source: "ai" | "rules" | "mock";
  sourceNote: string | null;
  locked: string[];
  stale: boolean;
  loading: boolean;
  onLock: (id: string) => void;
  onSwap: (id: string) => void;
  onAiSwap: (id: string) => void;
  swapping: string | null;
  onRemove: (id: string) => void;
  onAdd: () => void;
  onRefine: (chips: FeedbackChip[], text: string) => void;
  onOrder: () => void;
  canOrder: boolean;
  onParty: () => void;
}

// One printed pepper is "a little spicy", never "mild" (QA r8): viewers see the 🌶 on the menu.
const SPICE = ["", "A little spicy", "Spicy", "Very spicy"];

export function Ticket({ menu, plan, diners, settings, source, sourceNote, locked, stale, loading, onLock, onSwap, onAiSwap, swapping, onRemove, onAdd, onRefine, onOrder, canOrder, onParty }: Props) {
  const [filter, setFilter] = useState("all");
  const [open, setOpen] = useState<string[]>([]);
  const [refining, setRefining] = useState(false);
  const byId: Record<string, Dish> = Object.fromEntries(menu.dishes.map((d) => [d.id, d]));
  const items = plan.items.filter((i) => byId[i.dish_id]);
  // QA r18: the coverage line comes from the backend per-diner status, never "everyone" when someone only has dishes to confirm
  const cov = coverageLabel(items.filter((i) => byId[i.dish_id].category !== "staple"), diners);
  // a missed 'enough food' rule says exactly what is missing, never just a label
  const label = (c: { name: string; passed: boolean; detail?: string }) =>
    c.name === "coverage" ? cov.label : c.name === "enough" && !c.passed && c.detail ? c.detail.replace(/\.$/, "") : checkLabel(c.name, c.passed);
  const passed = (c: { name: string; passed: boolean }) => (c.name === "coverage" ? c.passed && cov.passed : c.passed);
  const cur = currencySymbol(menu.currency);
  const remaining = settings.budget - plan.per_person;
  const over = remaining < 0;
  const questions = plan.confirm_with_staff.length;
  const failed = plan.checks.filter((c) => !c.passed);
  const disabled = loading || stale || swapping !== null;
  const categories = [...new Set(items.map((i) => byId[i.dish_id].category))];
  const actualFilter = filter === "all" || categories.includes(filter) ? filter : "all";
  const visible = items.filter((i) => actualFilter === "all" || byId[i.dish_id].category === actualFilter);
  const toggleOpen = (id: string) => setOpen((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  return (
    <div className="plan" aria-busy={loading}>
      <div className="plan-head">
        <div>
          <p className="plan-sub">
            {menu.restaurant_name}, {diners.length} {diners.length === 1 ? "diner" : "diners"}
          </p>
          <h1>{items.length} {items.length === 1 ? "dish" : "dishes"} to share</h1>
          {source !== "mock" && plan.summary && <p className={`plan-summary${source === "rules" ? " plan-summary-rules" : ""}`}>{plan.summary}</p>}
        </div>
        {!stale && (
          <button className="btn btn-outline" onClick={() => setRefining((v) => !v)} disabled={loading} aria-expanded={refining}>
            <RefreshCw size={15} className={loading ? "spin" : ""} />
            {loading ? "Updating the order…" : "Change suggestions"}
          </button>
        )}
      </div>

      {refining && !stale && (
        <RefineBox loading={loading} onCancel={() => setRefining(false)} onSubmit={(chips, text) => { setRefining(false); onRefine(chips, text); }} />
      )}

      {failed.length > 0 && (
        <div className="notice error-notice" role="status">
          <X size={17} />
          <div>
            {failed.map((c) => (
              <p key={c.name}>{c.detail}</p>
            ))}
          </div>
        </div>
      )}

      <div className="plan-grid">
        <div className="plan-main">
          <div>
            <div className="courses-toolbar">
              <div className="course-tabs" role="group" aria-label="Filter recommended dishes">
                <button className={actualFilter === "all" ? "active" : ""} aria-pressed={actualFilter === "all"} onClick={() => setFilter("all")}>
                  All dishes <span>{items.length}</span>
                </button>
                {categories.map((c) => (
                  <button key={c} className={actualFilter === c ? "active" : ""} aria-pressed={actualFilter === c} onClick={() => setFilter(c)}>
                    {CATEGORY_LABEL[c] ?? c}
                    <span>{items.filter((i) => byId[i.dish_id].category === c).length}</span>
                  </button>
                ))}
              </div>
              <p className="course-hint">
                <LockKeyhole size={13} />
                Keep a dish to hold onto it when suggestions change.
              </p>
            </div>
            <div className="dish-grid">
              {visible.map((item) => (
                <DishCard
                  key={item.dish_id}
                  item={item}
                  dish={byId[item.dish_id]}
                  diners={diners}
                  cur={cur}
                  kept={locked.includes(item.dish_id)}
                  ai={source !== "mock"}
                  expanded={open.includes(item.dish_id)}
                  disabled={disabled}
                  onToggle={toggleOpen}
                  onLock={onLock}
                  onSwap={onSwap}
                  onAiSwap={onAiSwap}
                  swapping={swapping === item.dish_id}
                  onRemove={onRemove}
                />
              ))}
              <button className="add-course-card" onClick={onAdd} disabled={disabled}>
                <span>
                  <Plus size={20} />
                </span>
                <strong>Something else in mind?</strong>
                <small>Find another dish on the menu</small>
              </button>
            </div>
            {visible.some((i) => photoFor(byId[i.dish_id])) && (
              <p className="photo-note">
                Photos show similar dishes from Wikimedia Commons, for illustration. They are not this restaurant's food and say nothing about ingredients.
              </p>
            )}
          </div>

          <section id="ask-server" className="sheet ask" aria-labelledby="ask-heading">
            <h2 id="ask-heading">Ask your server before you order</h2>
            <p>Matching everyone's recorded needs says nothing about how a dish is cooked. These questions come from the menu wording; the order ticket repeats them.</p>
            {questions > 0 ? (
              <ol>
                {plan.confirm_with_staff.map((q) => (
                  <li key={q}>{q}</li>
                ))}
              </ol>
            ) : (
              <p>No specific questions came up. Still tell your server about any allergies at the table.</p>
            )}
          </section>

          <Coverage menu={menu} plan={plan} diners={diners} />

          <details className="plan-how">
            <summary>How this plan was checked</summary>
            <ul>
              {plan.checks.map((c) => (
                <li key={c.name}>
                  <strong>{label(c)}.</strong> {c.detail}
                </li>
              ))}
            </ul>
            <p>
              {items.length} {items.length === 1 ? "dish" : "dishes"}. Variety score {Math.round(plan.variety_score * 100)} of 100, from categories, ingredients and cooking methods.
            </p>
          </details>
        </div>

        <aside className="bill" aria-label="Your order">
          <h2>Your order, {items.length} dishes</h2>
          <p className={`plan-source plan-source-${source}`} title={sourceNote ?? undefined}>
            {source === "ai" ? <Sparkles size={13} /> : <ListChecks size={13} />}
            {source === "ai" ? "Chosen by AI, checked by the rules" : source === "rules" ? "Built by the rules after the AI's orders failed the checks" : "Demo fixture plan"}
          </p>
          <p className="bill-total">
            <strong>{money(plan.per_person, cur)}</strong>
            <span>per person</span>
          </p>
          <p className="bill-table">{money(plan.total, cur)} for the table, including tax and tip</p>
          <div className={`bill-budget ${over ? "over" : ""}`}>
            <div className="bill-track">
              <span style={{ width: `${Math.max(0, Math.min(100, (100 * plan.per_person) / settings.budget))}%` }} />
            </div>
            {over
              ? `${money(-remaining, cur)} a person over your ${money(settings.budget, cur)} budget`
              : `${money(remaining, cur)} a person under your ${money(settings.budget, cur)} budget`}
          </div>
          <ul className="bill-checks" aria-label="Plan checks">
            {plan.checks.map((c) => (
              <li key={c.name} className={passed(c) ? "" : "failed"}>
                {passed(c) ? <Check size={14} /> : <X size={14} />}
                {label(c)}
              </li>
            ))}
          </ul>
          <details className="bill-breakdown">
            <summary>Price breakdown</summary>
            <dl>
              <dt>Menu prices</dt>
              <dd>{money(plan.subtotal, cur)}</dd>
              <dt>Tax ({Number((settings.tax * 100).toFixed(3))}%)</dt>
              <dd>{money(plan.tax, cur)}</dd>
              <dt>Tip ({Number((settings.tip * 100).toFixed(2))}%)</dt>
              <dd>{money(plan.tip, cur)}</dd>
            </dl>
          </details>
          {questions > 0 && (
            <a className="bill-ask" href="#ask-server">
              {questions} {questions === 1 ? "question" : "questions"} for your server
            </a>
          )}
          <button className="btn btn-light" onClick={onOrder} disabled={!canOrder}>
            View order ticket
          </button>
          <p className="bill-note">Confirm fees and serving sizes with your server. Nothing is ordered from here.</p>
          <button className="text-button light" onClick={onParty}>
            Edit people and budget
          </button>
        </aside>
      </div>

      <div className="mobile-bar">
        <div>
          <strong>
            {money(plan.per_person, cur)} <span>per person</span>
          </strong>
          <small>{money(plan.total, cur)} for the table</small>
        </div>
        <button className="btn btn-light" disabled={!canOrder} onClick={onOrder}>
          Order ticket
        </button>
      </div>
    </div>
  );
}

function DishCard({ item, dish, diners, cur, kept, ai, expanded, disabled, onToggle, onLock, onSwap, onAiSwap, swapping, onRemove }: {
  item: PlanItem;
  dish: Dish;
  diners: DinerProfile[];
  cur: string;
  kept: boolean;
  ai: boolean;
  expanded: boolean;
  disabled: boolean;
  onToggle: (id: string) => void;
  onLock: (id: string) => void;
  onSwap: (id: string) => void;
  onAiSwap: (id: string) => void;
  swapping: boolean;
  onRemove: (id: string) => void;
}) {
  const name = dishName(dish);
  const notFor = diners.filter((p) => !item.edible_by.includes(p.id));
  // spice tag and taste note come from the backend (plan.spice); old saved plans fall back
  const heat = item.status ? item.heat_note ?? null : heatNote(dish, diners.filter((p) => item.edible_by.includes(p.id)));
  const tooHot = diners.filter((p) => item.status?.[p.id]?.taste === "too_spicy");
  const spiceTag = item.status ? item.spice_label ?? null : dish.spice_level ? SPICE[dish.spice_level] : null;
  // AI plans carry one rule-checked question per dish; other plans use the templates.
  const questions = ai && item.server_question !== undefined ? (item.server_question ? [item.server_question] : []) : dishQuestions(dish, diners);
  // The backend's per-diner status is the one source (QA r15); old saved plans lack it.
  const unsure = item.status ? needsConfirm(item.status, item.edible_by) : questions.length > 0;
  const veg = vegTag(item.veg_tag); // backend-decided (QA r16)
  const photo = photoFor(dish);
  const panelId = `dish-panel-${dish.id}`;
  return (
    <article className={`dish-card ${kept ? "dish-kept" : ""} ${photo ? "has-photo" : ""}`} aria-label={name}>
      {photo && <img className="dish-photo" src={photo.src} alt="" width={80} height={80} loading="lazy" />}
      <div className="dish-card-heading">
        <h2>{name}</h2>
        <p className="dish-sub">
          <span className="dish-price">
            {money((dish.price ?? 0) * item.quantity, cur)}
            {item.quantity > 1 && (
              <small>
                {" "}
                ({item.quantity} × {money(dish.price, cur)})
              </small>
            )}
          </span>
          {dish.name_zh && <span lang="zh">{dish.name_zh}</span>}
        </p>
      </div>
      <div className="dish-tags">
        {kept && (
          <span className="tag-kept">
            <LockKeyhole size={12} />
            Kept
          </span>
        )}
        {veg && (
          <span className={veg.ask ? "tag-ask" : ""} title={veg.ask ? "Ask the kitchen first" : undefined}>
            <Leaf size={12} />
            {veg.label}
          </span>
        )}
        {spiceTag && (
          <span>
            <Flame size={12} />
            {spiceTag}
          </span>
        )}
        {(dish.menu_marks ?? []).map((m) => <span key={m} className="tag-mark" title={MARK_LABEL[m]?.title}>Menu: {MARK_LABEL[m]?.short ?? m}</span>)}
        {dish.cooking_method && <span>{dish.cooking_method.replaceAll("_", " ")}</span>}
        {notFor.length === 0 && tooHot.length === 0 && (
          <span title={unsure ? "Allowed for everyone only once the server answers the questions below" : "Matches every diner's recorded requirements"} className={unsure ? "tag-ask" : ""}>
            <Users size={12} />
            {fitsChip(diners.length, unsure)}
          </span>
        )}
      </div>
      {ai && item.reason && (
        <p className="dish-reason">
          <Sparkles size={12} />
          <span>{item.reason}</span>
        </p>
      )}
      {(notFor.length > 0 || heat) && (
        <div className="dish-notes">
          {notFor.length > 0 && (
            <p className="not-for">
              <UserX size={13} />
              <span>Not for {listNames(notFor.map((p) => p.name))}</span>
            </p>
          )}
          {heat && (
            <p>
              <Flame size={13} />
              <span>{heat}</span>
            </p>
          )}
        </div>
      )}
      <div className="dish-panel" id={panelId} hidden={!expanded}>
        {questions.map((q) => (
          <p key={q} className="dish-question">
            <CircleHelp size={13} />
            <span>{q}</span>
          </p>
        ))}
        {!ai && <p>{item.reason || "Adds another option to your shared table."}</p>}
        {dish.allergens.length > 0 && <p className="dish-flags">{dish.allergens.map(flagWording).join(" · ")}</p>}
        {photo && (
          <p className="dish-flags">
            Photo of a similar dish, for illustration:{" "}
            <a href={photo.source} target="_blank" rel="noreferrer">
              {photo.author}
            </a>
            , {photo.license}.
          </p>
        )}
      </div>
      <div className="dish-foot">
        <button className={`dish-more ${questions.length ? "has-check" : ""}`} aria-expanded={expanded} aria-controls={panelId} onClick={() => onToggle(dish.id)}>
          {questions.length > 0 && <CircleHelp size={14} />}
          {questions.length ? `${questions.length} kitchen ${questions.length === 1 ? "check" : "checks"}` : "Details"}
          <ChevronDown size={14} />
        </button>
        <button
          className={`dish-action ${kept ? "kept" : ""}`}
          aria-label={`Keep ${name}`}
          title={kept ? "Kept when suggestions change" : "Keep this dish"}
          aria-pressed={kept}
          onClick={() => onLock(dish.id)}
          disabled={disabled}
        >
          {kept ? <LockKeyhole size={15} /> : <UnlockKeyhole size={15} />}
        </button>
        {dish.category !== "staple" && (
          <button className="dish-action swap-action ai-swap-action" aria-label={`Let AI replace ${name}`} title="Let AI swap this: only this dish changes" onClick={() => onAiSwap(dish.id)} disabled={disabled}>
            {swapping ? <RefreshCw size={14} className="spin" /> : <Sparkles size={14} />}
            {swapping ? "Swapping…" : "AI swap"}
          </button>
        )}
        {dish.category !== "staple" && (
          <button className="dish-action pick-action" aria-label={`Pick from menu to replace ${name}`} title="Pick a replacement from the menu yourself" onClick={() => onSwap(dish.id)} disabled={disabled}>
            <ArrowLeftRight size={14} />
            Pick from menu
          </button>
        )}
        <button className="dish-action remove-action" aria-label={`Remove ${name}`} title={`Remove ${name}`} onClick={() => onRemove(dish.id)} disabled={disabled}>
          <Trash2 size={15} />
        </button>
      </div>
    </article>
  );
}
