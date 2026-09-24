import { useEffect, useState } from "react";
import { ArrowLeftRight, Check, CheckCircle2, CircleHelp, FileImage, Flame, Leaf, Pencil, Plus, Search, Upload, UserX, Users } from "lucide-react";
import { evaluateMenu, parseMenu } from "../api";
import { CATEGORY_LABEL, currencySymbol, dishName, flagWording, listNames, money } from "../lib/format";
import { DISH_PHOTOS } from "../lib/dishPhotos";
import type { DinerProfile, Dish, Eligibility, Menu, MenuSummary, Plan } from "../types";
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
  tax: number;
  tip: number;
  onPick: (id: string) => void;
  onClose: () => void;
  onUpdate: (menu: Menu) => void;
  onSelectMenu: (id: string) => void;
}

const MAX_DISHES = 40;
const MAX_IMAGE_BYTES = 8 * 1024 * 1024;
const SPICE = ["", "Mild", "Medium", "Hot"];

/** The restaurant menu drawer: browse and edit the menu, import one, or pick a dish to add or swap in. */
export function SwapSheet({ menu, menus, menuId, plan, diners, excluded, old, mode, initialTab = "browse", tax, tip, onPick, onClose, onUpdate, onSelectMenu }: Props) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [sameCategory, setSameCategory] = useState(false);
  const [allDiners, setAllDiners] = useState(false);
  const [eligibility, setEligibility] = useState<Eligibility | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<"browse" | "import">(initialTab);
  const [text, setText] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
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

  const importRows = async () => {
    setParsing(true);
    setError("");
    setImported([]);
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
      const result = await parseMenu({ text, image_base64 });
      setImported(result.dishes);
      setText(result.text);
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
              <p>Your choice is kept. Dishes you have not kept may change to stay within budget and everyone's needs. The price difference shown is for this dish only.</p>
            </div>
          </div>
        )}
        {mode === "browse" && (
          <>
            <label className="field-label">
              Restaurant
              <select className="field" value={menuId} onChange={(e) => onSelectMenu(e.target.value)}>
                {menus.map((m) => (
                  <option key={m.slug} value={m.slug}>{m.slug === menuId ? menu.restaurant_name : m.restaurant_name}</option>
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
            <p className="helper">Paste your menu below, one dish and price per line. After importing, review ingredients and dietary details before getting suggestions.</p>
            <details className="photo-import">
              <summary>Use a menu photo instead</summary>
              <p className="helper">Photo reading requires image recognition to be available. If it fails, paste the menu text below.</p>
              <label className="upload-area">
                <FileImage size={24} />
                <strong>{photo?.name ?? "Choose a menu photo"}</strong>
                <span>PNG, JPEG or WebP, up to 8 MB</span>
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
            </details>
            {photo && <button className="btn btn-outline btn-small" onClick={() => setPhoto(null)}>Use text instead</button>}
            <div className="field-grid">
              <label className="field-label">
                Use imported dishes
                <select className="field" value={importMode} onChange={(e) => setImportMode(e.target.value as "append" | "replace")}>
                  <option value="replace">Start a new menu</option>
                  <option value="append">Add to current menu</option>
                </select>
              </label>
              {importMode === "replace" && (
                <label className="field-label">
                  Restaurant name
                  <input className="field" value={restaurantName} onChange={(e) => setRestaurantName(e.target.value)} placeholder="Your restaurant" />
                </label>
              )}
            </div>
            <label className="field-label">
              Menu text
              <textarea className="field" rows={6} value={text} onChange={(e) => { setText(e.target.value); setImported([]); }} placeholder={"Garlic greens $12.95\nSteamed rice $2.00"} />
            </label>
            <button className="btn btn-primary" disabled={parsing || (!text.trim() && !photo)} onClick={() => void importRows()}>
              <Upload size={15} />
              {parsing ? "Reading menu…" : "Extract dishes"}
            </button>
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
                    update({
                      ...menu,
                      ...(importMode === "replace" ? { restaurant_name: restaurantName.trim() || "My restaurant", source: "User-imported menu", cuisine: "Custom menu" } : {}),
                      verified: false,
                      dishes: importMode === "replace" ? imported : [...menu.dishes, ...imported],
                    });
                    setImported([]);
                    setTab("browse");
                  }}
                >
                  <Check size={15} />
                  Add to menu for review
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
              <label>
                <input type="checkbox" checked={allDiners} onChange={(e) => setAllDiners(e.target.checked)} />
                Fits every diner's recorded needs
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
                const photo = DISH_PHOTOS[d.id];
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
                          {d.is_vegetarian === true && <span><Leaf size={12} />{d.is_vegan ? "Vegan" : "Vegetarian"}</span>}
                          {d.spice_level > 0 && <span><Flame size={12} />{SPICE[d.spice_level]}</span>}
                          {e && notFor.length === 0 && <span title="Matches every diner's recorded requirements"><Users size={12} />Matches all {diners.length}</span>}
                        </div>
                        {!e ? (
                          <p className="helper">Checking diner requirements…</p>
                        ) : (
                          notFor.length > 0 && (
                            <div className="dish-notes">
                              <p className="not-for"><UserX size={13} /><span>Not for {listNames(notFor.map((p) => p.name))}</span></p>
                            </div>
                          )
                        )}
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
            {candidates.some((d) => DISH_PHOTOS[d.id]) && <p className="photo-note">Photos show similar dishes, for illustration.</p>}
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
