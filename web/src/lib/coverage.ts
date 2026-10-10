import type { DinerStatusMap } from "../types";

/** Per-diner counts read only from the backend's diner_status (QA r18): "ok" dishes they can
 *  eat as is, "confirm" dishes they can eat once the server confirms. Pass non-staple items. */
export function dinerCounts(items: { status?: DinerStatusMap }[], dinerIds: string[]) {
  return Object.fromEntries(dinerIds.map((id) => [id, {
    // a taste conflict (too spicy for them) is not their dish (2026-10-10)
    ok: items.filter((i) => i.status?.[id]?.status === "ok" && i.status?.[id]?.taste !== "too_spicy").length,
    confirm: items.filter((i) => i.status?.[id]?.status === "needs_confirm" && i.status?.[id]?.taste !== "too_spicy").length,
  }])) as Record<string, { ok: number; confirm: number }>;
}

/** The order checklist's coverage line, same rule as the backend code_summary: "everyone can
 *  eat" only when every diner has at least one "ok" dish. */
export function coverageLabel(items: { status?: DinerStatusMap }[], diners: { id: string; name: string }[]): { passed: boolean; label: string } {
  const c = dinerCounts(items, diners.map((p) => p.id));
  const none = diners.filter((p) => c[p.id].ok + c[p.id].confirm === 0);
  const askOnly = diners.filter((p) => c[p.id].ok === 0 && c[p.id].confirm > 0);
  const names = (ps: { name: string }[]) => ps.length === 1 ? ps[0].name : ps.slice(0, -1).map((p) => p.name).join(", ") + " and " + ps[ps.length - 1].name;
  if (none.length) return { passed: false, label: `${names(none)} ${none.length === 1 ? "has" : "have"} nothing to eat` };
  if (askOnly.length) return { passed: true, label: `Everyone has a dish, ${names(askOnly)} only if the server confirms` };
  return { passed: true, label: "Everyone has a dish they can eat" };
}

/** Checks that only warn: they are shown, never block the order ticket (QA r20 D-7). */
export const WARN_CHECKS = new Set(["enough"]);

/** Why the order ticket is blocked, or null. Only hard failures block, and always say why. */
export function orderBlock(p: { checks: { name: string; passed: boolean; detail?: string }[] } | null, stale: boolean, loading: boolean): string | null {
  if (!p) return "No order yet.";
  if (loading) return "Updating the order…";
  if (stale) return "The order is out of date; update it first.";
  const hard = p.checks.find((c) => !c.passed && !WARN_CHECKS.has(c.name));
  return hard ? `Can't show the ticket: ${hard.detail || hard.name}` : null;
}
