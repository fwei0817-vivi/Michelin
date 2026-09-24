import { useState } from "react";
import { currencySymbol, dishName, money } from "../lib/format";
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
  const cur = currencySymbol(menu.currency);

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
    <Sheet title="Order ticket" wide onClose={onClose}><div className="print-area">
      <div className="max-w-xl">
        <div>
          <h2 className="text-[24px] font-semibold leading-tight">{menu.restaurant_name}</h2>
          <p className="mt-1 text-fg-2">Table of {n} · {plan.items.length} dishes to share</p>
          <p className="mt-2 text-xs text-fg-3 print:hidden">Show this list to your server. This preview does not place an order.</p>
        </div>

        <ol className="mt-6 divide-y divide-line border-y border-line">
          {plan.items.map((i) => {
            const d = byId[i.dish_id];
            if (!d) return null;
            return (
              <li key={d.id} className="flex items-baseline justify-between gap-4 py-3">
                <div>
                  <p className="text-[18px] font-semibold leading-tight">{dishName(d)}</p>
                  {d.name_zh && <p className="mt-1 text-sm text-fg-2" lang="zh">{d.name_zh}</p>}
                  {i.quantity > 1 && <p className="mt-2 text-xs text-fg-2">{i.quantity} × {money(d.price, cur)}</p>}
                </div>
                <p className="tnum text-base font-semibold whitespace-nowrap">{money((d.price ?? 0) * i.quantity, cur)}</p>
              </li>
            );
          })}
        </ol>

        {plan.confirm_with_staff.length > 0 && (
          <section className="mt-7">
            <h3 className="text-lg font-semibold">Please check with the kitchen</h3>
            <ul className="mt-2 list-disc space-y-2 pl-5 text-[15px]">
              {plan.confirm_with_staff.map((q) => (
                <li key={q}>{q}</li>
              ))}
            </ul>
          </section>
        )}

        <dl className="ticket-costs"><dt>Menu subtotal</dt><dd>{money(plan.subtotal, cur)}</dd><dt>Tax</dt><dd>{money(plan.tax, cur)}</dd><dt>Tip</dt><dd>{money(plan.tip, cur)}</dd></dl>
        <p className="tnum mt-4 text-fg-2">
          {money(plan.total, cur)} with tax and tip, {money(plan.per_person, cur)} each
        </p>

        {copyError && <p role="alert" className="mt-4 text-sm text-danger print:hidden">Clipboard unavailable. Use Print or select the text to copy it.</p>}
        <div className="mt-6 flex flex-wrap gap-3 print:hidden">
          <button type="button" onClick={copy} className="btn btn-primary">
            <Copy size={15}/>{copied ? "Copied" : "Copy for the group chat"}
          </button>
          <button type="button" onClick={() => window.print()} className="btn btn-outline">
            <Printer size={15}/>Print
          </button>
        </div>
      </div>
    </div></Sheet>
  );
}
