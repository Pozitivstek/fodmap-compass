// Список рецептов с фильтрами и оценкой под ограничения пользователя.
import { api, q } from "../api.js";
import { go, store } from "../state.js";
import { chip, haptic, html, mount, num, showError } from "../ui.js";

const DEBOUNCE_MS = 300;

function card(r) {
  return html`<button class="card tight" data-recipe="${r.id}" style="display:flex;gap:12px;width:100%;text-align:left;align-items:center">
    <span style="font-size:40px;flex:none">${r.emoji}</span>
    <span class="grow"><b style="display:block">${r.title}</b>
      <span class="small muted">${r.minutes} мин · ${num(r.per_serving.kcal)} ккал · Б ${num(r.per_serving.protein)} г</span>
      ${r.problems.length ? html`<span class="small" style="display:block;color:var(--red)">Не подходит: ${r.problems.join(", ")}</span>` : ""}
      <span style="display:block;margin-top:4px">${r.tags.slice(0, 3).map((t) => html`<span class="tag">${t}</span>`)}</span></span>
    ${chip(r.level)}</button>`;
}

export async function render(root, params) {
  const state = { meal: params.meal || "", query: params.q || "", safe: params.safe !== "0" };
  mount(root, html`
    <header class="topbar"><div><h1>Рецепты</h1><div class="sub">Подобраны под ваши ограничения</div></div>
      <button class="icon-btn" data-go="/shopping" aria-label="Покупки">🛒</button></header>
    <label class="search"><span>🔍</span><input id="q" type="search" placeholder="Курица, суп, без варки…" value="${state.query}"></label>
    <div class="pills" style="margin-top:12px">
      <button class="pill ${state.meal ? "" : "on"}" data-meal="">Все</button>
      ${Object.entries(store.meta.meals).map(([c, m]) => html`<button class="pill ${state.meal === c ? "on" : ""}" data-meal="${c}">${m.emoji} ${m.name}</button>`)}
      <button class="pill ${state.safe ? "on" : ""}" data-safe="1">✅ Только подходящие</button></div>
    <div id="list" class="stack" style="margin-top:8px"></div>`);
  const list = root.querySelector("#list");

  async function load() {
    history.replaceState(null, "", `#/recipes${q({ meal: state.meal, q: state.query, safe: state.safe ? "" : "0" })}`);
    try {
      const items = await api.get(`/api/recipes${q({ meal: state.meal, q: state.query, safe_only: state.safe })}`);
      mount(list, items.length ? html`${items.map(card)}` : html`<div class="empty"><div class="big">🍽️</div>Ничего не нашлось</div>`);
    } catch (error) {
      showError(error);
    }
  }
  let timer;
  root.querySelector("#q").addEventListener("input", (e) => {
    clearTimeout(timer);
    timer = setTimeout(() => { state.query = e.target.value.trim(); load(); }, DEBOUNCE_MS);
  });
  root.addEventListener("click", (event) => {
    const el = event.target.closest("[data-meal],[data-safe],[data-recipe],[data-go]");
    if (!el) return;
    haptic("select");
    if (el.dataset.recipe) return go(`/recipe/${el.dataset.recipe}`);
    if (el.dataset.go) return go(el.dataset.go);
    if (el.dataset.safe) {
      state.safe = !state.safe;
      el.classList.toggle("on", state.safe);
    } else {
      state.meal = el.dataset.meal;
      root.querySelectorAll("[data-meal]").forEach((p) => p.classList.toggle("on", p === el));
    }
    load();
  });
  load();
}
