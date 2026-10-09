import { useState } from "react";
import { ALLERGENS, ALLERGEN_LABEL, DIETS, DIET_LABEL } from "../lib/format";
import type { Allergen, Diet, DinerProfile } from "../types";
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

  const match = !diner ? saved.find((p) => p.name.trim().toLowerCase() === name.trim().toLowerCase()) : undefined;
  const [confirmForget, setConfirmForget] = useState(false);
  const toggle = <T,>(list: T[], v: T) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

  const save = () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    if (!diner && match) return; // pick the saved person instead of creating a duplicate
    const id = diner?.id ?? personId(trimmed, existingIds);
    onSave({ id, name: trimmed, allergies, diets, notes: notes.trim() });
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
          <p className="mt-2 text-xs text-fg-3">
            Allergies and diets are hard rules: a dish that may break one is left out or becomes a question for your server.
          </p>
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
