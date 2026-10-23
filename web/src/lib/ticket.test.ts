import { linesSubtotal, ticketLines, ticketText } from "./ticket";

let fails = 0;
function eq(a: unknown, b: unknown, what: string) {
  if (JSON.stringify(a) !== JSON.stringify(b)) { fails++; console.error("FAIL", what, a, "!=", b); } else console.log("ok", what);
}
// QA r25: four diners, plain rice added by code (4 × $2.00) plus a code top-up dish.
const dishes = [
  { id: "tomato_egg", name_en: "Tomato & Egg", price: 16, category: "stir_fry" },
  { id: "mongolian_beef", name_en: "Mongolian Beef", price: 19.5, category: "stir_fry" },
  { id: "lo_mein_vegetable", name_en: "Vegetable Lo Mein", price: 14, category: "other" },
  { id: "steamed_rice", name_en: "Steamed Rice", price: 2, category: "staple" },
];
const items = [{ dish_id: "tomato_egg", quantity: 1 }, { dish_id: "mongolian_beef", quantity: 1 }, { dish_id: "lo_mein_vegetable", quantity: 1 }, { dish_id: "steamed_rice", quantity: 4 }];
const subtotal = 16 + 19.5 + 14 + 8;
const plan = { items, subtotal, tax: 5.1, tip: 10.35, total: 72.95, per_person: 18.24, confirm_with_staff: [] as string[] };
const lines = ticketLines(plan, dishes);
eq(lines.map((l) => l.id), items.map((i) => i.dish_id), "every item listed, rice and top-up included");
eq(lines.find((l) => l.rice), { id: "steamed_rice", name: "Steamed Rice", nameZh: null, quantity: 4, unit: 2, total: 8, rice: true }, "rice count, unit and line total");
eq(linesSubtotal(lines), plan.subtotal, "lines add up to the plan subtotal (rice included)");
const text = ticketText("Cafe", 4, plan, dishes, "$");
eq(text.includes("Steamed Rice × 4  $2.00 each  $8.00"), true, "group-chat text lists rice");
eq(text.includes("Vegetable Lo Mein  $14.00"), true, "group-chat text lists the top-up dish");
eq(text.includes("Subtotal $57.50, tax $5.10, tip $10.35"), true, "group-chat text subtotal includes rice");
eq(text.includes("$18.24 each"), true, "per person from the plan");
eq(text.includes("no plain rice"), false, "no missing-rice note when rice is on the menu");
// A menu without plain rice (Cafe Mandarin): nothing is added, and the ticket says so.
const noRice = dishes.filter((d) => d.category !== "staple");
const plain = { ...plan, items: items.slice(0, 3), subtotal: 49.5 };
eq(linesSubtotal(ticketLines(plain, noRice)), 49.5, "no-rice menu still adds up");
eq(ticketText("Cafe", 4, plain, noRice, "$").includes("lists no plain rice"), true, "no-rice note");
// cents: 3 × $1.10 is $3.30, not 3.3000000000000003
eq(ticketLines({ ...plan, items: [{ dish_id: "x", quantity: 3 }] }, [{ id: "x", name_en: "X", price: 1.1, category: "staple" }])[0].total, 3.3, "cent-exact line total");
if (fails) throw new Error(`${fails} ticket test(s) failed`);
