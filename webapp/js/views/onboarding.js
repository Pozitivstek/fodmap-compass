// Знакомство: что такое FODMAP → ограничения → питание → тело → тема и напоминания.
import { THEME_NAMES, THEME_SWATCHES, applyTheme, go, saveSettings, store } from "../state.js";
import { haptic, html, mount, showError } from "../ui.js";

const STEPS = 5;

export async function render(root) {
  const s = store.me.settings;
  const state = {
    step: 0, conditions: [...s.conditions], diet_style: s.diet_style, dislikes: s.dislikes.join(", "),
    body: { ...(s.body || {}) }, theme: s.theme, reminders: s.reminders?.enabled ?? true,
  };
  const draw = () => {
    mount(root, html`<div class="steps">${Array.from({ length: STEPS }, (_, i) => html`<i class="${i <= state.step ? "on" : ""}"></i>`)}</div>
      ${screens[state.step](state)}
      <div class="sticky-bottom grid-2">${state.step ? html`<button class="btn ghost" id="prev">Назад</button>` : html`<span></span>`}
        <button class="btn" id="next">${state.step === STEPS - 1 ? "Начать 🚀" : "Дальше"}</button></div>`);
  };
  draw();
  root.addEventListener("input", (event) => {
    const el = event.target;
    if (el.id === "dislikes") state.dislikes = el.value;
    if (el.dataset.body) state.body[el.dataset.body] = Number(el.value.replace(",", ".")) || null;
  });
  root.addEventListener("click", async (event) => {
    const el = event.target.closest("[data-cond],[data-diet],[data-theme-pick],[data-sex],#prev,#next,#rem");
    if (!el) return;
    haptic("select");
    if (el.dataset.cond) {
      const code = el.dataset.cond;
      state.conditions = state.conditions.includes(code) ? state.conditions.filter((c) => c !== code) : [...state.conditions, code];
      el.classList.toggle("on");
      return;
    }
    if (el.dataset.diet) state.diet_style = el.dataset.diet;
    else if (el.dataset.sex) state.body.sex = el.dataset.sex;
    else if (el.dataset.themePick) { state.theme = el.dataset.themePick; applyTheme(state.theme); }
    else if (el.id === "rem") state.reminders = !state.reminders;
    else if (el.id === "prev") state.step -= 1;
    else if (el.id === "next") {
      if (state.step === 1 && !state.conditions.length) return showError(new Error("Выберите хотя бы одно ограничение"));
      if (state.step < STEPS - 1) state.step += 1;
      else return finish(state);
    }
    draw();
  });
}

async function finish(state) {
  try {
    await saveSettings({
      conditions: state.conditions, diet_style: state.diet_style, theme: state.theme, onboarded: true,
      dislikes: state.dislikes.split(",").map((w) => w.trim()).filter(Boolean),
      body: Object.fromEntries(Object.entries(state.body).filter(([, v]) => v)),
      tz: Intl.DateTimeFormat().resolvedOptions().timeZone || "Europe/Moscow",
      reminders: { enabled: state.reminders },
    });
    haptic("success");
    go("/home", { replace: true });
  } catch (error) {
    showError(error);
  }
}

const screens = [
  () => html`<div class="center"><div class="onb-emoji">🧭</div><h1 style="margin:0">ФудКомпас</h1>
    <p class="muted">Помощник для тех, кто следит за питанием из-за кишечника или аллергии.</p></div>
    <div class="card"><b>Что такое FODMAP?</b><p class="muted small" style="margin:6px 0 0">Это короткоцепочечные углеводы, которые плохо всасываются
      и бродят в кишечнике: <b>Ф</b>ерментируемые <b>О</b>лиго-, <b>Д</b>и-, <b>М</b>оносахариды <b>и</b> <b>П</b>олиолы. У людей с СРК они вызывают вздутие,
      боль, газы и расстройства стула.</p></div>
    <div class="card"><b>Диета идёт в 3 этапа</b><p class="muted small" style="margin:6px 0 0">1. Исключение (2–6 недель) — только безопасные порции.<br>
      2. Повторное введение — по одной группе, чтобы найти свои триггеры.<br>3. Личный рацион — ограничиваете только то, что реально мешает.</p></div>
    <div class="card"><b>Что я умею</b><p class="muted small" style="margin:6px 0 0">Подскажу, можно ли продукт и сколько, разберу состав по штрихкоду,
      посчитаю КБЖУ, запомню вашу реакцию на продукты и подберу рецепты.</p></div>`,
  (state) => html`<h1 style="margin:6px 0">Что у вас?</h1><p class="muted">Можно выбрать несколько — оценки продуктов подстроятся.</p>
    <div class="choices">${Object.entries(store.meta.conditions).map(([code, c]) => html`<button class="choice ${state.conditions.includes(code) ? "on" : ""}" data-cond="${code}">
      ${c.emoji} ${c.name}${c.desc ? html`<small>${c.desc}</small>` : ""}</button>`)}</div>`,
  (state) => html`<h1 style="margin:6px 0">Как вы питаетесь?</h1>
    <div class="choices">${Object.entries(store.meta.diet_styles).map(([code, d]) => html`<button class="choice ${state.diet_style === code ? "on" : ""}" data-diet="${code}">${d.emoji} ${d.name}</button>`)}</div>
    <label class="field"><span>Чего вы не едите или не любите?</span><input class="input" id="dislikes" value="${state.dislikes}" placeholder="грибы, кинза, печень"></label>`,
  (state) => html`<h1 style="margin:6px 0">Для подсчёта КБЖУ</h1><p class="muted">Можно пропустить — тогда возьмём средние нормы.</p>
    <div class="choices">${[["female", "👩 Женский"], ["male", "👨 Мужской"]].map(([c, n]) => html`<button class="choice ${state.body.sex === c ? "on" : ""}" data-sex="${c}">${n}</button>`)}</div>
    <div class="grid-3"><label class="field"><span>Год рождения</span><input class="input" data-body="birth_year" inputmode="numeric" value="${state.body.birth_year || ""}"></label>
      <label class="field"><span>Рост, см</span><input class="input" data-body="height" inputmode="decimal" value="${state.body.height || ""}"></label>
      <label class="field"><span>Вес, кг</span><input class="input" data-body="weight" inputmode="decimal" value="${state.body.weight || ""}"></label></div>`,
  (state) => html`<h1 style="margin:6px 0">Оформление</h1><div class="themes">${Object.entries(THEME_NAMES).map(([code, name]) =>
    html`<button class="theme-swatch ${state.theme === code ? "on" : ""}" data-theme-pick="${code}"><div class="sw">${THEME_SWATCHES[code].map((c) => html`<i style="background:${c}"></i>`)}</div>${name}</button>`)}</div>
    <button class="choice ${state.reminders ? "on" : ""}" id="rem" style="width:100%;margin-top:16px">🔔 Напоминания в боте<small>Спрошу о самочувствии после еды и напомню записать день</small></button>`,
];
