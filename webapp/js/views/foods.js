// Справочник: поиск по базе и Open Food Facts, категории, недавнее.
import { api, q } from "../api.js";
import { go } from "../state.js";
import { foodRow, haptic, html, mount, showError } from "../ui.js";

const DEBOUNCE_MS = 350;

export async function render(root, params) {
  const state = { query: params.q || "", category: params.category || "" };
  const categories = await api.get("/api/foods/categories").catch(() => []);
  mount(root, html`
    <header class="topbar"><div><h1>Продукты</h1><div class="sub">Можно ли, сколько и что внутри</div></div>
      <button class="icon-btn" data-go="/scan" aria-label="Сканер">📷</button></header>
    <label class="search"><span>🔍</span><input id="q" type="search" placeholder="Авокадо, кефир, «Активиа»…"
      value="${state.query}" autocomplete="off" enterkeyhint="search"><button class="btn sm ghost" data-go="/scan">Штрихкод</button></label>
    <div class="pills" style="margin-top:12px" id="cats">
      <button class="pill ${state.category ? "" : "on"}" data-cat="">Все</button>
      ${categories.map((c) => html`<button class="pill ${state.category === c.code ? "on" : ""}" data-cat="${c.code}">${c.emoji} ${c.name}</button>`)}
    </div>
    <div id="results"></div>`);
  const input = root.querySelector("#q");
  const results = root.querySelector("#results");
  let timer;
  let seq = 0;

  async function load() {
    const id = ++seq;
    history.replaceState(null, "", `#/foods${q({ q: state.query, category: state.category })}`);
    if (!state.query && !state.category) return renderStart(results, categories);
    mount(results, html`<div class="skeleton" style="height:220px;margin-top:12px"></div>`);
    try {
      const data = await api.get(`/api/foods/search${q({ q: state.query, category: state.category })}`);
      if (id === seq) renderResults(results, data);
    } catch (error) {
      showError(error);
    }
  }

  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(() => { state.query = input.value.trim(); load(); }, DEBOUNCE_MS);
  });
  root.addEventListener("click", (event) => {
    const el = event.target.closest("[data-cat],[data-food],[data-go]");
    if (!el) return;
    event.preventDefault();
    haptic("select");
    if (el.dataset.go) return go(el.dataset.go);
    if (el.dataset.food) return go(`/food/${encodeURIComponent(el.dataset.food)}`);
    state.category = el.dataset.cat;
    root.querySelectorAll("[data-cat]").forEach((p) => p.classList.toggle("on", p.dataset.cat === state.category));
    load();
  });
  load();
}

async function renderStart(el, categories) {
  const [recent, tolerances] = await Promise.all([
    api.get("/api/foods/recent").catch(() => []), api.get("/api/foods/tolerances").catch(() => []),
  ]);
  const marks = { ok: "💚", caution: "💛", avoid: "❤️‍🩹" };
  mount(el, html`
    ${recent.length ? html`<div class="section-title"><h2>Недавние</h2></div>
      <div class="pills">${recent.map((r) => html`<button class="pill" data-food="${r.ref}">${r.emoji} ${r.name}</button>`)}</div>` : ""}
    ${tolerances.length ? html`<div class="section-title"><h2>Мои отметки</h2></div>
      <div class="card tight list">${tolerances.slice(0, 8).map((t) => html`<button class="item" data-food="${t.ref}">
        <span class="emoji">${marks[t.status]}</span><span class="grow"><span class="title">${t.name}</span>
        <span class="meta" style="display:block">${t.ok_count} хорошо · ${t.mild_count + t.bad_count} с симптомами${t.tested_g ? ` · проверено до ${t.tested_g} г` : ""}</span></span></button>`)}</div>` : ""}
    <div class="section-title"><h2>Категории</h2></div>
    <div class="tiles">${categories.map((c) => html`<button class="tile" data-cat="${c.code}"><span class="big">${c.emoji}</span>
      <b>${c.name}</b><span class="small muted">${c.count} продуктов</span></button>`)}</div>
    <div class="card" style="margin-top:12px"><b>🛒 Не нашли продукт?</b>
      <div class="small muted">Введите название товара из магазина — поищем в Open Food Facts, или отсканируйте штрихкод.</div></div>`);
}

function renderResults(el, data) {
  const empty = !data.catalog.length && !data.products.length;
  mount(el, html`
    ${data.catalog.length ? html`<div class="section-title"><h2>В справочнике</h2><span class="small muted">${data.catalog.length}</span></div>
      <div class="card tight list">${data.catalog.map((f) => foodRow(f))}</div>` : ""}
    ${data.products.length ? html`<div class="section-title"><h2>Товары из магазинов</h2><span class="small muted">Open Food Facts</span></div>
      <div class="card tight list">${data.products.map((f) => foodRow(f))}</div>` : ""}
    ${data.external_error ? html`<p class="small muted center">${data.external_error}</p>` : ""}
    ${empty ? html`<div class="empty"><div class="big">🤷</div>Ничего не нашлось.<br>Попробуйте иначе или отсканируйте штрихкод.</div>` : ""}`);
}
