import { useState } from "react";
import { ALLERGENS, ALLERGEN_LABEL, DIETS, DIET_LABEL, PREFERENCES, PREFERENCE_LABEL, SPICE_PREFS, cleanTerm } from "../lib/format";
import type { Allergen, Diet, DinerProfile, Preference } from "../types";
import { Sheet } from "./Sheet";

interface Props {
  diner: DinerProfile | null; // null = someone new
  existingIds: string[]; // tonight's and saved people's ids, so a new id never collides
  saved: DinerProfile[]; // everyone known: tonight's table and saved people
  tonight: string[];
  atTable: boolean;
  onSave: (d: DinerProfile) => void;
  onPick: (d: DinerProfile) => void;
  onRemove: (id: string) => void;
  onForget: (id: string) => void;
  onClose: () => void;
}

/** Free-text chips ("mango", "halal"): type and press Enter or Add; × removes; a few
 * common ones are one tap away. */
function TermChips({ label, values, onChange, suggestions, placeholder }: { label: string; values: string[]; onChange: (v: string[]) => void; suggestions: string[]; placeholder: string }) {
  const [text, setText] = useState("");
  const add = (raw: string) => {
    const terms = raw.split(",").map(cleanTerm).filter((t) => t && !values.includes(t));
    if (terms.length) onChange([...values, ...terms].slice(0, 10));
    setText("");
  };
  return (
    <div className="term-chips">
      <span className="text-sm text-fg-2">{label}</span>
      <div className="check-grid">
        {values.map((t) => (
          <span key={t} className="check-chip on term-chip">
            {t}
            <button type="button" aria-label={`Remove ${t}`} onClick={() => onChange(values.filter((x) => x !== t))}>×</button>
          </span>
        ))}
        {suggestions.filter((t) => !values.includes(t)).map((t) => (
          <button key={t} type="button" className="check-chip suggest-chip" onClick={() => add(t)}>+ {t}</button>
        ))}
      </div>
      <div className="term-add">
        <input
          className="field"
          aria-label={label}
          value={text}
          maxLength={40}
          placeholder={placeholder}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add(text);
            }
          }}
        />
        <button type="button" className="btn btn-outline btn-small" disabled={!cleanTerm(text)} onClick={() => add(text)}>Add</button>
      </div>
    </div>
  );
}

/** Stable, readable id from the name ("Li Wei" -> "li-wei", then "li-wei-2" if taken). */
export function personId(name: string, taken: string[]): string {
  const base = name.normalize("NFKD").replace(/[^\x00-\x7f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40) || "person";
  let id = base, n = 2;
  while (taken.includes(id)) id = `${base}-${n++}`;
  return id;
}

export function DinerSheet({ diner, existingIds, saved, tonight, atTable, onSave, onPick, onRemove, onForget, onClose }: Props) {
  const [name, setName] = useState(diner?.name ?? "");
  const [allergies, setAllergies] = useState<Allergen[]>(diner?.allergies ?? []);
  const [diets, setDiets] = useState<Diet[]>(diner?.diets ?? []);
  const [notes, setNotes] = useState(diner?.notes ?? "");
  const [otherAllergies, setOtherAllergies] = useState<string[]>(diner?.other_allergies ?? []);
  const [otherDiets, setOtherDiets] = useState<string[]>(diner?.other_diets ?? []);
  const [prefs, setPrefs] = useState<Preference[]>(diner?.preferences ?? []);
  const togglePref = (x: Preference) => {
    if (prefs.includes(x)) return setPrefs(prefs.filter((p) => p !== x));
    // One spice level at a time: "Loves spicy" replaces "No spicy".
    setPrefs([...prefs.filter((p) => !(SPICE_PREFS.includes(x) && SPICE_PREFS.includes(p))), x]);
  };

  const match = !diner ? saved.find((p) => p.name.trim().toLowerCase() === name.trim().toLowerCase()) : undefined;
  const [confirmForget, setConfirmForget] = useState(false);
  const toggle = <T,>(list: T[], v: T) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

  const save = () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    if (!diner && match) return; // pick the saved person instead of creating a duplicate
    const id = diner?.id ?? personId(trimmed, existingIds);
    onSave({ id, name: trimmed, allergies, diets, other_allergies: otherAllergies, other_diets: otherDiets, preferences: prefs, notes: notes.trim() });
  };

  return (
    <Sheet title={diner ? `About ${diner.name}` : "Someone new"} onClose={onClose}>
      <p className="helper">Saved automatically, so next time you can just pick {diner ? diner.name : "them"} from your saved people.</p>
      <form
        className="mt-5 space-y-6"
        onSubmit={(e) => {
          e.preventDefault();
          save();
        }}
      >
        <label className="block text-sm">
          <span className="text-fg-2">Name</span>
          <input
            autoFocus={!diner}
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="field"
          />
        </label>
        {match && (
          <div className="notice" role="status">
            <span>
              {tonight.includes(match.id) ? `${match.name} is already at the table. Use a different name for someone else.` : `${match.name} is already saved${match.allergies.length || match.diets.length ? ` (${[...match.allergies, ...match.diets].join(", ")})` : ""}.`}
            </span>
            {!tonight.includes(match.id) && (
              <button type="button" className="btn btn-outline btn-small" onClick={() => onPick(match)}>
                Add saved {match.name}
              </button>
            )}
          </div>
        )}

        <fieldset className="diner-checks">
          <legend className="text-sm text-fg-2">Allergies</legend>
          <div className="check-grid">
            {ALLERGENS.map((a) => (
              <label key={a} className={`check-chip ${allergies.includes(a) ? "on" : ""}`}>
                <input type="checkbox" checked={allergies.includes(a)} onChange={() => setAllergies(toggle(allergies, a))} />
                {ALLERGEN_LABEL[a]}
              </label>
            ))}
          </div>
          <TermChips label="Other allergies" values={otherAllergies} onChange={setOtherAllergies} suggestions={["mango", "cilantro", "msg", "kiwi"]} placeholder="e.g. mango, cilantro" />
        </fieldset>

        <fieldset className="diner-checks">
          <legend className="text-sm text-fg-2">Diet</legend>
          <div className="check-grid">
            {DIETS.map((d) => (
              <label key={d} className={`check-chip ${diets.includes(d) ? "on" : ""}`}>
                <input type="checkbox" checked={diets.includes(d)} onChange={() => setDiets(toggle(diets, d))} />
                {DIET_LABEL[d]}
              </label>
            ))}
          </div>
          <TermChips label="Other diets" values={otherDiets} onChange={setOtherDiets} suggestions={["halal", "kosher", "no alcohol"]} placeholder="e.g. halal, no alcohol" />
          <p className="mt-2 text-xs text-fg-3">
            Allergies and diets are hard rules: a dish that may break one is left out or becomes a question for your server.
          </p>
        </fieldset>

        <fieldset className="diner-checks">
          <legend className="text-sm text-fg-2">Preferences</legend>
          <div className="check-grid">
            {PREFERENCES.map((x) => (
              <label key={x} className={`check-chip ${prefs.includes(x) ? "on" : ""}`}>
                <input type="checkbox" checked={prefs.includes(x)} onChange={() => togglePref(x)} />
                {PREFERENCE_LABEL[x]}
              </label>
            ))}
          </div>
          <p className="mt-2 text-xs text-fg-3">Preferences are soft: the AI favours dishes that suit them but never leaves anyone without food.</p>
        </fieldset>

        <label className="block text-sm">
          <span className="text-fg-2">Tastes and preferences</span>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            maxLength={500}
            rows={2}
            placeholder="No spicy food, loves tofu, not a fan of cilantro"
            className="field"
          />
          <small className="text-xs text-fg-3">In their own words. The AI reads this when it picks dishes.</small>
        </label>

        <div className="drawer-footer flex flex-wrap items-center justify-between gap-3">
          {diner ? (
            <span className="flex flex-wrap gap-3">
              {atTable && (
                <button type="button" onClick={() => onRemove(diner.id)} className="text-sm text-fg-2 hover:text-danger">
                  Not eating tonight
                </button>
              )}
              {confirmForget ? (
                <button type="button" onClick={() => onForget(diner.id)} className="text-sm text-danger font-semibold">
                  Yes, delete {diner.name} for good
                </button>
              ) : (
                <button type="button" onClick={() => setConfirmForget(true)} className="text-sm text-fg-2 hover:text-danger">
                  Delete saved person
                </button>
              )}
            </span>
          ) : (
            <span />
          )}
          <div className="flex gap-3">
            <button type="button" onClick={onClose} className="btn btn-outline">
              Cancel
            </button>
            <button type="submit" disabled={!name.trim() || !!match} className="btn btn-primary">
              {diner ? "Save" : "Add to table"}
            </button>
          </div>
        </div>
      </form>
    </Sheet>
  );
}
