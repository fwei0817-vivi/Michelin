import { useState } from "react";
import { ArrowLeftRight, Check, ChevronDown, CircleHelp, Flame, Leaf, LockKeyhole, Plus, RefreshCw, Trash2, UnlockKeyhole, UserX, Users, X } from "lucide-react";
import { CATEGORY_LABEL, checkLabel, currencySymbol, dishName, flagWording, listNames, money } from "../lib/format";
import { dishQuestions, heatNote } from "../lib/dietary";
import { DISH_PHOTOS } from "../lib/dishPhotos";
import { Coverage } from "./Coverage";
import type { DinerProfile, DiningSettings, Dish, Menu, Plan, PlanItem } from "../types";

interface Props {
  menu: Menu;
  plan: Plan;
  diners: DinerProfile[];
  settings: DiningSettings;
  locked: string[];
  stale: boolean;
  loading: boolean;
  onLock: (id: string) => void;
  onSwap: (id: string) => void;
  onRemove: (id: string) => void;
  onAdd: () => void;
  onPlan: () => void;
  onOrder: () => void;
  canOrder: boolean;
  onParty: () => void;
}

const SPICE = ["", "Mild", "Medium", "Hot"];

export function Ticket({ menu, plan, diners, settings, locked, stale, loading, onLock, onSwap, onRemove, onAdd, onPlan, onOrder, canOrder, onParty }: Props) {
  const [filter, setFilter] = useState("all");
  const [open, setOpen] = useState<string[]>([]);
  const byId: Record<string, Dish> = Object.fromEntries(menu.dishes.map((d) => [d.id, d]));
  const items = plan.items.filter((i) => byId[i.dish_id]);
  const cur = currencySymbol(menu.currency);
  const remaining = settings.budget - plan.per_person;
  const over = remaining < 0;
  const questions = plan.confirm_with_staff.length;
  const failed = plan.checks.filter((c) => !c.passed);
  const disabled = loading || stale;
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
          <h1>{items.length} dishes to share</h1>
        </div>
        {!stale && (
          <button className="btn btn-outline" onClick={onPlan} disabled={loading}>
            <RefreshCw size={15} className={loading ? "spin" : ""} />
            {loading ? "Finding dishes…" : "Refresh suggestions"}
          </button>
        )}
      </div>

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
                Keep a dish to hold onto it when suggestions refresh.
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
                  expanded={open.includes(item.dish_id)}
                  disabled={disabled}
                  onToggle={toggleOpen}
                  onLock={onLock}
                  onSwap={onSwap}
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
            {visible.some((i) => DISH_PHOTOS[i.dish_id]) && (
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

          <Coverage menu={menu} plan={plan} diners={diners} minDishes={settings.minDishes} />

          <details className="plan-how">
            <summary>How this plan was checked</summary>
            <ul>
              {plan.checks.map((c) => (
                <li key={c.name}>
                  <strong>{checkLabel(c.name, c.passed, settings.minDishes)}.</strong> {c.detail}
                </li>
              ))}
            </ul>
            <p>
              {items.length} dishes against a target of {settings.dishCount}. Variety score {Math.round(plan.variety_score * 100)} of 100, from categories, ingredients and cooking methods.
            </p>
          </details>
        </div>

        <aside className="bill" aria-label="Your order">
          <h2>Your order, {items.length} dishes</h2>
          <p className="bill-total">
            <strong>{money(plan.per_person, cur)}</strong>
            <span>per person</span>
          </p>
          <p className="bill-table">{money(plan.total, cur)} for the table, using selected tax and tip</p>
          <div className={`bill-budget ${over ? "over" : ""}`}>
            <div className="bill-track">
              <span style={{ width: `${Math.max(0, Math.min(100, (100 * plan.per_person) / settings.budget))}%` }} />
            </div>
            {over
              ? `${money(-remaining, cur)} over your ${money(settings.budget, cur)} budget`
              : `${money(remaining, cur)} under your ${money(settings.budget, cur)} budget`}
          </div>
          <ul className="bill-checks" aria-label="Plan checks">
            {plan.checks.map((c) => (
              <li key={c.name} className={c.passed ? "" : "failed"}>
                {c.passed ? <Check size={14} /> : <X size={14} />}
                {checkLabel(c.name, c.passed, settings.minDishes)}
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

function DishCard({ item, dish, diners, cur, kept, expanded, disabled, onToggle, onLock, onSwap, onRemove }: {
  item: PlanItem;
  dish: Dish;
  diners: DinerProfile[];
  cur: string;
  kept: boolean;
  expanded: boolean;
  disabled: boolean;
  onToggle: (id: string) => void;
  onLock: (id: string) => void;
  onSwap: (id: string) => void;
  onRemove: (id: string) => void;
}) {
  const name = dishName(dish);
  const notFor = diners.filter((p) => !item.edible_by.includes(p.id));
  const heat = heatNote(dish, diners.filter((p) => item.edible_by.includes(p.id)));
  const questions = dishQuestions(dish, diners);
  const photo = DISH_PHOTOS[dish.id];
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
        {dish.is_vegetarian === true && (
          <span>
            <Leaf size={12} />
            {dish.is_vegan ? "Vegan" : "Vegetarian"}
          </span>
        )}
        {dish.spice_level > 0 && (
          <span>
            <Flame size={12} />
            {SPICE[dish.spice_level]}
          </span>
        )}
        {dish.cooking_method && <span>{dish.cooking_method.replaceAll("_", " ")}</span>}
        {notFor.length === 0 && (
          <span title="Matches every diner's recorded requirements">
            <Users size={12} />
            Matches all {diners.length}
          </span>
        )}
      </div>
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
        <p>{item.reason || "Adds another option to your shared table."}</p>
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
          title={kept ? "Kept when suggestions refresh" : "Keep this dish"}
          aria-pressed={kept}
          onClick={() => onLock(dish.id)}
          disabled={disabled}
        >
          {kept ? <LockKeyhole size={15} /> : <UnlockKeyhole size={15} />}
        </button>
        <button className="dish-action swap-action" aria-label={`Swap ${name}`} onClick={() => onSwap(dish.id)} disabled={disabled}>
          <ArrowLeftRight size={14} />
          Swap
        </button>
        <button className="dish-action remove-action" aria-label={`Remove ${name}`} title={`Remove ${name}`} onClick={() => onRemove(dish.id)} disabled={disabled}>
          <Trash2 size={15} />
        </button>
      </div>
    </article>
  );
}
