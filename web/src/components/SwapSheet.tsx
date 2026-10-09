import { useEffect, useRef, useState } from "react";
import { ArrowLeftRight, Check, CheckCircle2, CircleHelp, FileImage, Flame, Leaf, Pencil, Plus, Search, Sparkles, TriangleAlert, Upload, UserX, Users } from "lucide-react";
import { evaluateMenu, parseMenu, getPreparedInputs, extractMenu } from "../api";
import { CATEGORY_LABEL, MARK_LABEL, currencySymbol, dishName, flagWording, groupFamilies, listNames, markWording, money, niceName, siblings } from "../lib/format";
import { photoFor } from "../lib/dishPhotos";
import { concernedBy, mayHideMeat } from "../lib/dietary";
import type { DinerProfile, Dish, Eligibility, Menu, MenuSummary, Plan, PreparedInput } from "../types";
import { DishEditor } from "./DishEditor";
import { Sheet } from "./Sheet";

interface Props {
  menu: Menu;
  menus: MenuSummary[];
  menuId: string;
  plan: Plan | null;
  diners: DinerProfile[];
  excluded: string[];
  old: string | null;
  mode: "browse" | "pick";
  initialTab?: "browse" | "import";
  /** Photos (or PDFs) picked on the menu step: one is read straight away; several wait so
   * more pages can be added or removed first. */
  initialPhotos?: File[];
  /** Started from "Have the menu in front of you?": importing opens the new restaurant. */
  openAfterImport?: boolean;
  tax: number;
  tip: number;
  /** The table's all-in budget (tax and tip included), to flag dishes that would break it. */
  budget?: number;
  onPick: (id: string) => void;
  /** Replacing a dish: let the AI pick instead (only that dish changes). */
  onAiSwap?: (id: string) => void;
  onClose: () => void;
  onUpdate: (menu: Menu) => void;
  /** Add an imported menu as a separate restaurant; returns its id. Does not switch to it. */
  onCreate: (menu: Menu) => string;
  onSelectMenu: (id: string) => void;
}

const MAX_DISHES = 150; // same as the server (MAX_MENU_DISHES)
const MAX_IMAGE_BYTES = 8 * 1024 * 1024;
const MAX_PAGES = 8; // same as the server
const isPdf = (f: File) => f.type === "application/pdf" || /\.pdf$/i.test(f.name);

const asBase64 = (f: File) => new Promise<string>((resolve, reject) => {
  const reader = new FileReader();
  reader.onload = () => resolve(String(reader.result).split(",")[1]);
  reader.onerror = () => reject(new Error(`${f.name} could not be read.`));
  reader.readAsDataURL(f);
});

/** Page thumbnails (object URLs), freed when the pages change. */
function usePreviews(files: File[]): string[] {
  const [urls, setUrls] = useState<string[]>([]);
  useEffect(() => {
    const made = files.map((f) => (isPdf(f) ? "" : URL.createObjectURL(f)));
    setUrls(made);
    return () => made.forEach((u) => u && URL.revokeObjectURL(u));
  }, [files]);
  return urls;
}
const SPICE = ["", "Mild", "Medium", "Hot"];
// Animal products and allergens that a dish name often does not reveal.
const HIDDEN = /pork|lard|beef|chicken|duck|lamb|meat|broth|stock|shrimp|prawn|crab|oyster|fish|anchov|scallop|egg|milk|butter|cream|cheese|peanut|sesame|nut/i;

/** Ingredients the AI thinks a dish may hide, in plain words, naming who they matter to
 * ("may hide pork fat, ask (Pat)"). Notes that matter to nobody at the table are left out. */
export function hiddenIngredients(d: Dish, diners: DinerProfile[] = []): string | null {
  const name = `${d.name_en ?? ""} ${d.description_raw ?? ""}`.toLowerCase();
  const printed = (ingredient: string) => ingredient.toLowerCase().split(/\W+/).some((w) => w.length >= 4 && name.includes(w));
  const stem = (n: string) => n.toLowerCase().replace(/s\b/g, "");
  const shown = d.main_ingredients.filter((i) => i.tier !== "menu" && HIDDEN.test(i.name) && !printed(i.name));
  // "pork" adds nothing next to "minced pork"; "peanut" nothing next to "peanuts".
  const distinct = shown.filter((i, k) => !shown.some((o, j) => j !== k && (stem(o.name) === stem(i.name) ? j < k : stem(o.name).includes(stem(i.name)))));
  const notes = distinct
    .flatMap((i) => {
      const who = diners.length ? concernedBy(i.name, diners) : [];
      if (diners.length && !who.length) return [];
      const text = i.tier === "inferred" ? `usually made with ${i.name}` : `may hide ${i.name}, ask`;
      return [who.length ? `${text} (${listNames(who.map((p) => p.name))})` : text];
    });
  return notes.length ? [...new Set(notes)].slice(0, 3).join("; ") : null;
}

const cents = (n: number) => Math.round(n * 100 + 1e-6) / 100;

/** How far an order with this menu-price subtotal would go over the all-in budget (0 if not). */
function overBudget(subtotal: number, tax: number, tip: number, budget: number): number {
  const s = cents(subtotal);
  const total = s + cents(s * tax) + cents(s * tip);
  return Math.max(0, cents(total - budget));
}

const CONCERNS = ["peanut", "tree nut", "sesame", "shellfish", "fish", "egg", "dairy", "milk", "soy", "wheat", "gluten", "pork", "chicken", "beef", "lamb", "duck", "meat", "alcohol"];

/** One plain line per diner, e.g. "has pork", "may have peanut, ask", or both: what is only
 * possible always reads "may have", whatever else the diner can't have. */
export function plainReason(reasons: string[], confirm: boolean, person?: DinerProfile): string {
  // The diner's own terms ("mango", "halal") read as they wrote them.
  const own = [...(person?.other_allergies ?? []), ...(person?.other_diets ?? [])].map((t) => t.replace(/ /g, "_"));
  const isOwn = (r: string) => own.some((t) => r.toLowerCase().replace(/ /g, "_").includes(t));
  const parts = reasons.filter(isOwn).map(ownReason);
  // "may have mango, ask; may have cilantro, ask" -> "may have mango and cilantro, ask"
  const maybe = parts.filter((x) => /^may have .+, ask$/.test(x)).map((x) => x.slice(9, -5));
  const ownParts = [...parts.filter((x) => !/^may have .+, ask$/.test(x)), ...(maybe.length ? [`may have ${joinWords(maybe)}, ask`] : [])];
  const rest = reasons.filter((r) => !isOwn(r));
  if (!ownParts.length) return plainCore(rest, confirm);
  return [...new Set([...(rest.length ? [plainCore(rest, confirm)] : []), ...ownParts])].join("; ");
}

/** "Contains mango" -> "has mango"; "May contain mango" / "Confirm mango, …" -> "may have
 * mango, ask"; "Breaks halal" -> "not halal"; "Confirm no_alcohol preparation" -> "may have
 * alcohol, ask"; "Confirm halal preparation" -> "ask if it's halal". */
function ownReason(r: string): string {
  let m = /^Contains (.+?)( \(on the menu\))?$/.exec(r);
  if (m) return `has ${m[1]}`;
  m = /^May contain (.+)$/.exec(r) ?? /^Confirm (.+?)(?:, including sauces|, can it be left out| ingredient\/preparation)/.exec(r);
  if (m) return `may have ${m[1].replace(/_/g, " ")}, ask`;
  m = /^Breaks (.+?)( \(on the menu\))?$/.exec(r);
  if (m) return m[1].startsWith("no ") ? `has ${m[1].slice(3)}` : `not ${m[1]}`;
  m = /^Confirm (.+?) preparation$/.exec(r);
  if (m) {
    const diet = m[1].replace(/_/g, " ");
    return diet.startsWith("no ") ? `may have ${diet.slice(3)}, ask` : `ask if it's ${diet}`;
  }
  return r;
}

function plainCore(reasons: string[], confirm: boolean): string {
  const sure = reasons.filter((r) => !/^confirm/i.test(r));
  const maybe = reasons.filter((r) => /^confirm/i.test(r));
  if (!sure.length) return reasonLine(maybe, maybe.length > 0 || confirm);
  const has = reasonLine(sure, false);
  if (!maybe.length) return has;
  const hasItems = has.startsWith("has ") ? has.slice(4).split(/, | and /) : [];
  const may = reasonLine(maybe, true);
  if (!may.startsWith("may have ")) return has;
  const rest = may.slice(9, -5).split(/, | and /).filter((w) => !hasItems.includes(w));
  return rest.length ? `${has}; may have ${joinWords(rest)}, ask` : has;
}

const joinWords = (w: string[]) => (w.length <= 1 ? w.join("") : `${w.slice(0, -1).join(", ")} and ${w[w.length - 1]}`);

function reasonLine(reasons: string[], confirm: boolean): string {
  const text = reasons.join(" ").toLowerCase().replace(/_/g, " ").replace(/\bno pork\b/g, "pork");
  const items = CONCERNS.filter(w => new RegExp(`\\b${w}s?\\b`).test(w === "fish" ? text.replace(/shellfish/g, "") : text));
  const named = items.some(w => ["pork", "chicken", "beef", "lamb", "duck"].includes(w));
  const shown = named ? items.filter(w => w !== "meat") : items; // "has beef", not "has beef and meat"
  const list = joinWords(shown);
  if (!list) return confirm ? `ask if it's ${/vegan/.test(text) ? "vegan" : /vegetarian/.test(text) ? "vegetarian" : "safe"}` : /vegan/.test(text) ? "not vegan" : /vegetarian/.test(text) ? "not vegetarian" : "can't eat it";
  return confirm ? `may have ${list}, ask` : `has ${list}`;
}

/** The restaurant menu drawer: browse and edit the menu, import one, or pick a dish to add or swap in. */
export function SwapSheet({ menu, menus, menuId, plan, diners, excluded, old, mode, initialTab = "browse", initialPhotos = [], openAfterImport = false, tax, tip, budget, onPick, onAiSwap, onClose, onUpdate, onCreate, onSelectMenu }: Props) {
  const [created, setCreated] = useState<{ id: string; name: string } | null>(null);
  const [prepared, setPrepared] = useState<PreparedInput[]>([]);
  const [preparedId, setPreparedId] = useState("");
  const [extractedMenu, setExtractedMenu] = useState<Menu | null>(null);
  const [extractionNotice, setExtractionNotice] = useState("");
  useEffect(() => { let active = true; getPreparedInputs().then(rows => {if (active) setPrepared(rows);}).catch(() => {}); return () => {active = false;}; }, []);
  const replay = async () => {
    const input = prepared.find(p => p.menu_id === preparedId);
    if (!input) return;
    setParsing(true); setError(""); setImported([]); setExtractedMenu(null); setExtractionNotice("");
    try {
      const result = await extractMenu({menu_id: input.menu_id, text: input.input_text});
      setExtractedMenu(result.menu); setImported(result.menu.dishes); setImportMode("replace");
      setExtractionNotice(result.notice); setRestaurantName(niceName(result.menu.restaurant_name)); setCreated(null);
    } catch(e) {setError(e instanceof Error ? e.message : String(e));}
    finally {setParsing(false);}
  };
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [sameCategory, setSameCategory] = useState(false);
  const [allDiners, setAllDiners] = useState(false);
  const [eligibility, setEligibility] = useState<Eligibility | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<"browse" | "import">(initialTab);
  const [text, setText] = useState("");
  const [photos, setPhotos] = useState<File[]>(initialPhotos);
  const previews = usePreviews(photos);
  const photo = photos[0] ?? null;
  const addPages = (picked: File[]) => {
    const tooBig = picked.filter((f) => f.size > MAX_IMAGE_BYTES);
    const ok = picked.filter((f) => f.size <= MAX_IMAGE_BYTES);
    const next = [...photos, ...ok].slice(0, MAX_PAGES);
    setPhotos(next);
    setImported([]);
    setError(tooBig.length ? `Choose files smaller than 8 MB (${tooBig.map((f) => f.name).join(", ")} skipped).` : photos.length + ok.length > MAX_PAGES ? `Use up to ${MAX_PAGES} pages for one menu.` : "");
  };
  const [readNotice, setReadNotice] = useState("");
  const [parsing, setParsing] = useState(false);
  const [imported, setImported] = useState<Dish[]>([]);
  const [editor, setEditor] = useState<Dish | "new" | null>(null);
  const [verified, setVerified] = useState(false);
  const [importMode, setImportMode] = useState<"append" | "replace">(initialTab === "import" ? "replace" : "append");
  const [restaurantName, setRestaurantName] = useState("");

  const importedCount = imported.length + (importMode === "append" ? menu.dishes.length : 0);
  const onSlip = new Set(plan?.items.map((i) => i.dish_id) ?? []);
  const oldDish = menu.dishes.find((d) => d.id === old);
  const oldQuantity = plan?.items.find((i) => i.dish_id === old)?.quantity ?? 1;
  const cur = currencySymbol(menu.currency);

  useEffect(() => {
    let active = true;
    setEligibility(null);
    setError("");
    evaluateMenu(menu, diners)
      .then((r) => { if (active) setEligibility(r); })
      .catch((e) => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [menu, diners]);

  const candidates = menu.dishes.filter((d) =>
    (mode === "browse" || !onSlip.has(d.id)) &&
    (category === "all" || d.category === category) &&
    (!sameCategory || !oldDish || d.category === oldDish.category) &&
    (!allDiners || eligibility?.[d.id]?.edible_by.length === diners.length) &&
    `${dishName(d)} ${d.main_ingredients.map((i) => i.name).join(" ")}`.toLowerCase().includes(query.toLowerCase()),
  );
  candidates.sort((a, b) =>
    (eligibility?.[b.id]?.edible_by.length ?? 0) - (eligibility?.[a.id]?.edible_by.length ?? 0) || (a.price ?? Infinity) - (b.price ?? Infinity),
  );
  // Versions of one printed line stay together; when swapping a version, its siblings first.
  const listed = groupFamilies(candidates);
  if (oldDish?.family_id) listed.sort((a, b) => Number(b.family_id === oldDish.family_id) - Number(a.family_id === oldDish.family_id));
  const hiddenByCategory = sameCategory && oldDish ? menu.dishes.filter((d) => !onSlip.has(d.id) && d.category !== oldDish.category).length : 0;

  const update = (next: Menu) => { setVerified(false); onUpdate(next); };
  const autoRead = useRef(initialPhotos.length === 1);
  useEffect(() => { if (autoRead.current) { autoRead.current = false; void importRows(); } });

  const importRows = async () => {
    setParsing(true);
    setError("");
    setImported([]); setExtractedMenu(null); setExtractionNotice(""); setCreated(null); setReadNotice("");
    try {
      const pages = await Promise.all(photos.map(asBase64));
      const result = await parseMenu(pages.length ? { images_base64: pages } : { text });
      setImported(result.dishes);
      setText(result.text);
      setReadNotice(result.notice ?? "");
      if (result.restaurant_name && !restaurantName.trim()) setRestaurantName(niceName(result.restaurant_name));
      if (!result.dishes.length) setError("No name-and-price rows found. Put one dish per line, with the price at the end, then try again.");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setParsing(false);
    }
  };

  const saveDish = (d: Dish) => {
    if (editor === "new" && menu.dishes.length >= MAX_DISHES) {
      setError(`Use up to ${MAX_DISHES} dishes in one menu.`);
      setEditor(null);
      return;
    }
    update({ ...menu, verified: false, dishes: menu.dishes.some((x) => x.id === d.id) ? menu.dishes.map((x) => (x.id === d.id ? d : x)) : [...menu.dishes, d] });
    setEditor(null);
  };

  const title = oldDish ? `Swap ${dishName(oldDish)}` : mode === "pick" ? "Add a dish" : "Restaurant menu";

  return (
    <>
      <Sheet wide title={title} onClose={onClose}>
        {mode === "pick" && (
          <div className="swap-explainer">
            <ArrowLeftRight size={19} />
            <div>
              <strong>{oldDish ? `Replacing ${dishName(oldDish)}` : "Adding to your order"}</strong>
              <p>{oldDish ? "Only this dish changes. The rules check your pick against the budget, allergies and diets, and say why if it doesn't fit." : plan ? "Only this dish is added; nothing else changes. The rules check it against the budget, allergies and diets, and say why if it doesn't fit." : "Your choice is kept. Dishes you have not kept may change to stay within budget and everyone's needs."} The price difference shown is for this dish only.</p>
              {oldDish && onAiSwap && plan && (
                <button className="btn btn-outline btn-small ai-swap-inline" onClick={() => onAiSwap(oldDish.id)}>
                  <Sparkles size={14} />
                  Let AI swap this instead (only this dish changes)
                </button>
              )}
            </div>
          </div>
        )}
        {mode === "browse" && (
          <>
            <label className="field-label">
              Restaurant
              <select className="field" value={menuId} onChange={(e) => onSelectMenu(e.target.value)}>
                {menus.map((m) => (
                  <option key={m.slug} value={m.slug}>{m.restaurant_name}{m.slug.startsWith("local-") ? " (imported)" : ""}</option>
                ))}
              </select>
            </label>
            <div className="menu-tabs">
              <button className={tab === "browse" ? "selected" : ""} onClick={() => setTab("browse")}>Browse and edit</button>
              <button className={tab === "import" ? "selected" : ""} onClick={() => setTab("import")}><Upload size={14} />Import menu</button>
              <button onClick={() => setEditor("new")}><Plus size={14} />Add dish</button>
            </div>
          </>
        )}
        {error && <p className="notice error-notice" role="alert">{error}</p>}

        {tab === "import" ? (
          <div className="import-panel">
            {created && (
              <div className="notice" role="status">
                <span>Added “{created.name}” as a new restaurant. {menu.restaurant_name} is still selected.</span>
                <button className="btn btn-outline btn-small" onClick={() => onSelectMenu(created.id)}>Switch to {created.name}</button>
              </div>
            )}
            <div className="field-grid">
              <label className="field-label">
                Use imported dishes
                <select className="field" disabled={!!extractedMenu} value={importMode} onChange={(e) => setImportMode(e.target.value as "append" | "replace")}>
                  <option value="replace">Add as a new restaurant</option>
                  <option value="append">Add to {menu.restaurant_name}</option>
                </select>
              </label>
              {importMode === "replace" && (
                <label className="field-label">
                  New restaurant name
                  <input className="field" value={restaurantName} onChange={(e) => setRestaurantName(e.target.value)} placeholder="Restaurant name" />
                </label>
              )}
            </div>
            <label className="upload-area">
              <FileImage size={24} />
              <strong>{photos.length ? (photos.length < MAX_PAGES ? "Add another page" : `${MAX_PAGES} pages, the most for one menu`) : "Choose menu photos or a PDF"}</strong>
              <span>PNG, JPEG or WebP photos, or a PDF, up to 8 MB each and {MAX_PAGES} pages. Several pages are read together as one menu; names and prices are read from the pages, and the AI guesses likely ingredients from each name.</span>
              <input
                aria-label="Menu image"
                type="file"
                multiple
                disabled={photos.length >= MAX_PAGES}
                accept="image/png,image/jpeg,image/webp,application/pdf"
                onChange={(e) => {
                  addPages(Array.from(e.target.files ?? []));
                  e.target.value = "";
                }}
              />
            </label>
            {photos.length > 0 && (
              <ul className="page-thumbs" aria-label="Menu pages">
                {photos.map((f, k) => (
                  <li key={`${f.name}-${k}`}>
                    {previews[k] ? <img src={previews[k]} alt={`Page ${k + 1}`} /> : <span className="page-pdf"><FileImage size={22} />PDF</span>}
                    <small title={f.name}>{k + 1}. {f.name}</small>
                    <button type="button" className="text-button" aria-label={`Remove page ${k + 1} (${f.name})`} onClick={() => { setPhotos(photos.filter((_, j) => j !== k)); setImported([]); }}>Remove</button>
                  </li>
                ))}
              </ul>
            )}
            {photos.length > 0 ? (
              <button className="btn btn-outline btn-small" onClick={() => setPhotos([])}>Paste text instead</button>
            ) : (
              <label className="field-label">
                Or paste the menu text, one dish and price per line
                <textarea aria-label="Menu text" className="field" rows={6} value={text} onChange={(e) => { setText(e.target.value); setImported([]); }} placeholder={"Garlic greens $12.95\nSteamed rice $2.00"} />
              </label>
            )}
            <button className="btn btn-primary" disabled={parsing || (!text.trim() && !photo)} onClick={() => void importRows()}>
              <Upload size={15} />
              {parsing ? (photos.length > 1 ? `Reading ${photos.length} pages…` : "Reading menu…") : photos.length > 1 ? `Read ${photos.length} pages as one menu` : photo ? "Read the menu" : "Extract dishes"}
            </button>
            {readNotice && <p className="helper" role="status">{readNotice}</p>}
            <details className="photo-import">
              <summary>Use an assistant-prepared model response</summary>
              <section aria-label="Prepared model responses" className="import-review">
                <p className="helper">Exact-input replay from official-menu facts. No live model, OCR, or image recognition.</p>
                <label className="field-label">Prepared menu<select aria-label="Prepared menu" className="field" value={preparedId} disabled={parsing} onChange={e => setPreparedId(e.target.value)}>
                  <option value="">Choose a prepared input…</option>
                  {prepared.map(p => <option key={p.menu_id} value={p.menu_id}>{p.menu_id} · {p.retrieved_at}</option>)}
                </select></label>
                <button className="btn btn-outline" disabled={parsing || !preparedId} onClick={() => void replay()}>Replay prepared response</button>
                {extractionNotice && <p role="status">{extractionNotice}</p>}
              </section>
            </details>
            {imported.length > 0 && (
              <div className="import-review">
                <h3>{imported.length} dishes found{imported.some((d) => d.family_id) ? ` (${new Set(imported.filter((d) => d.family_id).map((d) => d.family_id)).size} with a choice, one dish per choice)` : ""}</h3>
                <ul>
                  {groupFamilies(imported).map((d, k, all) => {
                    if (d.family_id && all[k - 1]?.family_id === d.family_id) return null;
                    const mark = markWording(d);
                    const heading = d.menu_section && d.menu_section !== all.slice(0, k).reverse().find((x) => x.menu_section)?.menu_section
                      ? <li key={`section-${k}`} className="menu-section-head">{d.menu_section}</li> : null;
                    if (!d.family_id) return [heading, <li key={d.id}><span>{dishName(d)}{mark && <small className="menu-mark"> {mark}</small>}</span><strong>{money(d.price, cur)}</strong></li>];
                    const versions = all.filter((x) => x.family_id === d.family_id);
                    return [heading, (
                      <li key={d.family_id} className="family-row">
                        <span>{d.family_name ?? dishName(d)}{mark && <small className="menu-mark"> {mark}</small>}<small className="family-choices">Choice of {versions.map((x) => `${x.variant} ${money(x.price, cur)}`).join(" · ")}</small></span>
                        <strong>{versions.length} choices</strong>
                      </li>
                    )];
                  })}
                </ul>
                <button
                  className="btn btn-outline"
                  disabled={importedCount > MAX_DISHES}
                  onClick={() => {
                    if (importMode === "replace" || extractedMenu) {
                      // A new, independent restaurant. The current one keeps its name and dishes,
                      // and stays selected until the user switches.
                      const name = niceName(restaurantName.trim() || extractedMenu?.restaurant_name || "My restaurant");
                      const fresh: Menu = extractedMenu
                        ? { ...extractedMenu, restaurant_name: name, verified: false }
                        : { restaurant_id: "", restaurant_name: name, cuisine: "custom", source: "User-imported menu", currency: menu.currency, verified: false, dishes: imported };
                      const id = onCreate(fresh);
                      if (openAfterImport) { onSelectMenu(id); onClose(); } // the button says so; the menu is ready, so the window closes
                      else setCreated({ id, name });
                    } else {
                      update({ ...menu, verified: false, dishes: [...menu.dishes, ...imported] });
                      setTab("browse");
                    }
                    setImported([]); setExtractedMenu(null);
                  }}
                >
                  <Check size={15} />
                  {importMode === "replace" || extractedMenu
                    ? openAfterImport ? `Import and open ${restaurantName.trim() || extractedMenu?.restaurant_name || "this menu"}` : "Add restaurant for review"
                    : `Add to ${menu.restaurant_name} for review`}
                </button>
                {importedCount > MAX_DISHES && <p className="helper">Use up to {MAX_DISHES} dishes in one menu.</p>}
              </div>
            )}
          </div>
        ) : (
          <>
            <div className="menu-filters">
              <label className="search-field">
                <Search size={16} />
                <input aria-label="Search dishes or ingredients" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search dishes or ingredients" />
              </label>
              <select className="field" aria-label="Dish category" value={category} onChange={(e) => setCategory(e.target.value)}>
                <option value="all">All categories</option>
                {Object.entries(CATEGORY_LABEL).map(([id, label]) => (
                  <option key={id} value={id}>{label}</option>
                ))}
              </select>
            </div>
            <div className="menu-checkboxes">
              {oldDish && (
                <label>
                  <input type="checkbox" checked={sameCategory} onChange={(e) => setSameCategory(e.target.checked)} />
                  Same category only
                </label>
              )}
              <label className="fit-switch">
                <input type="checkbox" role="switch" checked={allDiners} disabled={!diners.length} onChange={(e) => setAllDiners(e.target.checked)} />
                Only dishes that fit every diner
              </label>
              <span>
                {candidates.length} {candidates.length === 1 ? "dish" : "dishes"}
                {hiddenByCategory > 0 && `, ${hiddenByCategory} more in other categories`}
              </span>
            </div>
            {!menu.verified && (
              <div className="menu-review">
                <strong>Review this menu before planning</strong>
                <p>Check prices, categories, portions, and dietary details. Unknown fields remain unknown.</p>
                <label>
                  <input type="checkbox" checked={verified} onChange={(e) => setVerified(e.target.checked)} />
                  I have reviewed this menu against the source.
                </label>
                <button
                  className="btn btn-outline btn-small"
                  disabled={!verified || !menu.dishes.length || menu.dishes.some((d) => d.price == null || !d.name_en?.trim())}
                  onClick={() => onUpdate({ ...menu, verified: true })}
                >
                  <CheckCircle2 size={14} />
                  Mark reviewed
                </button>
              </div>
            )}
            {!eligibility && !error && <p role="status" className="helper">Checking diner requirements…</p>}
            <ul className="menu-list">
              {listed.map((d) => {
                const e = eligibility?.[d.id];
                const others = siblings(d, menu.dishes);
                const versionOnSlip = others.filter((x) => onSlip.has(x.id) && x.id !== old);
                const qty = d.category === "staple" ? diners.length : 1;
                const delta = ((d.price ?? 0) * qty - (oldDish?.price ?? 0) * oldQuantity) * (1 + tax + tip);
                const photo = photoFor(d);
                const notFor = e ? diners.filter((p) => !e.edible_by.includes(p.id)) : [];
                // Diners who can eat it only if the server confirms (e.g. "Pat: may have pork, ask").
                const askFor = e ? diners.filter((p) => e.edible_by.includes(p.id) && e.assessments?.[p.id]?.status === "requires_confirmation") : [];
                const over = plan && budget != null && d.price != null && !onSlip.has(d.id) ? overBudget(plan.subtotal + d.price * qty - (oldDish?.price ?? 0) * (oldDish ? oldQuantity : 0), tax, tip, budget) : 0;
                const canPick = !!e && e.edible_by.length > 0 && d.price != null && menu.verified && diners.length > 0 && over <= 0;
                return (
                  <li key={d.id} className="menu-row">
                    {photo ? <img className="menu-thumb" src={photo.src} alt="" width={64} height={64} loading="lazy" /> : <span className="menu-thumb" aria-hidden="true" />}
                    <div className="menu-row-body">
                      <div className="menu-row-text">
                        <div>
                          <h3>{dishName(d)}</h3>
                          {d.name_zh && <p className="dish-sub"><span lang="zh">{d.name_zh}</span></p>}
                        </div>
                        <div className="dish-tags">
                          <span>{CATEGORY_LABEL[d.category] ?? d.category}</span>
                          {d.family_id && <span className="tag-family" title={`One of ${others.length + 1} choices on the menu line ${d.family_name ?? ""}`}>{others.length + 1} choices of {d.family_name}</span>}
                          {(d.menu_marks ?? []).map((m) => <span key={m} className="tag-mark" title={MARK_LABEL[m]?.title}>Menu: {MARK_LABEL[m]?.short ?? m}</span>)}
                          {d.is_vegetarian === true && <span className={mayHideMeat(d) ? "tag-ask" : ""}><Leaf size={12} />{d.is_vegan ? "Vegan" : "Vegetarian"}{mayHideMeat(d) ? "? ask" : ""}</span>}
                          {d.spice_level != null && d.spice_level > 0 && <span><Flame size={12} />{SPICE[d.spice_level]}</span>}
                          {e && diners.length > 0 && notFor.length === 0 && <span title="Matches every diner's recorded requirements"><Users size={12} />Matches all {diners.length}{mayHideMeat(d) ? " if confirmed" : ""}</span>}
                        </div>
                        {!e ? (
                          <p className="helper">Checking diner requirements…</p>
                        ) : (
                          (notFor.length > 0 || askFor.length > 0) && (
                            <div className="dish-notes">
                              {notFor.map(p => <p className="not-for" key={p.id}><UserX size={13}/><span>{p.name}: {plainReason(e.blocked_for[p.id] ?? [], e.assessments?.[p.id]?.status === "requires_confirmation" || (e.blocked_for[p.id] ?? []).every(r => /^confirm/i.test(r)), p)}</span></p>)}
                              {askFor.map(p => <p className="ask-for" key={p.id}><CircleHelp size={13}/><span>{p.name}: {plainReason(e.assessments?.[p.id]?.reasons ?? [], true, p)}</span></p>)}
                            </div>
                          )
                        )}
                        {hiddenIngredients(d, diners) && <p className="hidden-flag"><TriangleAlert size={13} /><span>Hidden ingredient: {hiddenIngredients(d, diners)}</span></p>}
                        {e && e.questions.length > 0 && <p className="dish-question"><CircleHelp size={13} /><span>{e.questions[0]}</span></p>}
                        {d.allergens.length > 0 && (
                          <details className="dish-flags">
                            <summary>Ingredient notes</summary>
                            <p>{d.allergens.map(flagWording).join("; ")}</p>
                          </details>
                        )}
                        {versionOnSlip.length > 0 && <small className="menu-restore">Another version is on this order: {versionOnSlip.map(dishName).join(", ")}. Usually one version is enough.</small>}
                        {excluded.includes(d.id) && <small className="menu-restore">Removed earlier. Choosing it brings it back.</small>}
                      </div>
                      <div className="menu-row-side">
                        <strong className="menu-price">
                          {money(d.price, cur)}
                          {mode === "pick" && <small>{delta >= 0 ? "+" : "−"}{money(Math.abs(delta), cur)} all-in*</small>}
                        </strong>
                        <div className="menu-row-actions">
                          {mode === "browse" && (
                            <button className="btn btn-outline btn-small" onClick={() => setEditor(d)}><Pencil size={13} />Edit</button>
                          )}
                          {onSlip.has(d.id) ? (
                            <span className="helper"><Check size={13} /> On this order</span>
                          ) : (
                            (mode === "pick" || plan) && (
                              <>
                                <button className="btn btn-primary btn-small" disabled={!canPick} title={over > 0 ? `Over the table's budget by ${money(over, cur)} with tax and tip` : undefined} onClick={() => onPick(d.id)}>
                                  {oldDish ? "Swap in" : "Add to order"}
                                </button>
                                {over > 0 && <small className="over-budget">Over budget by {money(over, cur)}</small>}
                              </>
                            )
                          )}
                        </div>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
            {candidates.some((d) => photoFor(d)) && <p className="photo-note">Photos show similar dishes, for illustration.</p>}
            {!candidates.length && (
              <div className="empty-state">
                <h2>No matching dishes</h2>
                <p>Try another category or remove a filter.</p>
                <button className="btn btn-outline" onClick={() => { setQuery(""); setCategory("all"); setSameCategory(false); setAllDiners(false); }}>Clear filters</button>
              </div>
            )}
            {mode === "browse" && (
              <button className="btn btn-primary w-full mt-5" onClick={onClose} disabled={!menu.verified}>
                {menu.verified ? "Use this menu" : "Review menu to continue"}
              </button>
            )}
            <p className="helper mt-4">
              {mode === "pick"
                ? "*Price change for this dish only, including tax and tip. Other dishes you have not kept may change."
                : "Menu edits apply to this session. Diner eligibility comes from the recorded dietary requirements; confirm open questions with staff."}
            </p>
          </>
        )}
      </Sheet>
      {editor && <DishEditor dish={editor === "new" ? undefined : editor} onClose={() => setEditor(null)} onSave={saveDish} />}
    </>
  );
}
