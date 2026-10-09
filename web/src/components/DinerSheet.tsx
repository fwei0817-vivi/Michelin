import { useState } from "react";
import { ALLERGENS, ALLERGEN_LABEL, DIETS, DIET_LABEL, SPICE_LABEL, splitList } from "../lib/format";
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

const chip = (on: boolean) =>
  `rounded-full border px-3 py-1.5 text-sm ${on ? "border-brand bg-brand text-surface" : "border-line-strong text-fg-2 hover:border-fg-3"}`;

export function DinerSheet({ diner, existingIds, saved, tonight, atTable, onSave, onPick, onRemove, onForget, onClose }: Props) {
  const [name, setName] = useState(diner?.name ?? "");
  const [allergies, setAllergies] = useState<Allergen[]>(diner?.allergies ?? []);
  const [diets, setDiets] = useState<Diet[]>(diner?.diets ?? []);
  const [spice, setSpice] = useState<number | null>(diner?.max_spice ?? null);
  const [dislikes, setDislikes] = useState((diner?.dislikes ?? []).join(", "));
  const [likes, setLikes] = useState((diner?.likes ?? []).join(", "));

  const match = !diner ? saved.find((p) => p.name.trim().toLowerCase() === name.trim().toLowerCase()) : undefined;
  const [confirmForget, setConfirmForget] = useState(false);
  const toggle = <T,>(list: T[], v: T) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

  const save = () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    if (!diner && match) return; // pick the saved person instead of creating a duplicate
    const id = diner?.id ?? personId(trimmed, existingIds);
    onSave({ id, name: trimmed, allergies, diets, max_spice: spice, dislikes: splitList(dislikes), likes: splitList(likes) });
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

        <fieldset>
          <legend className="text-sm text-fg-2">Allergies</legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {ALLERGENS.map((a) => (
              <button key={a} type="button" aria-pressed={allergies.includes(a)} onClick={() => setAllergies(toggle(allergies, a))} className={chip(allergies.includes(a))}>
                {ALLERGEN_LABEL[a]}
              </button>
            ))}
          </div>
        </fieldset>

        <fieldset>
          <legend className="text-sm text-fg-2">Diet</legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {DIETS.map((d) => (
              <button key={d} type="button" aria-pressed={diets.includes(d)} onClick={() => setDiets(toggle(diets, d))} className={chip(diets.includes(d))}>
                {DIET_LABEL[d]}
              </button>
            ))}
          </div>
          <p className="mt-2 text-xs text-fg-3">
            Recorded conflicts exclude a dish for this person. Unknown ingredients remain questions to confirm with the kitchen.
          </p>
        </fieldset>

        <fieldset>
          <legend className="text-sm text-fg-2">Heat</legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {SPICE_LABEL.map((label, i) => (
              <button key={label} type="button" aria-pressed={spice === i} onClick={() => setSpice(spice === i ? null : i)} className={chip(spice === i)}>
                {label}
              </button>
            ))}
          </div>
          <p className="mt-2 text-xs text-fg-3">Heat and dislikes affect preferences. Spicier dishes may still appear, with a note.</p>
        </fieldset>

        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm">
            <span className="text-fg-2">Dislikes</span>
            <input
              value={dislikes}
              onChange={(e) => setDislikes(e.target.value)}
              placeholder="cilantro, offal"
              className="field"
            />
          </label>
          <label className="block text-sm">
            <span className="text-fg-2">Likes</span>
            <input
              value={likes}
              onChange={(e) => setLikes(e.target.value)}
              placeholder="tofu, spicy"
              className="field"
            />
          </label>
        </div>

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
