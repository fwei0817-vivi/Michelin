import { Check } from "lucide-react";

const STEPS = ["Menu", "Table", "Dishes"] as const;
export type Step = "menu" | "table" | "plan";
const INDEX: Record<Step, number> = { menu: 0, table: 1, plan: 2 };

/** 1 Menu, 2 Table, 3 Dishes. Completed steps can be revisited. */
export function Stepper({ step, onStep, canPlan }: { step: Step; onStep: (s: Step) => void; canPlan: boolean }) {
  const current = INDEX[step];
  const target: Step[] = ["menu", "table", "plan"];
  return (
    <ol className="steps" aria-label="Plan a meal">
      {STEPS.map((label, i) => {
        const reachable = i < current || (i === 2 && canPlan && current !== 2);
        const body = (
          <>
            <span>{i < current ? <Check size={13} /> : i + 1}</span>
            {label}
          </>
        );
        return (
          <li key={label} className={i === current ? "current" : i < current ? "complete" : ""} aria-current={i === current ? "step" : undefined}>
            {reachable ? <button type="button" className="step-link" onClick={() => onStep(target[i])}>{body}</button> : body}
          </li>
        );
      })}
    </ol>
  );
}
