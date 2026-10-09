import { useRef } from "react";
import { ArrowLeft, BadgeCheck, Camera, ImageUp } from "lucide-react";
import type { DinerProfile, DiningSettings, Menu } from "../types";
import { currencySymbol, dishName, money } from "../lib/format";
import { photoFor } from "../lib/dishPhotos";
import { Stepper, type Step } from "./Stepper";
import { TableSetup } from "./TableSetup";

const titleCase = (s: string) => s.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());

interface Props {
  step: "menu" | "table";
  onStep: (s: Step) => void;
  canPlan: boolean;
  menu: Menu;
  diners: DinerProfile[];
  saved: DinerProfile[];
  onPick: (d: DinerProfile) => void;
  onRemove: (id: string) => void;
  settings: DiningSettings;
  photoReader: "openrouter" | "gemini" | "ocr" | null;
  onMenu: () => void;
  onPhoto: (file: File) => void;
  onPaste: () => void;
  onSample: () => void;
  onChange: (s: DiningSettings) => void;
  onEdit: (d: DinerProfile) => void;
  onAdd: () => void;
  onPreset: (id: string) => void;
  onPlan: () => void;
  loading: boolean;
  current?: boolean; // a recommendation for exactly these inputs already exists
  onApprove?: () => void; // "Looks right": mark an imported menu reviewed and go on
}

const PHOTO_TEXT = {
  openrouter: "Take or upload a photo. The AI reads the dishes and prices; our reviewed ingredient knowledge does the rest.",
  gemini: "Take or upload a photo. Gemini reads the dishes and prices; our reviewed ingredient knowledge does the rest.",
  ocr: "Take or upload a photo. This server reads the dishes and prices; our reviewed ingredient knowledge does the rest.",
  none: "Take or upload a photo, or paste the text. Our reviewed ingredient knowledge does the rest.",
};

export function SetupFlow({ step, onStep, canPlan, menu, diners, saved, onPick, onRemove, settings, photoReader, onMenu, onPhoto, onPaste, onSample, onChange, onEdit, onAdd, onPreset, onPlan, loading, current, onApprove }: Props) {
  const cur = currencySymbol(menu.currency);
  const imported = menu.restaurant_id.startsWith("local-");
  const camera = useRef<HTMLInputElement>(null);
  const upload = useRef<HTMLInputElement>(null);
  // The menu itself, dishes with an illustrative photo first.
  const preview = [...menu.dishes].sort((a, b) => Number(!!photoFor(b)) - Number(!!photoFor(a))).slice(0, 12);
  const picked = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (f) onPhoto(f);
  };
  return (
    <div className="onboarding">
      <Stepper step={step} onStep={onStep} canPlan={canPlan} canTable={!!menu?.verified && diners.length > 0} />
      {step === "menu" ? (
        <>
          <h1>{imported ? "Your menu is ready" : "Choose a menu"}</h1>
          <p className="setup-intro">{imported ? `${menu.restaurant_name}: ${menu.dishes.length} dishes with prices, read from your menu. Check them, then pick who's eating.` : "We suggest dishes to share from one menu, within your budget and everyone's recorded dietary needs."}</p>
          {imported ? (
            <>
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
              <button className="btn btn-outline btn-small" onClick={onMenu}>
                View menu
              </button>
            </div>
            <ul className="menu-preview" aria-label="Dishes on this menu">
              {preview.map((d) => {
                const photo = photoFor(d);
                return (
                  <li key={d.id}>
                    {photo ? <img src={photo.src} alt="" width={120} height={120} loading="lazy" /> : <span className="menu-preview-blank" aria-hidden="true" />}
                    <strong>{dishName(d)}</strong>
                    <small>{money(d.price, cur)}</small>
                  </li>
                );
              })}
            </ul>
            {preview.some((d) => photoFor(d)) && <p className="photo-note">Photos show similar dishes, for illustration.</p>}
          </section>
          <div className="setup-actions">
            {imported && !menu.verified && onApprove ? (
              <button className="btn btn-primary" onClick={onApprove}>
                Looks right, use this menu
              </button>
            ) : (
              <button className="btn btn-primary" onClick={() => onStep("table")} disabled={!menu.verified}>
                Continue with this menu
              </button>
            )}
            <button className="text-button" onClick={onSample}>
              Or try the sample plan
            </button>
          </div>
              <h2 className="setup-subhead">Or read a different menu</h2>
          <section className="photo-first" aria-labelledby="photo-heading">
            <h2 id="photo-heading">Have the menu in front of you?</h2>
            <p>{PHOTO_TEXT[photoReader ?? "none"]}</p>
            <div className="setup-actions">
              <button className="btn btn-primary" onClick={() => camera.current?.click()}>
                <Camera size={16} />
                Take a photo
              </button>
              <button className="btn btn-outline" onClick={() => upload.current?.click()}>
                <ImageUp size={16} />
                Upload a photo
              </button>
              <button className="text-button" onClick={onPaste}>
                Or paste the menu text
              </button>
            </div>
            {!photoReader && <p className="helper">Photo reading is not set up on this server yet, so pasting the text is the reliable path.</p>}
            <input ref={camera} type="file" accept="image/*" capture="environment" hidden aria-label="Take a menu photo" onChange={picked} />
            <input ref={upload} type="file" accept="image/png,image/jpeg,image/webp" hidden aria-label="Upload a menu photo" onChange={picked} />
          </section>
            </>
          ) : (
            <>
          <section className="photo-first" aria-labelledby="photo-heading">
            <h2 id="photo-heading">Have the menu in front of you?</h2>
            <p>{PHOTO_TEXT[photoReader ?? "none"]}</p>
            <div className="setup-actions">
              <button className="btn btn-primary" onClick={() => camera.current?.click()}>
                <Camera size={16} />
                Take a photo
              </button>
              <button className="btn btn-outline" onClick={() => upload.current?.click()}>
                <ImageUp size={16} />
                Upload a photo
              </button>
              <button className="text-button" onClick={onPaste}>
                Or paste the menu text
              </button>
            </div>
            {!photoReader && <p className="helper">Photo reading is not set up on this server yet, so pasting the text is the reliable path.</p>}
            <input ref={camera} type="file" accept="image/*" capture="environment" hidden aria-label="Take a menu photo" onChange={picked} />
            <input ref={upload} type="file" accept="image/png,image/jpeg,image/webp" hidden aria-label="Upload a menu photo" onChange={picked} />
          </section>
          <h2 className="setup-subhead">Or use a saved menu</h2>
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
              <button className="btn btn-outline btn-small" onClick={onMenu}>
                View menu
              </button>
            </div>
            <ul className="menu-preview" aria-label="Dishes on this menu">
              {preview.map((d) => {
                const photo = photoFor(d);
                return (
                  <li key={d.id}>
                    {photo ? <img src={photo.src} alt="" width={120} height={120} loading="lazy" /> : <span className="menu-preview-blank" aria-hidden="true" />}
                    <strong>{dishName(d)}</strong>
                    <small>{money(d.price, cur)}</small>
                  </li>
                );
              })}
            </ul>
            {preview.some((d) => photoFor(d)) && <p className="photo-note">Photos show similar dishes, for illustration.</p>}
          </section>
          <div className="setup-actions">
            <button className="btn btn-primary" onClick={() => onStep("table")} disabled={!menu.verified}>
              Continue with this menu
            </button>
            <button className="text-button" onClick={onSample}>
              Or try the sample plan
            </button>
          </div>
            </>
          )}
          <p className="session-note">Classroom prototype with no login: menu edits stay on this page, and the people you add are saved on this server for everyone using it.</p>
        </>
      ) : (
        <>
          <button className="text-button setup-back" onClick={() => onStep("menu")}>
            <ArrowLeft size={15} />
            Back to menu
          </button>
          <h1>Who's at the table?</h1>
          <p className="setup-intro">Pick saved people or add someone new; everyone you add is remembered for next time. Recorded allergies and diets rule dishes out; tastes only change the ranking.</p>
          <div className="setup-table">
            <TableSetup diners={diners} saved={saved} onPick={onPick} onRemove={onRemove} settings={settings} currency={menu.currency} onChange={onChange} onEdit={onEdit} onAdd={onAdd} onPreset={onPreset} onPlan={onPlan} loading={loading} current={current} initial />
          </div>
        </>
      )}
    </div>
  );
}
