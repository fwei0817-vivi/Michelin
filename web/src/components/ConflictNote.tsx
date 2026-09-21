import type { Conflict, Relaxation } from "../types";

interface Props {
  conflict: Conflict;
  onRelax: (r: Relaxation) => void;
}

const opensSettings = (r: Relaxation) => r.kind === "diet" || r.kind === "allergy";

export function ConflictNote({ conflict, onRelax }: Props) {
  return (
    <article className="print-in" aria-label="No order works yet">
      <div className="perf" aria-hidden="true" />
      <div className="paper rounded-b-md px-5 pb-6 pt-5 sm:px-7">
        <h2 className="text-[26px] font-semibold leading-tight">No order works yet</h2>
        <p className="mt-3 text-[15px] leading-relaxed">{conflict.message}</p>
        {conflict.relaxations.length > 0 && (
          <>
            <p className="mt-5 text-sm text-ink-soft">Any one of these would make an order possible.</p>
            <ul className="mt-2 space-y-2">
              {conflict.relaxations.map((r, i) => (
                <li key={i}>
                  <button
                    type="button"
                    onClick={() => onRelax(r)}
                    className="w-full rounded-md border border-ink/25 px-4 py-3 text-left hover:border-ink"
                  >
                    <span className="block">{r.description}</span>
                    {opensSettings(r) && (
                      <span className="mt-0.5 block text-sm text-ink-soft">Opens their settings so they decide.</span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </article>
  );
}
