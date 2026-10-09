import type { DinerProfile, Eligibility, Menu, MenuSummary, Plan, PlanRequest, PlanResponse, SwapResponse, PreparedInput, ExtractionResponse, ProfileSnapshot } from "./types";

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

/** Let the AI replace one dish; every other dish in `plan` stays as it is. */
export const postSwap = (body: PlanRequest & { plan: Plan; dish_id: string | null; new_dish_id?: string | null }) =>
  request<SwapResponse>("/api/plan/swap", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const evaluateMenu = (menu: Menu, diners: DinerProfile[]) => request<Eligibility>("/api/menu/evaluate", {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ menu, diners }),
});
export const getHealth = () => request<{ok: boolean; mock: boolean; photo?: "openrouter" | "gemini" | "ocr" | null}>("/api/health");
export const parseMenu = (body: {text?: string; image_base64?: string}) => request<{ dishes: Menu["dishes"]; text: string; mode?: string; notice?: string; restaurant_name?: string | null }>("/api/menu/parse", {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});

export const getPreparedInputs = () => request<PreparedInput[]>("/api/model/prepared");
export const extractMenu = (body: {menu_id: string; text?: string; image_base64?: string}) =>
  request<ExtractionResponse>("/api/menu/extract", {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body),
  });
/** Everyone you add is saved here and can be picked for the next meal. One shared household
 * list for the class demo: a namespace, not a login. */
export const PEOPLE_SCOPE = "household";
const scopeHeaders = {"Content-Type": "application/json", "X-Profile-Scope": PEOPLE_SCOPE};
export const getSavedPeople = () => request<DinerProfile[]>("/api/profiles", {headers: scopeHeaders});
/** Create or replace the person's saved record (no revision needed, so it works after a reload). */
export const savePerson = (profile: DinerProfile) =>
  request<ProfileSnapshot>(`/api/profiles/${encodeURIComponent(profile.id)}`, {
    method: "PUT", headers: scopeHeaders, body: JSON.stringify({profile}),
  });
export const deletePerson = (id: string) =>
  request<{deleted: boolean}>(`/api/profiles/${encodeURIComponent(id)}`, {method: "DELETE", headers: scopeHeaders});

export const applyPeopleAction = (diners: DinerProfile[], action: "add" | "update" | "remove" | "load_preferences", extra: {person?: DinerProfile; person_id?: string; saved?: DinerProfile[]}) =>
  request<{diners: DinerProfile[]; recommendation_invalidated: boolean}>("/api/meal/people", {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({diners, action, ...extra}),
  });
