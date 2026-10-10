import { useEffect, useRef, useState } from "react";
import { orderBlock } from "./lib/coverage";
import { AlertCircle, BookOpen, LoaderCircle, RefreshCw, Users, UtensilsCrossed, ArrowLeft } from "lucide-react";
import { applyPeopleAction, deletePerson, getHealth, getMenu, getMenus, getProfiles, getSavedPeople, menuFacts, postPlan, postSwap, savePerson } from "./api";
import { ConflictNote } from "./components/ConflictNote";
import { SetupFlow } from "./components/SetupFlow";
import { Stepper } from "./components/Stepper";
import { DinerSheet } from "./components/DinerSheet";
import { Progress } from "./components/Progress";
import { Sheet } from "./components/Sheet";
import { SwapSheet } from "./components/SwapSheet";
import { TableSetup } from "./components/TableSetup";
import { Ticket } from "./components/Ticket";
import { TopBar } from "./components/TopBar";
import { WaiterView } from "./components/WaiterView";
import type { DinerProfile, DiningSettings, FeedbackChip, Menu, MenuSummary, PlanResponse, Relaxation } from "./types";

type Context = { menu: Menu; menuId: string; diners: DinerProfile[]; settings: DiningSettings };
type Result = { response: PlanResponse; context: Context; key: string };
// settings.budget is per person, all-in (tax and tip included). The AI decides how many
// dishes; every count on screen is plan.items.length.
const initialSettings: DiningSettings = { budget: 25, tax: .08875, tip: .18, style: "balanced" };
const LOCAL_PREFIX = "local-";
const ADDING = "__adding__";  // `swapping` while a dish is being added
const keyFor = (c: Context) => JSON.stringify(c);
// Imported menus and tonight's table survive a reload (this browser only).
const SESSION_KEY = "michelin.session.v1";
interface Session { menus: Menu[]; menuId: string; diners: DinerProfile[]; settings: DiningSettings; step: "menu" | "table" | "plan" }
function loadSession(): Partial<Session> {
  try { return JSON.parse(localStorage.getItem(SESSION_KEY) ?? "{}") ?? {}; } catch { return {}; }
}
const errorText = (e: unknown) => e instanceof Error ? e.message : String(e);

export default function App() {
  const [menus, setMenus] = useState<MenuSummary[]>([]);
  const [menuId, setMenuId] = useState("");
  const [menu, setMenu] = useState<Menu | null>(null);
  const [diners, setDiners] = useState<DinerProfile[]>([]);
  const [presets, setPresets] = useState<DinerProfile[]>([]);
  // Everyone ever added: saved automatically, picked per meal (at most six tonight).
  const [saved, setSaved] = useState<DinerProfile[]>([]);
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
  // Undo after an AI swap restores the previous plan itself (no new model call).
  const [undo, setUndo] = useState<{ locked: string[]; excluded: string[]; message: string; result?: Result } | null>(null);
  const [swapping, setSwapping] = useState<string | null>(null);
  const [swapFailed, setSwapFailed] = useState<{ id: string | null; message: string; manual: boolean } | null>(null);
  const [swapSteps, setSwapSteps] = useState<string[]>([]);
  const [party, setParty] = useState(false);
  const [editing, setEditing] = useState<DinerProfile | "new" | null>(null);
  const [browser, setBrowser] = useState<{ mode: "browse" | "pick"; old: string | null; initialTab?: "browse" | "import"; photos?: File[]; fromStart?: boolean } | null>(null);
  const [waiter, setWaiter] = useState(false);
  const sequence = useRef(0);
  // Budget and course count follow the number of diners until the user sets them.
  const [photoReader, setPhotoReader] = useState<"openrouter" | "gemini" | "ocr" | null>(null);
  const menuSequence = useRef(0);
  const menuCache = useRef(new Map<string, Menu>());
  const restored = useRef<Partial<Session> | null>(null);
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
  const editSettings = (s: DiningSettings) => { invalidate(); setSettings(s); };
  const invalidate = () => { sequence.current++; setLoading(false); setError(null); setWaiter(false); setUndo(null); setSwapping(null); setSwapFailed(null); setNeedsReplan(true); };

  const generate = async (over: Partial<Context> & { locked?: string[]; excluded?: string[] } = {}) => {
    const m = over.menu ?? menu;
    const d = over.diners ?? diners;
    const s = over.settings ?? settings;
    if (!m || !d.length) return;
    if (!m.verified) { setError("Review the restaurant menu before planning."); return; }
    if (!(s.budget >= 1 && s.budget <= 500 && s.tax >= 0 && s.tax <= .3 && s.tip >= 0 && s.tip <= .4)) { setError("Check the budget, tax and tip."); return; }
    const context: Context = { menu: m, menuId: over.menuId ?? menuId, diners: d, settings: s };
    const seq = ++sequence.current;
    setLoading(true); setNeedsReplan(true); setError(null); setStep("plan");
    try {
      const response = await postPlan({ menu_id: context.menuId, menu_override: m, diners: d,
        budget_per_person: s.budget, tax_rate: s.tax, tip_rate: s.tip,
        style_preference: s.style, locked_dish_ids: over.locked ?? locked,
        excluded_dish_ids: over.excluded ?? excluded, explain: true });
      if (seq === sequence.current) {
        // Every dish count on screen comes from this one plan (the AI decides how many).
        setResult({ response, context, key: keyFor(context) }); setNeedsReplan(false);
      }
    } catch (e) { if (seq === sequence.current) setError(errorText(e)); }
    finally { if (seq === sequence.current) setLoading(false); }
  };

  useEffect(() => {
    let active = true;
    Promise.all([getMenus(), getProfiles(), getHealth()]).then(([ms, ps, health]) => {
      if (!active) return;
      const session = loadSession();
      const own = (session.menus ?? []).filter(m => m?.restaurant_id?.startsWith(LOCAL_PREFIX) && Array.isArray(m.dishes));
      own.forEach(m => menuCache.current.set(m.restaurant_id, m));
      const all = [...ms, ...own.map(m => ({ slug: m.restaurant_id, restaurant_name: m.restaurant_name, cuisine: m.cuisine, verified: m.verified, n_dishes: m.dishes.length }))];
      restored.current = session;
      setMenus(all); setDiners(Array.isArray(session.diners) ? session.diners : []); setPresets(ps); setMock(health.mock); setPhotoReader(health.photo ?? null);
      if (session.settings) setSettings({ ...initialSettings, ...session.settings });
      const start = all.some(m => m.slug === session.menuId) ? session.menuId! : all[0]?.slug;
      if (start) setMenuId(start); else setStarting(false);
    }).catch(e => { if (active) { setError(`Could not load the table: ${errorText(e)}`); setStarting(false); } });
    getSavedPeople().then(people => { if (active) setSaved(people); }).catch(() => undefined);
    return () => { active = false; sequence.current++; };
  }, []);

  useEffect(() => {
    if (!menuId) return;
    const seq = ++menuSequence.current;
    invalidate(); setStarting(true); setMenu(null); setResult(null); setLocked([]); setExcluded([]); setStep("menu");
    const cached = menuCache.current.get(menuId);
    (cached ? Promise.resolve(cached) : menuId.startsWith(LOCAL_PREFIX) ? Promise.reject(new Error("This imported menu is no longer available.")) : getMenu(menuId)).then(m => {
      if (seq !== menuSequence.current) return;
      menuCache.current.set(menuId, m); setMenu(m); setStarting(false);
      const back = restored.current; restored.current = null;
      if (back?.menuId === menuId && back.step && back.step !== "menu" && back.diners?.length) setStep("table");
    }).catch(e => { if (seq === menuSequence.current) { setError(errorText(e)); setStarting(false); } });
    return () => { menuSequence.current++; };
  }, [menuId]);

  useEffect(() => {
    if (starting && !menu) return; // not restored yet: don't overwrite the saved session
    const own = menus.filter(m => m.slug.startsWith(LOCAL_PREFIX)).map(m => menuCache.current.get(m.slug)).filter((m): m is Menu => !!m);
    try { localStorage.setItem(SESSION_KEY, JSON.stringify({ menus: own, menuId, diners, settings, step } satisfies Session)); } catch { /* storage full or blocked */ }
  }, [menus, menuId, menu, diners, settings, step, starting]);

  const startSample = async () => {
    try {
      const sample = menuCache.current.get(menuId) ?? await getMenu(menuId);
      menuCache.current.set(menuId, sample); setMenu(sample); const people = fromSaved(presets); setDiners(people); remember(people.filter(p => !saved.some(s => s.id === p.id)));
      const sampleSettings = initialSettings;
      setSettings(sampleSettings); setLocked([]); setExcluded([]); setUndo(null);
      void generate({ menu: sample, diners: people, settings: sampleSettings, locked: [], excluded: [] });
    } catch (e) { setError(errorText(e)); }
  };

  const planSteps = [
    `Reading ${diners.length === 1 ? "your" : "everyone's"} allergies and diets…`,
    `Picking dishes within $${settings.budget.toFixed(2)} per person, tax and tip included…`,
    "Checking every dish against allergies, diets and the budget…",
    "Still checking. If a dish fails a check, the AI is told why and picks again…",
  ];
  const currentContext = menu ? { menu, menuId, diners, settings } : null;
  const stale = !!result && (needsReplan || !currentContext || result.key !== keyFor(currentContext));
  const plan = result?.response.kind === "plan" ? result.response.plan ?? null : null;
  const snapshot = result?.context;
  const orderBlocked = orderBlock(plan ?? null, stale, loading); // warnings (enough food) never block
  const canOrder = orderBlocked === null;

  const changePeople = async (action: "add" | "update" | "remove" | "load_preferences", extra: {person?: DinerProfile; person_id?: string; saved?: DinerProfile[]}) => {
    invalidate(); setNeedsReplan(true);
    const seq = sequence.current;
    try {
      const {diners: next} = await applyPeopleAction(diners, action, extra);
      if (seq !== sequence.current) return;
      const nextSettings = settings;
      setDiners(next); setSettings(nextSettings); setEditing(null);
      if (!next.length) { setResult(null); setLocked([]); setExcluded([]); }
      else if (step === "plan" && menu?.verified) void generate({diners: next, settings: nextSettings});
    } catch (e) { if (seq === sequence.current) setError(errorText(e)); if (action === "load_preferences") throw e; }
  };
  /** Save people as their one current record, so they can be picked next time. */
  const remember = (people: DinerProfile[]) => {
    if (!people.length) return;
    setSaved(prev => { const byId = new Map(prev.map(p => [p.id, p])); people.forEach(p => byId.set(p.id, p)); return [...byId.values()].sort((a, b) => a.name.localeCompare(b.name)); });
    Promise.all(people.map(savePerson)).catch(e => setError(`Saved for tonight, but not for next time: ${errorText(e)}`));
  };
  const saveDiner = (d: DinerProfile) => { void changePeople(diners.some(p => p.id === d.id) ? "update" : "add", {person: d}); remember([d]); };
  const removeDiner = (id: string) => { void changePeople("remove", {person_id: id}); };
  const pickSaved = (p: DinerProfile) => { if (diners.length < 6 && !diners.some(d => d.id === p.id)) void changePeople("add", {person: p}); };
  const forgetPerson = async (id: string) => {
    try { await deletePerson(id); } catch (e) { if (!/Unknown person/.test(errorText(e))) { setError(errorText(e)); return; } }
    setSaved(prev => prev.filter(p => p.id !== id)); setEditing(null);
    if (diners.some(d => d.id === id)) removeDiner(id);
  };
  /** Sample people use their saved record when one exists, so nothing saved is overwritten. */
  const fromSaved = (people: DinerProfile[]) => people.map(p => saved.find(s => s.id === p.id) ?? p);
  const choosePreset = (id: string) => {
    const next: DinerProfile[] = fromSaved(id === "saved" ? presets : id === "two" ? presets.slice(0, 2) : []);
    invalidate(); setDiners(next); setLocked([]); setExcluded([]);
    remember(next.filter(p => !saved.some(s => s.id === p.id)));
    if (!next.length) setResult(null);
  };
  const pickDish = (newId: string) => {
    const old = browser?.old;
    // With a current plan, a pick swaps or adds just that dish; nothing else moves.
    if (plan && !stale) { void swapDish(old ?? null, newId); return; }
    setUndo({ locked: [...locked], excluded: [...excluded], message: "Dish added. The table has been rebalanced." });
    const ex = [...new Set([...excluded.filter(x => x !== newId), ...(old ? [old] : [])])];
    const lk = [...locked.filter(x => x !== old && x !== newId), newId];
    setExcluded(ex); setLocked(lk); setBrowser(null);
    void generate({ locked: lk, excluded: ex });
  };
  /** Replace one dish; every other dish stays exactly as it is. With `pick` the user's own
   *  choice is checked by the rules (no model call); without it the AI picks (one call). */
  const swapDish = async (id: string | null, pick?: string) => {
    const current = result;
    const p = current?.response.plan;
    if (!current || !p || stale) return;
    const { menu: m, menuId: mid, diners: d, settings: s } = current.context;
    const seq = ++sequence.current;
    const dishName = (x: string) => { const dish = m.dishes.find(y => y.id === x); return dish?.name_en || dish?.name_zh || x; };
    setSwapSteps(pick
      ? [`Checking ${dishName(pick)} against everyone's allergies and diets…`, `Checking it fits $${s.budget.toFixed(2)} per person with tax and tip…`]
      : [`Asking the AI for a replacement for ${dishName(id ?? "")}…`, "Checking its pick against everyone's allergies and diets…", `Checking it fits $${s.budget.toFixed(2)} per person with tax and tip…`]);
    // The earlier change's Undo stays until this one succeeds (a refusal must not drop it).
    setBrowser(null); setSwapping(id ?? ADDING); setSwapFailed(null); setError(null);
    try {
      const out = await postSwap({ menu_id: mid, menu_override: m, diners: d,
        budget_per_person: s.budget, tax_rate: s.tax, tip_rate: s.tip, style_preference: s.style,
        locked_dish_ids: locked, excluded_dish_ids: excluded, plan: p, dish_id: id, new_dish_id: pick ?? null });
      if (seq !== sequence.current) return;
      if (out.kind === "plan" && out.plan && out.new_dish_id) {
        setUndo({ locked: [...locked], excluded: [...excluded], result: current,
          message: `${pick ? "" : "AI: "}${out.message} Nothing else changed.` });
        // An explicit pick brings back a dish removed earlier; the replaced one is removed.
        setExcluded(prev => [...new Set([...prev.filter(x => x !== out.new_dish_id), ...(id ? [id] : [])])]);
        if (id) setLocked(prev => prev.filter(x => x !== id));
        setResult({ ...current, response: { ...current.response, plan: out.plan, source_note: out.source_note ?? current.response.source_note } });
      } else setSwapFailed({ id, message: out.message, manual: !!pick });
    } catch (e) { if (seq === sequence.current) setSwapFailed({ id, message: `${errorText(e)} Pick a replacement from the menu instead.`, manual: !!pick }); }
    finally { if (seq === sequence.current) setSwapping(null); }
  };
  /** "What should change?": the AI revises the current order; Undo restores it as it was. */
  const refinePlan = async (chips: FeedbackChip[], text: string) => {
    const current = result;
    const p = current?.response.plan;
    if (!current || !p || stale) return;
    const { menu: m, menuId: mid, diners: d, settings: s } = current.context;
    const seq = ++sequence.current;
    setLoading(true); setError(null);
    try {
      const response = await postPlan({ menu_id: mid, menu_override: m, diners: d,
        budget_per_person: s.budget, tax_rate: s.tax, tip_rate: s.tip, style_preference: s.style,
        locked_dish_ids: locked, excluded_dish_ids: excluded, explain: true,
        feedback: { chips, text, current: p.items.map(i => ({ dish_id: i.dish_id, quantity: i.quantity })) } });
      if (seq !== sequence.current) return;
      if (response.kind === "plan" && response.plan) {
        setUndo({ locked: [...locked], excluded: [...excluded], result: current,
          message: response.change_note ?? "The order was updated." });
        setResult({ ...current, response });
      } else setError(response.conflict?.message ?? "That change could not produce a new order; the current one stays.");
    } catch (e) { if (seq === sequence.current) setError(`${errorText(e)} The current order stays.`); }
    finally { if (seq === sequence.current) setLoading(false); }
  };
  const removeDish = (id: string) => {
    setUndo({ locked: [...locked], excluded: [...excluded], message: "Dish removed from suggestions. The table has been rebalanced." });
    const ex = [...new Set([...excluded, id])], lk = locked.filter(x => x !== id);
    setExcluded(ex); setLocked(lk); void generate({ excluded: ex, locked: lk });
  };
  /** Imported menus become their own restaurant next to the bundled ones; the current one is untouched. */
  const addMenu = (m: Menu): string => {
    const taken = new Set(menus.map(x => x.slug));
    let n = 1; while (taken.has(`${LOCAL_PREFIX}${n}`)) n++;
    const slug = `${LOCAL_PREFIX}${n}`;
    const own = { ...m, restaurant_id: slug };
    menuCache.current.set(slug, own);
    setMenus(prev => [...prev, { slug, restaurant_name: own.restaurant_name, cuisine: own.cuisine, verified: own.verified, n_dishes: own.dishes.length }]);
    return slug;
  };
  const updateMenu = (m: Menu) => {
    invalidate(); menuCache.current.set(menuId, m); setMenu(m);
    setMenus(prev => prev.map(x => x.slug === menuId ? { ...x, verified: m.verified, n_dishes: m.dishes.length } : x));
    // Edited or added rows get the AI's dish facts (the server re-derives them for planning anyway).
    if (m.dishes.some(d => !d.main_ingredients.length)) {
      const id = menuId;
      menuFacts(m).then(f => { const withFacts = { ...m, dishes: f.dishes }; if (menuCache.current.get(id) === m) { menuCache.current.set(id, withFacts); setMenu(cur => cur === m ? withFacts : cur); } }).catch(() => {});
    }
  };
  const selectMenu = (id: string) => { if (id !== menuId) { setBrowser(b => b && { ...b, initialTab: "browse", photos: undefined, fromStart: false }); setMenuId(id); } };
  const applyRelaxation = (r: Relaxation) => {
    if (r.kind === "budget" && r.new_value != null) {
      const s = { ...settings, budget: Math.min(500, r.new_value) };
      invalidate(); setSettings(s); void generate({ settings: s });
    } else if (r.diner_id) { const d = diners.find(d => d.id === r.diner_id); if (d) setEditing(d); }
  };

  return <div className="min-h-screen"><TopBar menu={menu} count={diners.length} onMenu={() => setBrowser({ mode: "browse", old: null })} onParty={() => step === "plan" ? setParty(true) : setStep("table")}/>
    <main className="workspace">
      {step === "plan" && <div className="plan-steps"><Stepper step="plan" onStep={s => setStep(s)} canPlan={!!result}/><button type="button" className="text-button setup-back plan-back" onClick={() => setStep("table")}><ArrowLeft size={15}/>Back to table</button></div>}
      {menu?.preparation_mode === "prepared_replay" && <div className="notice" role="status"><AlertCircle size={17}/><span>Assistant-prepared menu response replay. No live model or image OCR. Prices are a dated factual extract; ingredients and fees need confirmation.</span></div>}
      {mock && <div className="notice" role="status"><AlertCircle size={17}/><span>This demonstration uses a fixed set of sample dishes.</span></div>}
      {error && <div className="notice error-notice" role="alert"><AlertCircle size={17}/><span>{error}</span>{menu && <button className="btn btn-quiet btn-small" onClick={() => void generate()} disabled={loading}>Try again</button>}</div>}
      {stale && <div className="notice" role="status"><RefreshCw size={17} className={loading ? "spin" : ""}/>{loading ? <Progress key="replan" steps={planSteps} inline/> : <span>Your table or budget changed. Update the dishes to match.</span>}{!loading && <button className="btn btn-quiet btn-small" onClick={() => void generate()} disabled={!menu?.verified}>Update dishes</button>}</div>}
      {menu && !menu.verified && <div className="notice"><BookOpen size={17}/><span>Menu changes need review before a new plan can be generated.</span><button className="btn btn-quiet btn-small" onClick={() => setBrowser({ mode: "browse", old: null })}>Review menu</button></div>}
      {undo && !loading && <div className="change-notice" role="status"><span>{error || result?.response.kind === "conflict" ? "That change could not produce a new plan." : undo.message}</span><button className="text-button" onClick={() => { const previous = undo; setLocked(previous.locked); setExcluded(previous.excluded); setUndo(null); if (previous.result) setResult(previous.result); else void generate({ locked: previous.locked, excluded: previous.excluded }); }}>Undo</button><button className="dismiss-change" aria-label="Dismiss update" onClick={() => setUndo(null)}>×</button></div>}
      {swapFailed && !swapping && <div className="change-notice swap-failed" role="alert"><span>{swapFailed.message}</span><button className="text-button" onClick={() => { const id = swapFailed.id; setSwapFailed(null); setBrowser({ mode: "pick", old: id }); }}>{swapFailed.manual ? "Pick another dish" : "Pick from the menu"}</button><button className="dismiss-change" aria-label="Dismiss" onClick={() => setSwapFailed(null)}>×</button></div>}
      {swapping && <div className="change-notice" role="status"><Progress key={swapSteps.join()} steps={swapSteps} every={2200} inline/><span className="progress-note">Everything else stays.</span></div>}
      {(starting || (loading && !result)) ? <div className="empty-state" role="status">{starting || mock ? <><LoaderCircle size={30} className="spin mx-auto"/><h2>{starting ? "Setting the table…" : "Finding a table that works…"}</h2><p>Considering the menu, budget, and everyone's requirements.</p></> : <><h2>Finding a table that works…</h2><Progress key="plan" steps={planSteps}/></>}</div> : step !== "plan" && menu ? <SetupFlow step={step} onStep={s => s === "plan" ? (result && !stale ? setStep("plan") : void generate()) : setStep(s)} canPlan={!!result && diners.length > 0} photoReader={photoReader} onPhoto={files => setBrowser({ mode: "browse", old: null, initialTab: "import", photos: files, fromStart: true })} onPaste={() => setBrowser({ mode: "browse", old: null, initialTab: "import", fromStart: true })} menu={menu} diners={diners} saved={saved} onPick={pickSaved} onRemove={removeDiner} settings={settings} onMenu={() => setBrowser({ mode: "browse", old: null })} onSample={() => void startSample()} onChange={editSettings} onEdit={setEditing} onAdd={() => setEditing("new")} onPreset={choosePreset} onPlan={() => result && !stale ? setStep("plan") : void generate()} loading={loading} current={!!result && !stale && diners.length > 0} onApprove={() => { if (menu) { updateMenu({ ...menu, verified: true }); setStep("table"); } }}/> : stale && !loading ? <div className="empty-state"><h2>Update your meal</h2><p>The previous recommendation is no longer current.</p><button className="btn btn-primary" onClick={() => void generate()}>Update dishes</button></div> : plan && snapshot && diners.length ? <>
        <Ticket key={result?.key + JSON.stringify(plan.items)} menu={snapshot.menu} plan={plan} diners={snapshot.diners.filter(d => diners.some(c => c.id === d.id))} settings={snapshot.settings} source={result?.response.source ?? "ai"} sourceNote={result?.response.source_note ?? null} locked={locked} stale={stale} loading={loading} onLock={id => { setUndo(null); setLocked(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]); }} onSwap={id => setBrowser({ mode: "pick", old: id })} onAiSwap={id => void swapDish(id)} swapping={swapping} onRemove={removeDish} onAdd={() => setBrowser({ mode: "pick", old: null })} onRefine={(chips, text) => void refinePlan(chips, text)} onOrder={() => setWaiter(true)} canOrder={canOrder} orderBlocked={orderBlocked} onParty={() => setParty(true)}/>
      </> : result?.response.conflict ? <><ConflictNote conflict={result.response.conflict} menu={result.context.menu} diners={result.context.diners} settings={result.context.settings} onRelax={applyRelaxation}/><div className="conflict-actions">{result.response.conflict.code?.startsWith("ai_") && <button className="btn btn-primary" onClick={() => void generate()} disabled={loading}><RefreshCw size={16} className={loading ? "spin" : ""}/>Try again</button>}<button className="btn btn-quiet" onClick={() => setParty(true)}><Users size={16}/>Edit people and budget</button><button className="btn btn-quiet" onClick={() => { setLocked([]); setExcluded([]); void generate({ locked: [], excluded: [] }); }} disabled={loading}><RefreshCw size={16}/>Reset dish choices</button><button className="btn btn-quiet" onClick={() => setBrowser({ mode: "browse", old: null })}><BookOpen size={16}/>Browse menu</button></div></> : <div className="empty-state"><UtensilsCrossed size={30} className="mx-auto"/><h2>{diners.length ? "Your next meal starts here" : "Who's joining the table?"}</h2><p>{diners.length ? "Review your group and choose a menu to plan a shared meal." : "Add diners and their dietary requirements to get started."}</p><button className="btn btn-primary" onClick={() => setParty(true)}><Users size={16}/>Set up the table</button>{!!diners.length && menu && <button className="btn btn-quiet ml-3" onClick={() => void generate()}>Plan the table</button>}</div>}
      {(locked.length > 0 || excluded.length > 0) && <div className="choices-summary"><span>{choicesLine(locked, excluded, menu)}</span><button className="btn btn-outline btn-small" disabled={loading} onClick={() => { setLocked([]); setExcluded([]); void generate({ locked: [], excluded: [] }); }}>Reset dish choices</button></div>}
    </main>
    {party && <Sheet title="Your table" onClose={() => setParty(false)}><TableSetup diners={diners} saved={saved} onPick={pickSaved} onRemove={removeDiner} settings={settings} currency={menu?.currency ?? "USD"} onChange={editSettings} onEdit={setEditing} onAdd={() => setEditing("new")} onPreset={choosePreset} onPlan={() => { setParty(false); if (!result || stale) void generate(); }} loading={loading} current={!!result && !stale && diners.length > 0}/></Sheet>}
    {browser && menu && <SwapSheet key={menuId} menu={menu} menus={menus} menuId={menuId} plan={stale ? null : plan} diners={diners} excluded={excluded} old={browser.old} mode={browser.mode} initialTab={browser.initialTab} initialPhotos={browser.photos ?? []} openAfterImport={!!browser.fromStart} tax={settings.tax} tip={settings.tip} budget={settings.budget * Math.max(diners.length, 1)} onPick={pickDish} onAiSwap={id => void swapDish(id)} onClose={() => setBrowser(null)} onUpdate={updateMenu} onCreate={addMenu} onSelectMenu={selectMenu}/>}
    {editing && <DinerSheet diner={editing === "new" ? null : editing} existingIds={[...new Set([...diners, ...saved].map(d => d.id))]} saved={[...diners, ...saved.filter(s => !diners.some(d => d.id === s.id))]} tonight={diners.map(d => d.id)} atTable={editing !== "new" && diners.some(d => d.id === editing.id)} onSave={saveDiner} onPick={p => { pickSaved(p); setEditing(null); }} onRemove={removeDiner} onForget={id => void forgetPerson(id)} onClose={() => setEditing(null)}/>}
    {waiter && canOrder && snapshot && plan && <WaiterView menu={snapshot.menu} plan={plan} diners={snapshot.diners} onClose={() => setWaiter(false)}/>}
  </div>;
}

/** The kept/removed dishes in plain words, e.g. "Fish Fillet won't be suggested again." */
function choicesLine(locked: string[], excluded: string[], menu: Menu | null): string {
  const name = (id: string) => { const d = menu?.dishes.find(x => x.id === id); return d ? (d.name_en || d.name_zh || id) : id; };
  const list = (ids: string[]) => ids.length <= 2 ? ids.map(name).join(" and ") : `${ids.slice(0, 2).map(name).join(", ")} and ${ids.length - 2} more`;
  const parts = [];
  if (locked.length) parts.push(`Keeping ${list(locked)}.`);
  if (excluded.length) parts.push(`${list(excluded)} won't be suggested again.`);
  return parts.join(" ");
}
