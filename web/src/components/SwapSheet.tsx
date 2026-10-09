import { useEffect, useRef, useState } from "react";
import { ArrowLeftRight, Check, CheckCircle2, CircleHelp, FileImage, Flame, Leaf, Pencil, Plus, Search, Sparkles, TriangleAlert, Upload, UserX, Users } from "lucide-react";
import { evaluateMenu, parseMenu, getPreparedInputs, extractMenu } from "../api";
import { CATEGORY_LABEL, currencySymbol, dishName, flagWording, money } from "../lib/format";
import { photoFor } from "../lib/dishPhotos";
import { mayHideMeat } from "../lib/dietary";
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
  /** A photo picked on the menu step: read it straight away. */
  initialPhoto?: File | null;
  /** Started from "Have the menu in front of you?": importing opens the new restaurant. */
  openAfterImport?: boolean;
  tax: number;
  tip: number;
  onPick: (id: string) => void;
  /** Replacing a dish: let the AI pick instead (only that dish changes). */
  onAiSwap?: (id: string) => void;
  onClose: () => void;
  onUpdate: (menu: Menu) => void;
  /** Add an imported menu as a separate restaurant; returns its id. Does not switch to it. */
  onCreate: (menu: Menu) => string;
  onSelectMenu: (id: string) => void;
}

const MAX_DISHES = 40;
const MAX_IMAGE_BYTES = 8 * 1024 * 1024;
const SPICE = ["", "Mild", "Medium", "Hot"];
// Animal products and allergens that a dish name often does not reveal.
const HIDDEN = /pork|lard|beef|chicken|duck|lamb|meat|broth|stock|shrimp|prawn|crab|oyster|fish|anchov|scallop|egg|milk|butter|cream|cheese|peanut|sesame|nut/i;

/** Ingredients the knowledge base expects but the menu does not print, in plain words. */
function hiddenIngredients(d: Dish): string | null {
  const name = `${d.name_en ?? ""} ${d.description_raw ?? ""}`.toLowerCase();
  const printed = (ingredient: string) => ingredient.toLowerCase().split(/\W+/).some((w) => w.length >= 4 && name.includes(w));
  const notes = d.main_ingredients
    .filter((i) => i.tier !== "menu" && HIDDEN.test(i.name) && !printed(i.name))
    .map((i) => (i.tier === "inferred" ? `usually made with ${i.name}` : `may hide ${i.name}, ask`));
  return notes.length ? notes.join("; ") : null;
}

/** The restaurant menu drawer: browse and edit the menu, import one, or pick a dish to add or swap in. */
export function SwapSheet({ menu, menus, menuId, plan, diners, excluded, old, mode, initialTab = "browse", initialPhoto = null, openAfterImport = false, tax, tip, onPick, onAiSwap, onClose, onUpdate, onCreate, onSelectMenu }: Props) {
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
      setExtractionNotice(result.notice); setRestaurantName(result.menu.restaurant_name); setCreated(null);
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
  const [photo, setPhoto] = useState<File | null>(initialPhoto);
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
  const hiddenByCategory = sameCategory && oldDish ? menu.dishes.filter((d) => !onSlip.has(d.id) && d.category !== oldDish.category).length : 0;

  const update = (next: Menu) => { setVerified(false); onUpdate(next); };
  const autoRead = useRef(!!initialPhoto);
  useEffect(() => { if (autoRead.current) { autoRead.current = false; void importRows(); } });

  const importRows = async () => {
    setParsing(true);
    setError("");
    setImported([]); setExtractedMenu(null); setExtractionNotice(""); setCreated(null); setReadNotice("");
    try {
      let image_base64: string | undefined;
      if (photo) {
        image_base64 = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(String(reader.result).split(",")[1]);
          reader.onerror = () => reject(new Error("The image could not be read."));
          reader.readAsDataURL(photo);
        });
      }
      const result = await parseMenu(photo ? { image_base64 } : { text });
      setImported(result.dishes);
      setText(result.text);
      setReadNotice(result.notice ?? "");
      if (result.restaurant_name && !restaurantName.trim()) setRestaurantName(result.restaurant_name);
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
              <strong>{photo?.name ?? "Choose a menu photo"}</strong>
              <span>PNG, JPEG or WebP, up to 8 MB. Names and prices are read from the photo; ingredients come from our reviewed knowledge base.</span>
              <input
                aria-label="Menu image"
                type="file"
                accept="image/png,image/jpeg,image/webp"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f && f.size > MAX_IMAGE_BYTES) {
                    setError("Choose an image smaller than 8 MB.");
                    e.target.value = "";
                    setPhoto(null);
                  } else {
                    setPhoto(f ?? null);
                    setError("");
                    setImported([]);
                  }
                }}
              />
            </label>
            {photo ? (
              <button className="btn btn-outline btn-small" onClick={() => setPhoto(null)}>Paste text instead</button>
            ) : (
              <label className="field-label">
                Or paste the menu text, one dish and price per line
                <textarea aria-label="Menu text" className="field" rows={6} value={text} onChange={(e) => { setText(e.target.value); setImported([]); }} placeholder={"Garlic greens $12.95\nSteamed rice $2.00"} />
              </label>
            )}
            <button className="btn btn-primary" disabled={parsing || (!text.trim() && !photo)} onClick={() => void importRows()}>
              <Upload size={15} />
              {parsing ? "Reading menu…" : photo ? "Read the menu" : "Extract dishes"}
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
                <h3>{imported.length} dishes found</h3>
                <ul>
                  {imported.map((d) => (
                    <li key={d.id}><span>{dishName(d)}</span><strong>{money(d.price, cur)}</strong></li>
                  ))}
                </ul>
                <button
                  className="btn btn-outline"
                  disabled={importedCount > MAX_DISHES}
                  onClick={() => {
                    if (importMode === "replace" || extractedMenu) {
                      // A new, independent restaurant. The current one keeps its name and dishes,
                      // and stays selected until the user switches.
                      const name = restaurantName.trim() || extractedMenu?.restaurant_name || "My restaurant";
                      const fresh: Menu = extractedMenu
                        ? { ...extractedMenu, restaurant_name: name, verified: false }
                        : { restaurant_id: "", restaurant_name: name, cuisine: "custom", source: "User-imported menu", currency: menu.currency, verified: false, dishes: imported };
                      const id = onCreate(fresh);
                      if (openAfterImport) onSelectMenu(id); // the button says so: an explicit switch
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
              {candidates.map((d) => {
                const e = eligibility?.[d.id];
                const qty = d.category === "staple" ? diners.length : 1;
                const delta = ((d.price ?? 0) * qty - (oldDish?.price ?? 0) * oldQuantity) * (1 + tax + tip);
                const photo = photoFor(d);
                const notFor = e ? diners.filter((p) => !e.edible_by.includes(p.id)) : [];
                const canPick = !!e && e.edible_by.length > 0 && d.price != null && menu.verified && diners.length > 0;
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
                          {d.is_vegetarian === true && <span className={mayHideMeat(d) ? "tag-ask" : ""}><Leaf size={12} />{d.is_vegan ? "Vegan" : "Vegetarian"}{mayHideMeat(d) ? "? ask" : ""}</span>}
                          {d.spice_level != null && d.spice_level > 0 && <span><Flame size={12} />{SPICE[d.spice_level]}</span>}
                          {e && diners.length > 0 && notFor.length === 0 && <span title="Matches every diner's recorded requirements"><Users size={12} />Matches all {diners.length}{mayHideMeat(d) ? " if confirmed" : ""}</span>}
                        </div>
                        {!e ? (
                          <p className="helper">Checking diner requirements…</p>
                        ) : (
                          notFor.length > 0 && (
                            <div className="dish-notes">
                              {notFor.map(p => <p className="not-for" key={p.id}><UserX size={13}/><span>{p.name}: {e.assessments?.[p.id]?.status === "requires_confirmation" ? "Requires confirmation" : "Recorded conflict"} — {(e.blocked_for[p.id] ?? []).join("; ")}</span></p>)}
                            </div>
                          )
                        )}
                        {hiddenIngredients(d) && <p className="hidden-flag"><TriangleAlert size={13} /><span>Hidden ingredient: {hiddenIngredients(d)}</span></p>}
                        {e && e.questions.length > 0 && <p className="dish-question"><CircleHelp size={13} /><span>{e.questions[0]}</span></p>}
                        {d.allergens.length > 0 && (
                          <details className="dish-flags">
                            <summary>Ingredient notes</summary>
                            <p>{d.allergens.map(flagWording).join("; ")}</p>
                          </details>
                        )}
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
                              <button className="btn btn-primary btn-small" disabled={!canPick} onClick={() => onPick(d.id)}>
                                {oldDish ? "Swap in" : "Add to order"}
                              </button>
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
