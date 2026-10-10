import { coverageLabel, dinerCounts } from "./coverage";

const ok = { status: "ok" as const, reason: null };
const ask = { status: "needs_confirm" as const, reason: "halal" };
const no = { status: "no" as const, reason: "meat" };
const diners = [{ id: "ben", name: "Ben" }, { id: "mia", name: "Mia" }];
let fails = 0;
function eq(a: unknown, b: unknown, what: string) {
  if (JSON.stringify(a) !== JSON.stringify(b)) { fails++; console.error("FAIL", what, a, "!=", b); } else console.log("ok", what);
}
// QA r18 repro: Mia (halal) has only needs_confirm dishes
const r18 = [{ status: { ben: ok, mia: ask } }, { status: { ben: ok, mia: ask } }, { status: { ben: no, mia: ask } }];
eq(coverageLabel(r18, diners), { passed: true, label: "Everyone has a dish, Mia only if the server confirms" }, "mia ask-only");
eq(/everyone can eat/i.test(coverageLabel(r18, diners).label), false, "no false everyone-can-eat");
eq(dinerCounts(r18, ["ben", "mia"]), { ben: { ok: 2, confirm: 0 }, mia: { ok: 0, confirm: 3 } }, "counts from status");
eq(coverageLabel([{ status: { ben: ok, mia: ok } }], diners), { passed: true, label: "Everyone has a dish they can eat" }, "all ok");
eq(coverageLabel([{ status: { ben: no, mia: ok } }], diners), { passed: false, label: "Ben has nothing to eat" }, "ben none");
eq(coverageLabel([{ status: { ben: ask, mia: ask } }], diners).label, "Everyone has a dish, Ben and Mia only if the server confirms", "both ask");
eq(coverageLabel([{}], diners).passed, false, "missing status is not a pass");
// 2026-10-10: a too-spicy dish is not counted for a no-heat diner
const hot = { status: "ok" as const, reason: null, taste: "too_spicy" as const };
eq(coverageLabel([{ status: { ben: ok, mia: hot } }], diners), { passed: false, label: "Mia has nothing to eat" }, "too spicy not counted");
eq(dinerCounts([{ status: { ben: ok, mia: hot } }, { status: { ben: ok, mia: ok } }], ["mia"]), { mia: { ok: 1, confirm: 0 } }, "count skips too spicy");
if (fails) throw new Error(`${fails} coverage test(s) failed`);
