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
  `rounded-full border px-3 py-1.5 text-sm ${on ? "border-slip bg-slip text-ink" : "border-celadon/40 text-celadon hover:border-celadon"}`;

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
          <span className="text-celadon">Name</span>
          <input
            autoFocus={!diner}
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="mt-1 w-full rounded-lg border border-transparent bg-booth-deep px-3 py-2 text-slip focus:border-celadon focus:outline-none"
          />
        </label>

        <fieldset>
          <legend className="text-sm text-celadon">Allergies</legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {ALLERGENS.map((a) => (
              <button key={a} type="button" aria-pressed={allergies.includes(a)} onClick={() => setAllergies(toggle(allergies, a))} className={chip(allergies.includes(a))}>
                {ALLERGEN_LABEL[a]}
              </button>
            ))}
          </div>
        </fieldset>

        <fieldset>
          <legend className="text-sm text-celadon">Diet</legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {DIETS.map((d) => (
              <button key={d} type="button" aria-pressed={diets.includes(d)} onClick={() => setDiets(toggle(diets, d))} className={chip(diets.includes(d))}>
                {DIET_LABEL[d]}
              </button>
            ))}
          </div>
          <p className="mt-2 text-xs text-celadon-dim">
            Allergies and diet are hard limits: a dish that might break one is never counted for this person.
          </p>
        </fieldset>

        <fieldset>
          <legend className="text-sm text-celadon">Heat</legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {SPICE_LABEL.map((label, i) => (
              <button key={label} type="button" aria-pressed={spice === i} onClick={() => setSpice(spice === i ? null : i)} className={chip(spice === i)}>
                {label}
              </button>
            ))}
          </div>
          <p className="mt-2 text-xs text-celadon-dim">Heat and dislikes only change the ranking, never safety.</p>
        </fieldset>

        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm">
            <span className="text-celadon">Dislikes</span>
            <input
              value={dislikes}
              onChange={(e) => setDislikes(e.target.value)}
              placeholder="cilantro, offal"
              className="mt-1 w-full rounded-lg border border-transparent bg-booth-deep px-3 py-2 text-slip placeholder:text-celadon-dim focus:border-celadon focus:outline-none"
            />
          </label>
          <label className="block text-sm">
            <span className="text-celadon">Likes</span>
            <input
              value={likes}
              onChange={(e) => setLikes(e.target.value)}
              placeholder="tofu, spicy"
              className="mt-1 w-full rounded-lg border border-transparent bg-booth-deep px-3 py-2 text-slip placeholder:text-celadon-dim focus:border-celadon focus:outline-none"
            />
          </label>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
          {diner ? (
            <button type="button" onClick={() => onRemove(diner.id)} className="text-sm text-celadon hover:text-slip">
              Not eating tonight
            </button>
          ) : (
            <span />
          )}
          <div className="flex gap-3">
            <button type="button" onClick={onClose} className="rounded-full px-4 py-2 text-sm text-celadon hover:text-slip">
              Cancel
            </button>
            <button type="submit" disabled={!name.trim()} className="rounded-full bg-slip px-5 py-2 text-sm font-semibold text-ink disabled:opacity-50">
              Save
            </button>
          </div>
        </div>
      </form>
    </Sheet>
  );
}
