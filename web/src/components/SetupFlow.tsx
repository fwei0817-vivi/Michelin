import { ArrowLeft, ArrowRight, BookOpen, Check, Leaf, Upload, Users, UtensilsCrossed } from "lucide-react";
import type { DinerProfile, DiningSettings, Menu } from "../types";
import { currencySymbol, money } from "../lib/format";
import { TableSetup } from "./TableSetup";

export function SetupFlow({ step, onStep, menu, diners, settings, onMenu, onImport, onSample, onChange, onEdit, onAdd, onPreset, onPlan, loading }: {
  step: "menu" | "table"; onStep: (s: "menu" | "table") => void; menu: Menu;
  diners: DinerProfile[]; settings: DiningSettings; onMenu: () => void; onImport: () => void;
  onSample: () => void; onChange: (s: DiningSettings) => void; onEdit: (d: DinerProfile) => void;
  onAdd: () => void; onPreset: (id: string) => void; onPlan: () => void; loading: boolean;
}) {
  return <div className={`onboarding ${step === "table" ? "table-step" : ""}`}>
    <ol className="steps" aria-label="Plan a meal">
      <li className={step === "menu" ? "current" : "complete"} aria-current={step === "menu" ? "step" : undefined}><span>{step === "table" ? <Check size={14}/> : "1"}</span>Choose a menu</li>
      <li className={step === "table" ? "current" : ""} aria-current={step === "table" ? "step" : undefined}><span>2</span>Your table</li>
      <li><span>3</span>Make it yours</li>
    </ol>
    <div className="setup-layout"><section className="setup-main">
      <div className="eyebrow">{step === "menu" ? "LESS DECIDING. MORE DINING." : "EVERYONE GETS A SAY."}</div>
      <h1>{step === "menu" ? <>A good meal.<br/><em>For everyone.</em></> : <>Who's coming<br/><em>to dinner?</em></>}</h1>
      <p className="setup-intro">{step === "menu" ? "Find dishes to share, with your group's tastes, dietary needs and budget in mind." : "Start with the example group below, or add your own people. Tell us what works for each person."}</p>
      {step === "menu" ? <>
        <div className="menu-choice"><div className="choice-icon"><BookOpen size={25}/></div><div><span className="small-label">YOUR CURRENT MENU</span><h2>{menu.restaurant_name}</h2><p>{menu.cuisine.replaceAll("_", " ")} · {menu.dishes.length} dishes · {menu.verified ? "Reviewed menu" : "Needs review"}</p></div><button className="text-button" onClick={onMenu}>View menu <ArrowRight size={15}/></button></div>
        <button className="upload-choice" onClick={onImport}><span className="choice-icon"><Upload size={23}/></span><span><strong>Bring your own menu</strong><small>Paste menu text, review the dishes, then plan.</small></span><ArrowRight size={19}/></button>
        <div className="setup-actions"><button className="btn btn-primary" onClick={() => onStep("table")} disabled={!menu.verified}>Continue with this menu <ArrowRight size={17}/></button><button className="text-button" onClick={onSample}>Try the sample plan</button></div>
        <p className="session-note">Classroom prototype · Changes stay in this page and reset when you refresh.</p>
      </> : <>
        <button className="text-button setup-back" onClick={() => onStep("menu")}><ArrowLeft size={15}/>Back to menu</button>
        <div className="setup-table"><TableSetup diners={diners} settings={settings} currency={menu.currency} onChange={onChange} onEdit={onEdit} onAdd={onAdd} onPreset={onPreset} onPlan={onPlan} loading={loading} initial/></div>
      </>}
    </section><aside className="welcome-card">
      <div className="eyebrow">A LITTLE LESS “WHAT SHOULD WE GET?”</div>
      <div className="table-art" aria-hidden="true"><div className="plate plate-outer"><div className="plate-inner"><UtensilsCrossed size={39}/><span>FOR THE<br/>TABLE</span></div></div>{["L", "D", "A", "K", "M", "T"].map((n,i)=><span key={n} className={`seat seat-${i}`}>{n}</span>)}</div>
      <h2>Different tastes.<br/>One shared table.</h2><p>Build an order together, without losing anyone's preferences along the way.</p>
      <div className="welcome-facts"><span><Users size={17}/>{diners.length} diners</span><span>{money(settings.budget, currencySymbol(menu.currency))} / person</span></div>
      <div className="welcome-note"><Leaf size={18}/><span>Dietary needs guide the suggestions. Open ingredient questions stay visible for the kitchen.</span></div>
    </aside></div>
  </div>;
}
