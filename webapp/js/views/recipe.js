// Рецепт: оценка, КБЖУ на порцию, ингредиенты со светофором, шаги, запись в дневник.
import { api } from "../api.js";
import { go, store } from "../state.js";
import { LEVEL, busy, chip, html, isoDay, mount, num, sheet, showError, tg, toast } from "../ui.js";

export async function render(root, params) {
  let r;
  try {
    r = await api.get(`/api/recipes/${encodeURIComponent(params.id)}`);
  } catch (error) {
    mount(root, html`<div class="empty"><div class="big">😕</div>${error.message}</div>`);
    return;
  }
  const p = r.per_serving;
  mount(root, html`
    <section class="card food-hero"><div class="big-emoji">${r.emoji}</div><h1>${r.title}</h1>
      <div class="muted small">⏱ ${r.minutes} мин · 🍽 ${r.servings} ${r.servings === 1 ? "порция" : "порции"}</div>
      <p class="muted">${r.description}</p>
      <div class="verdict ${r.level}" style="text-align:left"><h2>${LEVEL[r.level].emoji} ${LEVEL[r.level].title}</h2>
        <div class="small">${r.stack.message}</div>
        ${r.problems.length ? html`<div class="small" style="margin-top:6px">Проблемные ингредиенты: <b>${r.problems.join(", ")}</b></div>` : ""}</div>
    </section>
    <div class="card" style="margin-top:12px"><b>На 1 порцию</b>
      <div class="nutri" style="margin-top:10px"><div><b>${num(p.kcal)}</b><small>ккал</small></div><div><b>${num(p.protein, 1)}</b><small>белки</small></div>
      <div><b>${num(p.fat, 1)}</b><small>жиры</small></div><div><b>${num(p.carbs, 1)}</b><small>углеводы</small></div></div></div>
    <div class="section-title"><h2>Ингредиенты</h2><button id="shop">＋ в покупки</button></div>
    <div class="card tight list">${r.ingredients.map((i) => html`<button class="item" data-food="${i.ref}">
      <span class="dot ${i.level}"></span><span class="grow"><span class="title">${i.emoji} ${i.name}</span>
      ${i.note ? html`<span class="meta" style="display:block">${i.note}</span>` : ""}
      ${i.level === "red" || i.level === "grey" ? html`<span class="meta" style="display:block;color:var(--red)">${i.reasons[0]}${i.swaps.length ? ` · замена: ${i.swaps.join(", ")}` : ""}</span>` : ""}</span>
      <span class="muted">${num(i.grams)} г</span></button>`)}</div>
    <div class="section-title"><h2>Приготовление</h2></div>
    <div class="card">${r.steps.map((s, n) => html`<div class="row" style="align-items:flex-start;margin-bottom:12px">
      <span class="chip plain" style="flex:none">${n + 1}</span><span>${s}</span></div>`)}</div>
    <button class="btn block" style="margin-top:14px" id="log">🍽 Я приготовил(а) — записать</button>
    <button class="btn ghost block" style="margin-top:10px" id="web">🌐 Похожие рецепты в интернете</button>`);

  root.querySelector("#web").addEventListener("click", () => tg?.openLink ? tg.openLink(r.search_url) : window.open(r.search_url, "_blank"));
  root.querySelector("#shop").addEventListener("click", (event) => busy(event.currentTarget, async () => {
    try {
      await api.post(`/api/recipes/${r.id}/shopping`);
      toast("Ингредиенты добавлены в список покупок 🛒", "success");
    } catch (error) { showError(error); }
  }));
  root.querySelector("#log").addEventListener("click", () => logSheet(r));
  root.addEventListener("click", (event) => {
    const el = event.target.closest("[data-food]");
    if (el) go(`/food/${encodeURIComponent(el.dataset.food)}`);
  });
}

function logSheet(r) {
  let meal = r.meals[0];
  let servings = 1;
  sheet(html`<h2>Записать «${r.title}»</h2>
    <div class="pills">${Object.entries(store.meta.meals).map(([c, m]) => html`<button class="pill ${c === meal ? "on" : ""}" data-m="${c}">${m.emoji} ${m.name}</button>`)}</div>
    <div class="row between" style="margin-top:14px"><b>Порций съедено</b><span class="grams" id="sv">1</span></div>
    <input class="slider" type="range" min="0.5" max="4" step="0.5" value="1" id="s">
    <button class="btn block" style="margin-top:10px" id="go">Записать ${chip(r.level)}</button>`, (el, close) => {
    el.querySelectorAll("[data-m]").forEach((p) => p.addEventListener("click", () => {
      meal = p.dataset.m;
      el.querySelectorAll("[data-m]").forEach((x) => x.classList.toggle("on", x === p));
    }));
    el.querySelector("#s").addEventListener("input", (e) => {
      servings = Number(e.target.value);
      el.querySelector("#sv").textContent = num(servings, 1);
    });
    el.querySelector("#go").addEventListener("click", (event) => busy(event.currentTarget, async () => {
      try {
        await api.post(`/api/recipes/${r.id}/log`, { day: isoDay(), meal, servings });
        close();
        toast("Записано в дневник 👩‍🍳", "success");
        go(`/diary`);
      } catch (error) { showError(error); }
    }));
  });
}
