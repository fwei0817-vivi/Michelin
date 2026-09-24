import { BadgeCheck, Check, Upload } from "lucide-react";
import type { DinerProfile, DiningSettings, Menu } from "../types";
import { currencySymbol, dishName, money } from "../lib/format";
import { DISH_PHOTOS } from "../lib/dishPhotos";
import { TableSetup } from "./TableSetup";

const STEPS = ["Menu", "Table", "Dishes"];
const titleCase = (s: string) => s.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());

interface Props {
  step: "menu" | "table";
  onStep: (s: "menu" | "table") => void;
  menu: Menu;
  diners: DinerProfile[];
  settings: DiningSettings;
  onMenu: () => void;
  onImport: () => void;
  onSample: () => void;
  onChange: (s: DiningSettings) => void;
  onEdit: (d: DinerProfile) => void;
  onAdd: () => void;
  onPreset: (id: string) => void;
  onPlan: () => void;
  loading: boolean;
}

export function SetupFlow({ step, onStep, menu, diners, settings, onMenu, onImport, onSample, onChange, onEdit, onAdd, onPreset, onPlan, loading }: Props) {
  const current = step === "menu" ? 0 : 1;
  const cur = currencySymbol(menu.currency);
  // Preview the menu itself: dishes with an illustrative photo first.
  const preview = [...menu.dishes].sort((a, b) => Number(!!DISH_PHOTOS[b.id]) - Number(!!DISH_PHOTOS[a.id])).slice(0, 6);
  return (
    <div className="onboarding">
      <ol className="steps" aria-label="Plan a meal">
        {STEPS.map((label, i) => (
          <li key={label} className={i === current ? "current" : i < current ? "complete" : ""} aria-current={i === current ? "step" : undefined}>
            <span>{i < current ? <Check size={13} /> : i + 1}</span>
            {label}
          </li>
        ))}
      </ol>
      {step === "menu" ? (
        <>
          <h1>Choose a menu</h1>
          <p className="setup-intro">We suggest dishes to share from one menu, within your budget and everyone's recorded dietary needs.</p>
          <section className="menu-choice" aria-label="Current menu">
            <div className="menu-choice-head">
              <div>
                <h2>{menu.restaurant_name}</h2>
                <p>
                  {titleCase(menu.cuisine)}, {menu.dishes.length} dishes.{" "}
                  {menu.verified ? (
                    <span className="reviewed">
                      <BadgeCheck size={14} />
                      Reviewed
                    </span>
                  ) : (
                    "Needs review"
                  )}
                </p>
              </div>
              <button className="text-button" onClick={onMenu}>
                View menu
              </button>
            </div>
            <ul className="menu-preview">
              {preview.map((d) => {
                const photo = DISH_PHOTOS[d.id];
                return (
                  <li key={d.id}>
                    {photo ? <img src={photo.src} alt="" width={96} height={96} loading="lazy" /> : <span className="menu-preview-blank" aria-hidden="true" />}
                    <strong>{dishName(d)}</strong>
                    <small>{money(d.price, cur)}</small>
                  </li>
                );
              })}
            </ul>
            {preview.some((d) => DISH_PHOTOS[d.id]) && <p className="photo-note">Photos show similar dishes, for illustration.</p>}
          </section>
          <div className="setup-actions">
            <button className="btn btn-primary" onClick={() => onStep("table")} disabled={!menu.verified}>
              Continue with this menu
            </button>
            <button className="btn btn-outline" onClick={onImport}>
              <Upload size={16} />
              Bring your own menu
            </button>
            <button className="text-button" onClick={onSample}>
              Or try the sample plan
            </button>
          </div>
          <p className="session-note">Classroom prototype. Changes stay on this page and reset when you refresh.</p>
        </>
      ) : (
        <>
          <button className="text-button setup-back" onClick={() => onStep("menu")}>
            Back to menu
          </button>
          <h1>Who's at the table?</h1>
          <p className="setup-intro">Use the example group or add your own people. Recorded allergies and diets rule dishes out; tastes only change the ranking.</p>
          <div className="setup-table">
            <TableSetup diners={diners} settings={settings} currency={menu.currency} onChange={onChange} onEdit={onEdit} onAdd={onAdd} onPreset={onPreset} onPlan={onPlan} loading={loading} initial />
          </div>
        </>
      )}
    </div>
  );
}
