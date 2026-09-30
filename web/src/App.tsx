import { useEffect, useRef, useState } from "react";
import { AlertCircle, BookOpen, LoaderCircle, RefreshCw, Users, UtensilsCrossed } from "lucide-react";
import { applyPeopleAction, getHealth, getMenu, getMenus, getProfiles, postPlan } from "./api";
import { ConflictNote } from "./components/ConflictNote";
import { ProfileHistory } from "./components/ProfileHistory";
import { SetupFlow } from "./components/SetupFlow";
import { DinerSheet } from "./components/DinerSheet";
import { Sheet } from "./components/Sheet";
import { SwapSheet } from "./components/SwapSheet";
import { TableSetup } from "./components/TableSetup";
import { Ticket } from "./components/Ticket";
import { TopBar } from "./components/TopBar";
import { WaiterView } from "./components/WaiterView";
import type { DinerProfile, DiningSettings, Menu, MenuSummary, PlanResponse, Relaxation } from "./types";

type Context = { menu: Menu; menuId: string; diners: DinerProfile[]; settings: DiningSettings };
type Result = { response: PlanResponse; context: Context; key: string };
const initialSettings: DiningSettings = { budget: 75, tax: .08875, tip: .18, minDishes: 2, dishCount: 7, style: "balanced" };
const keyFor = (c: Context) => JSON.stringify(c);
const errorText = (e: unknown) => e instanceof Error ? e.message : String(e);

export default function App() {
  const [menus, setMenus] = useState<MenuSummary[]>([]);
  const [menuId, setMenuId] = useState("");
  const [menu, setMenu] = useState<Menu | null>(null);
  const [diners, setDiners] = useState<DinerProfile[]>([]);
  const [presets, setPresets] = useState<DinerProfile[]>([]);
  const [settings, setSettings] = useState(initialSettings);
  const [locked, setLocked] = useState<string[]>([]);
  const [excluded, setExcluded] = useState<string[]>([]);
  const [result, setResult] = useState<Result | null>(null);
  const [needsReplan, setNeedsReplan] = useState(false);
  const [loading, setLoading] = useState(false);
  const [starting, setStarting] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mock, setMock] = useState(false);
  const [step, setStep] = useState<"menu" | "table" | "plan">("menu");
  const [undo, setUndo] = useState<{ locked: string[]; excluded: string[]; message: string } | null>(null);
  const [party, setParty] = useState(false);
  const [editing, setEditing] = useState<DinerProfile | "new" | null>(null);
  const [browser, setBrowser] = useState<{ mode: "browse" | "pick"; old: string | null; initialTab?: "browse" | "import" } | null>(null);
  const [waiter, setWaiter] = useState(false);
  const sequence = useRef(0);
  const menuSequence = useRef(0);
  const menuCache = useRef(new Map<string, Menu>());
  const focusedStep = useRef<string | null>(null);
  useEffect(() => {
    if (starting || loading || focusedStep.current === step) return;
    const heading = document.querySelector<HTMLElement>("main h1, main h2");
    if (!heading) return;
    if (focusedStep.current !== null) {
      window.scrollTo({ top: 0, behavior: "instant" });
      heading.tabIndex = -1;
      heading.focus({ preventScroll: true });
    }
    focusedStep.current = step;
  }, [step, starting, loading]);
  const invalidate = () => { sequence.current++; setLoading(false); setError(null); setWaiter(false); setUndo(null); setNeedsReplan(true); };

  const generate = async (over: Partial<Context> & { locked?: string[]; excluded?: string[] } = {}) => {
    const m = over.menu ?? menu;
    const d = over.diners ?? diners;
    const s = over.settings ?? settings;
    if (!m || !d.length) return;
    if (!m.verified) { setError("Review the restaurant menu before planning."); return; }
    if (!(s.budget >= 1 && s.budget <= 500 && s.tax >= 0 && s.tax <= .3 && s.tip >= 0 && s.tip <= .4 && Number.isInteger(s.minDishes) && s.minDishes >= 1 && Number.isInteger(s.dishCount) && s.dishCount >= 1 && s.dishCount <= 20)) { setError("Check the budget, tax, tip, and whole-number course counts."); return; }
    const context: Context = { menu: m, menuId: over.menuId ?? menuId, diners: d, settings: s };
    const seq = ++sequence.current;
    setLoading(true); setNeedsReplan(true); setError(null); setStep("plan");
    try {
      const response = await postPlan({ menu_id: context.menuId, menu_override: m, diners: d,
        budget_per_person: s.budget, budget_total: s.budget, tax_rate: s.tax, tip_rate: s.tip, min_dishes_per_person: s.minDishes,
        dish_count_target: s.dishCount, style_preference: s.style, locked_dish_ids: over.locked ?? locked,
        excluded_dish_ids: over.excluded ?? excluded, explain: true });
      if (seq === sequence.current) { setResult({ response, context, key: keyFor(context) }); setNeedsReplan(false); }
    } catch (e) { if (seq === sequence.current) setError(errorText(e)); }
    finally { if (seq === sequence.current) setLoading(false); }
  };

  useEffect(() => {
    let active = true;
    Promise.all([getMenus(), getProfiles(), getHealth()]).then(([ms, ps, health]) => {
      if (!active) return;
      setMenus(ms); setDiners([]); setPresets(ps); setMock(health.mock);
      setSettings(s => ({ ...s, dishCount: Math.min(20, Math.max(1, ps.length + 1)) }));
      if (ms.length) setMenuId(ms[0].slug); else setStarting(false);
    }).catch(e => { if (active) { setError(`Could not load the table: ${errorText(e)}`); setStarting(false); } });
    return () => { active = false; sequence.current++; };
  }, []);

  useEffect(() => {
    if (!menuId) return;
    const seq = ++menuSequence.current;
    invalidate(); setStarting(true); setMenu(null); setResult(null); setLocked([]); setExcluded([]); setStep("menu");
    const cached = menuCache.current.get(menuId);
    (cached ? Promise.resolve(cached) : getMenu(menuId)).then(m => {
      if (seq !== menuSequence.current) return;
      menuCache.current.set(menuId, m); setMenu(m); setStarting(false);
    }).catch(e => { if (seq === menuSequence.current) { setError(errorText(e)); setStarting(false); } });
    return () => { menuSequence.current++; };
  }, [menuId]);

  const startSample = async () => {
    try {
      const sample = await getMenu(menuId);
      menuCache.current.set(menuId, sample); setMenu(sample); setDiners(presets);
      const sampleSettings = { ...initialSettings, dishCount: Math.min(20, Math.max(1, presets.length + 1)) };
      setSettings(sampleSettings); setLocked([]); setExcluded([]); setUndo(null);
      void generate({ menu: sample, diners: presets, settings: sampleSettings, locked: [], excluded: [] });
    } catch (e) { setError(errorText(e)); }
  };

  const currentContext = menu ? { menu, menuId, diners, settings } : null;
  const stale = !!result && (needsReplan || !currentContext || result.key !== keyFor(currentContext));
  const plan = result?.response.kind === "plan" ? result.response.plan ?? null : null;
  const snapshot = result?.context;
  const canOrder = !!plan && !stale && !loading && !plan.checks.some(c => !c.passed);

  const changePeople = async (action: "add" | "update" | "remove" | "load_preferences", extra: {person?: DinerProfile; person_id?: string; saved?: DinerProfile[]}) => {
    invalidate(); setNeedsReplan(true);
    const seq = sequence.current;
    try {
      const {diners: next} = await applyPeopleAction(diners, action, extra);
      if (seq !== sequence.current) return;
      const nextSettings = settings.dishCount === diners.length + 1 || !diners.length ? { ...settings, dishCount: Math.min(20, Math.max(1, next.length + 1)) } : settings;
      setDiners(next); setSettings(nextSettings); setEditing(null);
      if (!next.length) { setResult(null); setLocked([]); setExcluded([]); }
      else if (step === "plan" && menu?.verified) void generate({diners: next, settings: nextSettings});
    } catch (e) { if (seq === sequence.current) setError(errorText(e)); if (action === "load_preferences") throw e; }
  };
  const saveDiner = (d: DinerProfile) => { void changePeople(diners.some(p => p.id === d.id) ? "update" : "add", {person: d}); };
  const removeDiner = (id: string) => { void changePeople("remove", {person_id: id}); };
  const choosePreset = (id: string) => {
    const next: DinerProfile[] = id === "synthetic-three" ? [1, 2, 3].map(n => ({id: `synthetic_${n}`, name: `Synthetic ${n}`, allergies: [], diets: [], likes: [], dislikes: [], max_spice: null})) : id === "saved" ? presets : id === "two" ? presets.slice(0, 2) : [];
    invalidate(); setDiners(next); setSettings(s => ({ ...s, dishCount: Math.max(1, next.length + 1) })); setLocked([]); setExcluded([]);
    if (!next.length) setResult(null);
  };
  const pickDish = (newId: string) => {
    const old = browser?.old;
    setUndo({ locked: [...locked], excluded: [...excluded], message: old ? "Dish swapped. The table has been rebalanced." : "Dish added. The table has been rebalanced." });
    const ex = [...new Set([...excluded.filter(x => x !== newId), ...(old ? [old] : [])])];
    const lk = [...locked.filter(x => x !== old && x !== newId), newId];
    setExcluded(ex); setLocked(lk); setBrowser(null);
    void generate({ locked: lk, excluded: ex });
  };
  const removeDish = (id: string) => {
    setUndo({ locked: [...locked], excluded: [...excluded], message: "Dish removed from suggestions. The table has been rebalanced." });
    const ex = [...new Set([...excluded, id])], lk = locked.filter(x => x !== id);
    setExcluded(ex); setLocked(lk); void generate({ excluded: ex, locked: lk });
  };
  const applyRelaxation = (r: Relaxation) => {
    if ((r.kind === "budget" || r.kind === "coverage") && r.new_value != null) {
      const s = { ...settings, [r.kind === "budget" ? "budget" : "minDishes"]: r.kind === "budget" ? r.new_value * diners.length : r.new_value };
      invalidate(); setSettings(s); void generate({ settings: s });
    } else if (r.diner_id) { const d = diners.find(d => d.id === r.diner_id); if (d) setEditing(d); }
  };

  return <div className="min-h-screen"><TopBar menu={menu} count={diners.length} onMenu={() => setBrowser({ mode: "browse", old: null })} onParty={() => step === "plan" ? setParty(true) : setStep("table")}/>
    <main className="workspace">
      {menu?.preparation_mode === "prepared_replay" && <div className="notice" role="status"><AlertCircle size={17}/><span>Assistant-prepared menu response replay. No live model or image OCR. Prices are a dated factual extract; ingredients and fees need confirmation.</span></div>}
      <ProfileHistory diners={diners} onLoad={people => changePeople("load_preferences", {saved: people})}/>
      {mock && <div className="notice" role="status"><AlertCircle size={17}/><span>This demonstration uses a fixed set of sample dishes.</span></div>}
      {error && <div className="notice error-notice" role="alert"><AlertCircle size={17}/><span>{error}</span>{menu && <button className="btn btn-quiet btn-small" onClick={() => void generate()} disabled={loading}>Try again</button>}</div>}
      {stale && <div className="notice" role="status"><RefreshCw size={17} className={loading ? "spin" : ""}/><span>{loading ? "Updating the dishes. Kept dishes stay in place…" : "Your table or budget changed. Update the dishes to match."}</span>{!loading && <button className="btn btn-quiet btn-small" onClick={() => void generate()} disabled={!menu?.verified}>Update dishes</button>}</div>}
      {menu && !menu.verified && <div className="notice"><BookOpen size={17}/><span>Menu changes need review before a new plan can be generated.</span><button className="btn btn-quiet btn-small" onClick={() => setBrowser({ mode: "browse", old: null })}>Review menu</button></div>}
      {undo && !loading && <div className="change-notice" role="status"><span>{error || result?.response.kind === "conflict" ? "That change could not produce a new plan." : undo.message}</span><button className="text-button" onClick={() => { const previous = undo; setLocked(previous.locked); setExcluded(previous.excluded); setUndo(null); void generate({ locked: previous.locked, excluded: previous.excluded }); }}>Undo</button><button className="dismiss-change" aria-label="Dismiss update" onClick={() => setUndo(null)}>×</button></div>}
      {(starting || (loading && !result)) ? <div className="empty-state" role="status"><LoaderCircle size={30} className="spin mx-auto"/><h2>{starting ? "Setting the table…" : "Finding a table that works…"}</h2><p>Considering the menu, budget, and everyone's requirements.</p></div> : step !== "plan" && menu ? <SetupFlow step={step} onStep={setStep} menu={menu} diners={diners} settings={settings} onMenu={() => setBrowser({ mode: "browse", old: null })} onImport={() => setBrowser({ mode: "browse", old: null, initialTab: "import" })} onSample={() => void startSample()} onChange={s => { invalidate(); setSettings(s); }} onEdit={setEditing} onAdd={() => setEditing("new")} onPreset={choosePreset} onPlan={() => void generate()} loading={loading}/> : stale && !loading ? <div className="empty-state"><h2>Update your meal</h2><p>The previous recommendation is no longer current.</p><button className="btn btn-primary" onClick={() => void generate()}>Update dishes</button></div> : plan && snapshot ? <>
        <Ticket key={result?.key + JSON.stringify(plan.items)} menu={snapshot.menu} plan={plan} diners={snapshot.diners} settings={snapshot.settings} locked={locked} stale={stale} loading={loading} onLock={id => { setUndo(null); setLocked(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]); }} onSwap={id => setBrowser({ mode: "pick", old: id })} onRemove={removeDish} onAdd={() => setBrowser({ mode: "pick", old: null })} onPlan={() => { setUndo(null); void generate(); }} onOrder={() => setWaiter(true)} canOrder={canOrder} onParty={() => setParty(true)}/>
      </> : result?.response.conflict ? <><ConflictNote conflict={result.response.conflict} menu={result.context.menu} diners={result.context.diners} settings={result.context.settings} onRelax={applyRelaxation}/><div className="conflict-actions"><button className="btn btn-quiet" onClick={() => setParty(true)}><Users size={16}/>Edit people and budget</button><button className="btn btn-quiet" onClick={() => { setLocked([]); setExcluded([]); void generate({ locked: [], excluded: [] }); }} disabled={loading}><RefreshCw size={16}/>Reset dish choices</button><button className="btn btn-quiet" onClick={() => setBrowser({ mode: "browse", old: null })}><BookOpen size={16}/>Browse menu</button></div></> : <div className="empty-state"><UtensilsCrossed size={30} className="mx-auto"/><h2>{diners.length ? "Your next meal starts here" : "Who's joining the table?"}</h2><p>{diners.length ? "Review your group and choose a menu to plan a shared meal." : "Add diners and their dietary requirements to get started."}</p><button className="btn btn-primary" onClick={() => setParty(true)}><Users size={16}/>Set up the table</button>{!!diners.length && menu && <button className="btn btn-quiet ml-3" onClick={() => void generate()}>Plan the table</button>}</div>}
      {(locked.length > 0 || excluded.length > 0) && <div className="choices-summary"><span>{locked.length} kept · {excluded.length} removed from recommendations</span><button className="btn btn-outline btn-small" disabled={loading} onClick={() => { setLocked([]); setExcluded([]); void generate({ locked: [], excluded: [] }); }}>Reset dish choices</button></div>}
    </main>
    {party && <Sheet title="Your table" onClose={() => setParty(false)}><TableSetup diners={diners} settings={settings} currency={menu?.currency ?? "USD"} onChange={s => { invalidate(); setSettings(s); }} onEdit={setEditing} onAdd={() => setEditing("new")} onPreset={choosePreset} onPlan={() => { setParty(false); void generate(); }} loading={loading}/></Sheet>}
    {browser && menu && <SwapSheet key={menuId} menu={menu} menus={menus} menuId={menuId} plan={stale ? null : plan} diners={diners} excluded={excluded} old={browser.old} mode={browser.mode} initialTab={browser.initialTab} tax={settings.tax} tip={settings.tip} onPick={pickDish} onClose={() => setBrowser(null)} onUpdate={m => { invalidate(); menuCache.current.set(menuId, m); setMenu(m); }} onSelectMenu={setMenuId}/>}
    {editing && <DinerSheet diner={editing === "new" ? null : editing} existingIds={diners.map(d => d.id)} onSave={saveDiner} onRemove={removeDiner} onClose={() => setEditing(null)}/>}
    {waiter && canOrder && snapshot && plan && <WaiterView menu={snapshot.menu} plan={plan} diners={snapshot.diners} onClose={() => setWaiter(false)}/>}
  </div>;
}
