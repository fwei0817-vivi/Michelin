// Frontend for the Michelin API. No build step: plain fetch + DOM.
// Same-origin by default; set window.MICHELIN_API when the page is hosted elsewhere.
const API = window.MICHELIN_API || "";

const $ = (sel) => document.querySelector(sel);
const state = { menus: [], profiles: [], menu: null };

async function getJSON(path) {
  const res = await fetch(API + path);
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

async function postJSON(path, body) {
  const res = await fetch(API + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `${res.status}`);
  return data;
}

function money(x) {
  return `$${Number(x).toFixed(2)}`;
}

function selectedDinerIds() {
  return [...document.querySelectorAll("#diners input:checked")].map((el) => el.value);
}

function updateCapHint() {
  const n = selectedDinerIds().length;
  const budget = Number($("#budget").value);
  const tax = Number($("#tax").value);
  const tip = Number($("#tip").value);
  if (!n) { $("#cap-hint").textContent = "Pick at least one diner."; return; }
  const cap = (budget * n) / (1 + tax + tip);
  $("#cap-hint").textContent =
    `Menu-price cap for ${n} people: ${money(cap)} (${money(cap / n)} each after tax and tip).`;
  $("#plan").disabled = n === 0;
}

function renderDiners() {
  const box = $("#diners");
  box.innerHTML = "";
  for (const p of state.profiles) {
    const tags = [...p.allergies.map((a) => `no ${a}`), ...p.diets].join(", ");
    const label = document.createElement("label");
    label.className = "diner";
    label.innerHTML =
      `<input type="checkbox" value="${p.id}" checked> ${p.name}` +
      (tags ? ` <span class="tags">· ${tags}</span>` : "");
    box.appendChild(label);
  }
}

function renderMenus() {
  const sel = $("#menu");
  sel.innerHTML = "";
  for (const m of state.menus) {
    const opt = document.createElement("option");
    opt.value = m.slug;
    opt.textContent = m.restaurant_name;
    sel.appendChild(opt);
  }
  updateMenuHint();
}

function updateMenuHint() {
  const m = state.menus.find((x) => x.slug === $("#menu").value);
  if (!m) return;
  $("#menu-hint").textContent =
    `${m.n_dishes} dishes · ${m.cuisine}` + (m.verified ? " · verified" : " · NOT verified yet");
}

function dishById(id) {
  return state.menu.dishes.find((d) => d.id === id);
}

function renderPlan(data) {
  const plan = data.plan;
  const out = $("#result");
  out.hidden = false;
  out.innerHTML = "";

  const allOk = plan.checks.every((c) => c.passed);
  const banner = document.createElement("div");
  banner.className = `banner ${allOk ? "ok" : "error"}`;
  banner.textContent = allOk ? "All hard constraints satisfied." : "Some checks failed.";
  out.appendChild(banner);

  const cards = document.createElement("div");
  cards.className = "cards";
  const tpl = $("#dish-card");
  const diners = Object.fromEntries(state.profiles.map((p) => [p.id, p.name]));
  for (const item of plan.items) {
    const d = dishById(item.dish_id);
    const node = tpl.content.cloneNode(true);
    node.querySelector(".name-en").textContent = d.name_en || d.id;
    node.querySelector(".name-zh").textContent = d.name_zh || "";
    node.querySelector(".meta").textContent =
      `${money(d.price)} × ${item.quantity} · ${d.category} · spice ${d.spice_level}`;
    node.querySelector(".reason").textContent = item.reason || "";
    node.querySelector(".ok-for").textContent =
      "OK for: " + item.edible_by.map((id) => diners[id] || id).join(", ");
    const flags = node.querySelector(".flags");
    for (const f of d.allergens) {
      const li = document.createElement("li");
      li.textContent = `${f.allergen} (${f.tier}, ${Math.round(f.confidence * 100)}%) — ${f.reason}`;
      flags.appendChild(li);
    }
    cards.appendChild(node);
  }
  out.appendChild(cards);

  const totals = document.createElement("p");
  totals.className = "totals";
  totals.innerHTML =
    `Subtotal ${money(plan.subtotal)} · tax ${money(plan.tax)} · tip ${money(plan.tip)} · ` +
    `<strong>total ${money(plan.total)}</strong> (${money(plan.per_person)} / person) · variety ${plan.variety_score.toFixed(2)}`;
  out.appendChild(totals);

  if (plan.confirm_with_staff.length) {
    const box = document.createElement("div");
    box.className = "confirm";
    box.innerHTML = "<h3>Ask the waiter · 请向服务员确认</h3><ul>" +
      plan.confirm_with_staff.map((q) => `<li>${q}</li>`).join("") + "</ul>";
    out.appendChild(box);
  }
}

function renderConflict(data) {
  const out = $("#result");
  out.hidden = false;
  out.innerHTML = "";
  const banner = document.createElement("div");
  banner.className = "banner error";
  banner.textContent = data.conflict.message;
  out.appendChild(banner);
  if (data.conflict.relaxations.length) {
    const box = document.createElement("div");
    box.className = "panel relax";
    box.innerHTML = "<p>Any one of these would make an order possible:</p><ul>" +
      data.conflict.relaxations.map((r) => `<li>${r.description}</li>`).join("") + "</ul>";
    out.appendChild(box);
  }
}

function renderError(message, level = "error") {
  const out = $("#result");
  out.hidden = false;
  out.innerHTML = `<div class="banner ${level}">${message}</div>`;
}

async function onPlan() {
  $("#plan").disabled = true;
  try {
    state.menu = await getJSON(`/api/menus/${$("#menu").value}`);
    const data = await postJSON("/api/plan", {
      menu_id: $("#menu").value,
      diner_ids: selectedDinerIds(),
      budget_per_person: Number($("#budget").value),
      tax_rate: Number($("#tax").value),
      tip_rate: Number($("#tip").value),
      min_dishes_per_person: Number($("#min-dishes").value),
      explain: $("#explain").checked,
    });
    if (data.kind === "conflict") renderConflict(data);
    else renderPlan(data);
  } catch (err) {
    renderError(String(err.message || err), /not implemented/i.test(err.message) ? "warn" : "error");
  } finally {
    $("#plan").disabled = false;
  }
}

async function init() {
  [state.menus, state.profiles] = await Promise.all([getJSON("/api/menus"), getJSON("/api/profiles")]);
  renderMenus();
  renderDiners();
  updateCapHint();
  $("#menu").addEventListener("change", updateMenuHint);
  $("#diners").addEventListener("change", updateCapHint);
  for (const id of ["#budget", "#tax", "#tip"]) $(id).addEventListener("input", updateCapHint);
  $("#plan").addEventListener("click", onPlan);
}

init().catch((err) => renderError(`Could not reach the API: ${err.message}`));
