import { dishName, money } from "./format";

/** The order ticket's lines (QA r25, 2026-10-10): every item the plan orders, including the
 *  plain rice the code adds per person and any code top-up dish, with count, unit price and
 *  line total. The ticket, the order panel and the group-chat text all read from here, so
 *  their lines add up to the plan's own subtotal (the one the plan page shows). */
export interface TicketLine { id: string; name: string; nameZh: string | null; quantity: number; unit: number | null; total: number; rice: boolean }
interface D { id: string; name_en?: string | null; name_zh?: string | null; price?: number | null; category: string }
interface P { items: { dish_id: string; quantity: number }[]; subtotal: number; tax: number; tip: number; total: number; per_person: number }

export function ticketLines(plan: P, dishes: D[]): TicketLine[] {
  const byId = new Map(dishes.map((d) => [d.id, d]));
  const out: TicketLine[] = [];
  for (const i of plan.items) {
    const d = byId.get(i.dish_id);
    if (!d) continue;
    const unit = d.price ?? null;
    out.push({ id: d.id, name: dishName(d as never), nameZh: d.name_zh ?? null, quantity: i.quantity, unit, total: Math.round((unit ?? 0) * 100) * i.quantity / 100, rice: d.category === "staple" });
  }
  return out;
}

/** Sum of the lines in cents; equals plan.subtotal when nothing is missing. */
export function linesSubtotal(lines: TicketLine[]): number {
  return lines.reduce((s, l) => s + Math.round(l.total * 100), 0) / 100;
}

/** No plain rice on the menu at all: say so, so nobody thinks it was forgotten. */
export function noRiceNote(dishes: D[]): string | null {
  return dishes.some((d) => d.category === "staple") ? null : "This menu lists no plain rice, so none is included; ask your server if you want some.";
}

export function lineText(l: TicketLine, cur: string): string {
  return l.quantity > 1 ? `${l.name} × ${l.quantity}  ${money(l.unit, cur)} each  ${money(l.total, cur)}` : `${l.name}  ${money(l.total, cur)}`;
}

export function ticketText(restaurant: string, n: number, plan: P & { confirm_with_staff: string[] }, dishes: D[], cur: string): string {
  const lines = [`${restaurant}, table of ${n}`, ""];
  for (const l of ticketLines(plan, dishes)) lines.push(lineText(l, cur));
  const note = noRiceNote(dishes);
  if (note) lines.push(note);
  lines.push("", `Subtotal ${money(plan.subtotal, cur)}, tax ${money(plan.tax, cur)}, tip ${money(plan.tip, cur)}`);
  lines.push(`Total ${money(plan.total, cur)} with tax and tip, ${money(plan.per_person, cur)} each`);
  if (plan.confirm_with_staff.length) {
    lines.push("", "Please check with the kitchen:");
    for (const q of plan.confirm_with_staff) lines.push(`- ${q}`);
  }
  return lines.join("\n");
}
