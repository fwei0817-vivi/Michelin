import { useState } from "react";
import { ALLERGENS, ALLERGEN_LABEL, DIETS, DIET_LABEL, SPICE_LABEL, slug, splitList } from "../lib/format";
import type { Allergen, Diet, DinerProfile } from "../types";
import { Sheet } from "./Sheet";

interface Props {
  diner: DinerProfile | null; // null = someone new
  existingIds: string[];
  onSave: (d: DinerProfile) => void;
  onRemove: (id: string) => void;
  onClose: () => void;
}

const chip = (on: boolean) =>
  `rounded-full border px-3 py-1.5 text-sm ${on ? "border-brand bg-brand text-surface" : "border-line-strong text-fg-2 hover:border-fg-3"}`;

export function DinerSheet({ diner, existingIds, onSave, onRemove, onClose }: Props) {
  const [name, setName] = useState(diner?.name ?? "");
  const [allergies, setAllergies] = useState<Allergen[]>(diner?.allergies ?? []);
  const [diets, setDiets] = useState<Diet[]>(diner?.diets ?? []);
  const [spice, setSpice] = useState<number | null>(diner?.max_spice ?? null);
  const [dislikes, setDislikes] = useState((diner?.dislikes ?? []).join(", "));
  const [likes, setLikes] = useState((diner?.likes ?? []).join(", "));

  const toggle = <T,>(list: T[], v: T) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

  const save = () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    let id = diner?.id ?? slug(trimmed);
    if (!diner) while (existingIds.includes(id)) id = `${id}_`;
    onSave({ id, name: trimmed, allergies, diets, max_spice: spice, dislikes: splitList(dislikes), likes: splitList(likes) });
  };

  return (
    <Sheet title={diner ? `About ${diner.name}` : "Someone new"} onClose={onClose}>
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
            <button type="button" onClick={() => onRemove(diner.id)} className="text-sm text-fg-2 hover:text-danger">
              Not eating tonight
            </button>
          ) : (
            <span />
          )}
          <div className="flex gap-3">
            <button type="button" onClick={onClose} className="btn btn-outline">
              Cancel
            </button>
            <button type="submit" disabled={!name.trim()} className="btn btn-primary">
              Save
            </button>
          </div>
        </div>
      </form>
    </Sheet>
  );
}
