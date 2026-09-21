import { useState } from "react";
import { dishName, money } from "../lib/format";
import { Copy, Printer } from "lucide-react";
import { Sheet } from "./Sheet";
import type { DinerProfile, Menu, Plan } from "../types";

interface Props {
  menu: Menu;
  plan: Plan;
  diners: DinerProfile[];
  onClose: () => void;
}

/** A compact English order ticket for sharing with the restaurant. */
export function WaiterView({ menu, plan, diners, onClose }: Props) {
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
  const byId = Object.fromEntries(menu.dishes.map((d) => [d.id, d]));
  const n = diners.length;
  const cur = menu.currency === "USD" ? "$" : menu.currency === "CNY" ? "¥" : `${menu.currency} `;

  const text = () => {
    const lines = [`${menu.restaurant_name}, table of ${n}`, ""];
    for (const i of plan.items) {
      const d = byId[i.dish_id];
      if (!d) continue;
      lines.push(`${i.quantity} × ${dishName(d)}  ${money((d.price ?? 0) * i.quantity, cur)} total`);
    }
    lines.push("", `Total ${money(plan.total, cur)} with tax and tip, ${money(plan.per_person, cur)} each`);
    if (plan.confirm_with_staff.length) {
      lines.push("", "Please check with the kitchen:");
      for (const q of plan.confirm_with_staff) lines.push(`- ${q}`);
    }
    return lines.join("\n");
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text());
      setCopied(true);
      setCopyError(false);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopyError(true);
    }
  };

  return (
    <Sheet title="Order ticket" wide onClose={onClose}><div className="print-area rounded-xl bg-slip text-ink">
      <div className="mx-auto max-w-lg px-6 py-8">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-[28px] font-semibold leading-tight">{menu.restaurant_name}</h2>
            <p className="mt-1 text-ink-soft">Table of {n}</p>
          </div>
          <button type="button" onClick={onClose} className="rounded-full border border-ink/30 px-4 py-2 text-sm hover:border-ink print:hidden">
            Back
          </button>
        </div>

        <ol className="mt-6 divide-y divide-ink/15 border-y border-ink/15">
          {plan.items.map((i) => {
            const d = byId[i.dish_id];
            if (!d) return null;
            return (
              <li key={d.id} className="flex items-baseline justify-between gap-4 py-3">
                <div>
                  <p className="text-[30px] font-semibold leading-tight">{dishName(d)}</p>

                </div>
                <p className="tnum text-[30px] leading-tight">{i.quantity}</p>
              </li>
            );
          })}
        </ol>

        {plan.confirm_with_staff.length > 0 && (
          <section className="mt-7">
            <h3 className="text-lg font-semibold">Please check with the kitchen</h3>
            <ul className="mt-2 list-disc space-y-2 pl-5 text-[17px]">
              {plan.confirm_with_staff.map((q) => (
                <li key={q}>{q}</li>
              ))}
            </ul>
          </section>
        )}

        <p className="tnum mt-7 text-ink-soft">
          {money(plan.total, cur)} with tax and tip, {money(plan.per_person, cur)} each
        </p>

        {copyError && <p role="alert" className="mt-4 text-sm text-seal print:hidden">Clipboard unavailable. Use Print or select the text to copy it.</p>}
        <div className="mt-6 flex flex-wrap gap-3 print:hidden">
          <button type="button" onClick={copy} className="rounded-full bg-ink px-5 py-2.5 text-sm font-medium text-slip hover:bg-ink/90">
            <Copy className="inline mr-2" size={15}/>{copied ? "Copied" : "Copy for the group chat"}
          </button>
          <button type="button" onClick={() => window.print()} className="rounded-full border border-ink/30 px-5 py-2.5 text-sm hover:border-ink">
            <Printer className="inline mr-2" size={15}/>Print
          </button>
        </div>
      </div>
    </div></Sheet>
  );
}
