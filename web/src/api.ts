import type { DinerProfile, Eligibility, Menu, MenuSummary, PlanRequest, PlanResponse, PreparedInput, ExtractionResponse, ProfileSnapshot } from "./types";

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

export const getPreparedInputs = () => request<PreparedInput[]>("/api/model/prepared");
export const extractMenu = (body: {menu_id: string; text?: string; image_base64?: string}) =>
  request<ExtractionResponse>("/api/menu/extract", {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body),
  });
const scopeHeaders = (scope: string) => ({"Content-Type": "application/json", "X-Profile-Scope": scope});
export const loadStoredProfiles = (scope: string) => request<DinerProfile[]>("/api/profiles", {headers: scopeHeaders(scope)});
export const profileHistory = (scope: string, id: string) => request<ProfileSnapshot[]>(`/api/profiles/${encodeURIComponent(id)}/history`, {headers: scopeHeaders(scope)});
export const persistProfile = (scope: string, profile: DinerProfile, revision: number) =>
  request<ProfileSnapshot>(revision ? `/api/profiles/${encodeURIComponent(profile.id)}` : "/api/profiles", {
    method: revision ? "PUT" : "POST", headers: scopeHeaders(scope),
    body: JSON.stringify(revision ? {profile, expected_revision: revision} : profile),
  });

export const applyPeopleAction = (diners: DinerProfile[], action: "add" | "update" | "remove" | "load_preferences", extra: {person?: DinerProfile; person_id?: string; saved?: DinerProfile[]}) =>
  request<{diners: DinerProfile[]; recommendation_invalidated: boolean}>("/api/meal/people", {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({diners, action, ...extra}),
  });
