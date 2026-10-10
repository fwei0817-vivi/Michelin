import { useState } from "react";
import { currencySymbol, money } from "../lib/format";
import { noRiceNote, ticketLines, ticketText } from "../lib/ticket";
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
  const n = diners.length;
  const cur = currencySymbol(menu.currency);

  const lines = ticketLines(plan, menu.dishes);
  const riceNote = noRiceNote(menu.dishes);
  const text = () => ticketText(menu.restaurant_name, n, plan, menu.dishes, cur);

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
          <p className="mt-1 text-fg-2">Table of {n} · {lines.length} items</p>
          <p className="mt-2 text-xs text-fg-3 print:hidden">Show this to your server. This preview does not place an order.</p>
        </div>

        <ol className="mt-6 divide-y divide-line border-y border-line">
          {lines.map((l) => (
            <li key={l.id} className="flex items-baseline justify-between gap-4 py-3">
              <div>
                <p className="text-[18px] font-semibold leading-tight">{l.name}{l.quantity > 1 && <span className="tnum"> × {l.quantity}</span>}</p>
                {l.nameZh && <p className="mt-1 text-sm text-fg-2" lang="zh">{l.nameZh}</p>}
                {l.quantity > 1 && <p className="mt-2 text-xs text-fg-2">{l.quantity} × {money(l.unit, cur)}</p>}
              </div>
              <p className="tnum text-base font-semibold whitespace-nowrap">{money(l.total, cur)}</p>
            </li>
          ))}
        </ol>
        {riceNote && <p className="mt-3 text-sm text-fg-2">{riceNote}</p>}

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
