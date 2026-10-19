// Быстрое добавление еды в дневник: поиск → порция → записать.
import { api, q } from "../api.js";
import { go, store } from "../state.js";
import { LEVEL, busy, chip, dayLabel, foodRow, haptic, html, isoDay, mount, num, sheet, showError, toast } from "../ui.js";
import { levelFor } from "./food.js";

const DEBOUNCE_MS = 350;

function mealByHour() {
  const hour = new Date().getHours();
  return hour < 5 ? "snack" : hour < 11 ? "breakfast" : hour < 16 ? "lunch" : hour < 21 ? "dinner" : "snack";
}

function portionSheet(card, state, onSaved) {
  let grams = card.portion.grams;
  const max = Math.max(300, (card.high_g || card.low_g || 100) * 2.5);
  const quick = [0.5, 1, 1.5, 2].map((k) => Math.round(card.portion.grams * k));
  const body = () => {
    const level = levelFor(card, grams);
    return html`<div class="row between"><span class="grams">${num(grams)} г</span>${chip(level)}</div>
      <div class="small muted">${num((card.per100.kcal * grams) / 100)} ккал · Б ${num((card.per100.protein * grams) / 100, 1)} · Ж ${num((card.per100.fat * grams) / 100, 1)} · У ${num((card.per100.carbs * grams) / 100, 1)}</div>
      ${card.verdict.safe_g ? html`<div class="small" style="margin-top:4px">Безопасно до <b>${num(card.verdict.safe_g)} г</b></div>` : ""}`;
  };
  sheet(html`<h2>${card.emoji} ${card.name}</h2><div id="live">${body()}</div>
    <input class="slider" type="range" min="1" max="${max}" value="${grams}" id="g">
    <div class="pills">${quick.map((g) => html`<button class="pill" data-g="${g}">${g} г</button>`)}</div>
    <button class="btn block" style="margin-top:12px" id="save">Записать в «${store.meta.meals[state.meal].name.toLowerCase()}»</button>`,
  (el, close) => {
    const live = el.querySelector("#live");
    const slider = el.querySelector("#g");
    const update = () => { mount(live, body()); };
    slider.addEventListener("input", () => { grams = Number(slider.value); update(); });
    el.querySelectorAll("[data-g]").forEach((b) => b.addEventListener("click", () => {
      grams = Number(b.dataset.g); slider.value = grams; update(); haptic("select");
    }));
    el.querySelector("#save").addEventListener("click", (event) => busy(event.currentTarget, async () => {
      try {
        await api.post("/api/diary", { ref: card.ref, day: state.day, meal: state.meal, grams });
        close();
        onSaved(card, grams, levelFor(card, grams));
      } catch (error) { showError(error); }
    }));
  });
}

async function openFood(ref, state, onSaved) {
  try {
    const card = await api.get(`/api/foods/item${q({ ref })}`);
    portionSheet(card, state, onSaved);
  } catch (error) { showError(error); }
}

export async function render(root, params) {
  const state = { day: params.day || isoDay(), meal: params.meal || mealByHour(), added: [] };
  const recent = await api.get("/api/foods/recent").catch(() => []);
  mount(root, html`
    <header class="topbar"><div><h1>Что вы съели?</h1><div class="sub">${dayLabel(state.day)}</div></div>
      <button class="icon-btn" data-go="/scan" aria-label="Сканер">📷</button></header>
    <div class="pills">${Object.entries(store.meta.meals).map(([code, m]) => html`<button class="pill ${code === state.meal ? "on" : ""}" data-meal="${code}">${m.emoji} ${m.name}</button>`)}</div>
    <label class="search" style="margin-top:10px"><span>🔍</span><input id="q" type="search" placeholder="Название продукта" autocomplete="off"></label>
    <div id="added"></div>
    <div id="results">${recent.length ? html`<div class="section-title"><h2>Недавние</h2></div>
      <div class="card tight list">${recent.map((r) => html`<button class="item" data-food="${r.ref}"><span class="emoji">${r.emoji}</span>
        <span class="grow title">${r.name}</span><span class="muted small">${num(r.grams)} г</span></button>`)}</div>` : ""}</div>
    <button class="btn block ghost" style="margin-top:14px" id="custom">⭐ Создать свой продукт</button>
    <button class="btn block" style="margin-top:10px" id="done">Готово</button>`);

  const onSaved = (card, grams, level) => {
    state.added.push({ name: card.name, grams, level });
    toast(`${LEVEL[level].emoji} ${card.name} — ${num(grams)} г`, "success");
    mount(root.querySelector("#added"), html`<div class="card tight" style="margin-top:12px"><b>Добавлено</b>
      ${state.added.map((a) => html`<div class="row between small" style="margin-top:6px"><span>${a.name}</span><span>${num(a.grams)} г ${LEVEL[a.level].emoji}</span></div>`)}</div>`);
  };
  if (params.ref) openFood(params.ref, state, onSaved);

  const input = root.querySelector("#q");
  let timer;
  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const text = input.value.trim();
      if (text.length < 2) return;
      try {
        const data = await api.get(`/api/foods/search${q({ q: text })}`);
        const items = [...data.catalog, ...data.products];
        mount(root.querySelector("#results"), items.length
          ? html`<div class="card tight list" style="margin-top:12px">${items.map((f) => foodRow(f))}</div>`
          : html`<div class="empty">Не нашлось. Создайте свой продукт ниже.</div>`);
      } catch (error) { showError(error); }
    }, DEBOUNCE_MS);
  });
  root.addEventListener("click", (event) => {
    const el = event.target.closest("[data-meal],[data-food],[data-go],#done,#custom");
    if (!el) return;
    if (el.dataset.meal) {
      state.meal = el.dataset.meal;
      root.querySelectorAll("[data-meal]").forEach((p) => p.classList.toggle("on", p === el));
      haptic("select");
    } else if (el.dataset.food) openFood(el.dataset.food, state, onSaved);
    else if (el.dataset.go) go(el.dataset.go);
    else if (el.id === "done") go(`/diary?day=${state.day}`);
    else if (el.id === "custom") customSheet(state, onSaved);
  });
}

function customSheet(state, onSaved) {
  const groups = store.meta.groups;
  const allergens = store.meta.allergens;
  sheet(html`<h2>⭐ Свой продукт</h2>
    <label class="field"><span>Название</span><input class="input" id="name" maxlength="80" placeholder="Например, бабушкины сырники"></label>
    <div class="grid-2"><label class="field"><span>Ккал на 100 г</span><input class="input" id="kcal" inputmode="decimal"></label>
      <label class="field"><span>Белки, г</span><input class="input" id="protein" inputmode="decimal"></label>
      <label class="field"><span>Жиры, г</span><input class="input" id="fat" inputmode="decimal"></label>
      <label class="field"><span>Углеводы, г</span><input class="input" id="carbs" inputmode="decimal"></label></div>
    <div class="field"><span>Есть ли внутри (если знаете)</span><div class="choices">${Object.entries(groups).map(([c, g]) => html`<button class="choice" data-group="${c}">${g.name}</button>`)}</div></div>
    <div class="field"><span>Аллергены</span><div class="choices">${Object.entries(allergens).map(([c, n]) => html`<button class="choice" data-allergen="${c}">${n}</button>`)}</div></div>
    <button class="btn block" style="margin-top:16px" id="create">Сохранить</button>`, (el, close) => {
    el.querySelectorAll(".choice").forEach((c) => c.addEventListener("click", () => c.classList.toggle("on")));
    el.querySelector("#create").addEventListener("click", (event) => busy(event.currentTarget, async () => {
      const val = (id) => Number(String(el.querySelector(`#${id}`).value).replace(",", ".")) || 0;
      const picked = (attr) => [...el.querySelectorAll(`[data-${attr}].on`)].map((c) => c.dataset[attr]);
      try {
        const card = await api.post("/api/foods/custom", {
          name: el.querySelector("#name").value.trim(), kcal: val("kcal"), protein: val("protein"), fat: val("fat"),
          carbs: val("carbs"), groups: picked("group"), allergens: picked("allergen"),
        });
        close();
        portionSheet(card, state, onSaved);
      } catch (error) { showError(error); }
    }));
  });
}
