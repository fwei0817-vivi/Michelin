import type { DinerProfile, Eligibility, Menu, MenuSummary, PlanRequest, PlanResponse } from "./types";

// Same origin by default. Set window.MICHELIN_API when the page is hosted elsewhere.
const API: string = (window as unknown as { MICHELIN_API?: string }).MICHELIN_API ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(API + path, init);
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) detail = body.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch {
      /* not JSON */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const getMenus = () => request<MenuSummary[]>("/api/menus");
export const getMenu = (slug: string) => request<Menu>(`/api/menus/${encodeURIComponent(slug)}`);
export const getProfiles = () => request<DinerProfile[]>("/api/profiles");
export const postPlan = (body: PlanRequest) =>
  request<PlanResponse>("/api/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const evaluateMenu = (menu: Menu, diners: DinerProfile[]) => request<Eligibility>("/api/menu/evaluate", {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ menu, diners }),
});
export const getHealth = () => request<{ok: boolean; mock: boolean}>("/api/health");
export const parseMenu = (body: {text?: string; image_base64?: string}) => request<{ dishes: Menu["dishes"]; text: string }>("/api/menu/parse", {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});
