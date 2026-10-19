// Дневник: приёмы пищи за день, КБЖУ, накопление FODMAP, самочувствие и вода.
import { api, q } from "../api.js";
import { go, render as refresh, store } from "../state.js";
import { animateBars, busy, chip, dayLabel, haptic, html, isoDay, macroBar, mount, num, ring, sheet, shiftDay, showError, toast } from "../ui.js";

function reactionLine(r) {
  const meta = store.meta;
  const f = meta.feelings[r.feeling];
  const symptoms = r.symptoms.map((s) => `${meta.symptoms[s]?.emoji || ""} ${meta.symptoms[s]?.name || s}`).join(", ");
  return html`<div class="small" style="margin-top:6px">${f?.emoji} <b>${f?.name}</b>${symptoms ? ` · ${symptoms}` : ""}${r.severity ? ` · ${r.severity}/5` : ""}
    ${r.note ? html`<div class="muted">«${r.note}»</div>` : ""}</div>`;
}

function mealCard(meal, day) {
  const quickFeel = meal.entries.length && !meal.reactions.length;
  return html`<div class="card">
    <div class="row between"><div class="meal-head"><span class="em">${meal.emoji}</span><div><h3>${meal.name}</h3>
      <div class="small muted">${num(meal.totals.kcal)} ккал</div></div></div>
      ${meal.entries.length && meal.stack.level !== "green" ? chip(meal.stack.level, "накопление") : ""}</div>
    ${meal.entries.length ? html`<div class="list" style="margin-top:6px">${meal.entries.map((e) => html`<button class="item" data-entry="${e.id}">
      <span class="dot ${e.verdict.level}"></span><span class="grow"><span class="title ellipsis" style="display:block">${e.emoji} ${e.name}</span>
      <span class="meta">${num(e.grams)} г · ${num(e.macros.kcal)} ккал</span></span><span class="muted">›</span></button>`)}</div>` : ""}
    ${meal.entries.length && meal.stack.level !== "green" ? html`<div class="small" style="color:var(--${meal.stack.level === "red" ? "red" : "yellow"})">${meal.stack.message}</div>` : ""}
    ${meal.reactions.map(reactionLine)}
    ${quickFeel ? html`<div class="feel-row">${Object.entries(store.meta.feelings).map(([code, f]) =>
      html`<button class="feel" data-feel="${code}" data-meal="${meal.code}"><span>${f.emoji}</span>${f.name}</button>`)}</div>` : ""}
    <a class="add-line" href="#/add?meal=${meal.code}&day=${day}">＋ Добавить</a>
  </div>`;
}

export async function render(root, params) {
  const day = params.day || isoDay();
  mount(root, html`<div class="skeleton" style="height:300px"></div>`);
  let data;
  try {
    data = await api.get(`/api/diary${q({ day })}`);
  } catch (error) {
    showError(error);
    return;
  }
  const t = data.totals, g = data.targets;
  const dayReactions = data.reactions.filter((r) => !r.meal);
  mount(root, html`
    <div class="daynav"><button class="icon-btn" data-day="${shiftDay(day, -1)}" aria-label="Назад">‹</button>
      <label class="center"><b>${dayLabel(day)}</b><input type="date" id="pick" value="${day}" max="${isoDay()}" style="opacity:0;position:absolute;width:1px"></label>
      <button class="icon-btn" data-day="${shiftDay(day, 1)}" ${day >= isoDay() ? "disabled" : ""} aria-label="Вперёд">›</button></div>
    <div class="card"><div class="row">${ring(t.kcal, g.kcal)}<div class="grow">
      ${macroBar("Белки", t.protein, g.protein, "p")}${macroBar("Жиры", t.fat, g.fat, "f")}${macroBar("Углеводы", t.carbs, g.carbs, "c")}</div></div>
      <div class="row between" style="margin-top:10px"><span class="small muted">Клетчатка ${num(t.fiber, 1)} / ${num(g.fiber)} г</span>${chip(data.stack.level, data.stack.short)}</div></div>
    ${Object.values(data.meals).map((m) => mealCard(m, day))}
    <div class="card"><div class="row between"><b>💧 Вода: ${num(data.water.ml)} / ${num(data.water.goal)} мл</b>
      <div class="row" style="gap:6px"><button class="btn sm ghost" data-water="-250">−</button><button class="btn sm" data-water="250">+250</button></div></div></div>
    <div class="card"><div class="row between"><b>🩺 Самочувствие за день</b><a href="#/react?day=${day}">Записать</a></div>
      ${dayReactions.length ? dayReactions.map(reactionLine) : html`<div class="small muted">Нет записей</div>`}</div>`);
  animateBars(root);

  root.querySelector("label.center").addEventListener("click", () => root.querySelector("#pick").showPicker?.());
  root.querySelector("#pick").addEventListener("change", (e) => e.target.value && go(`/diary?day=${e.target.value}`, { replace: true }));
  root.addEventListener("click", async (event) => {
    const el = event.target.closest("[data-day],[data-entry],[data-feel],[data-water]");
    if (!el || el.disabled) return;
    haptic("light");
    try {
      if (el.dataset.day) return go(`/diary?day=${el.dataset.day}`, { replace: true });
      if (el.dataset.water) {
        return busy(el, async () => {
          await api.post("/api/water", { delta_ml: Number(el.dataset.water), day });
          refresh();
        });
      }
      if (el.dataset.feel) {
        const feeling = el.dataset.feel;
        if (feeling === "mild" || feeling === "bad") return go(`/react?day=${day}&meal=${el.dataset.meal}&feeling=${feeling}`);
        return busy(el, async () => {
          await api.post("/api/reactions", { day, meal: el.dataset.meal, feeling });
          toast("Записано 💚", "success");
          refresh();
        });
      }
      const entry = Object.values(data.meals).flatMap((m) => m.entries).find((e) => String(e.id) === el.dataset.entry);
      if (entry) editEntry(entry);
    } catch (error) {
      showError(error);
    }
  });
}

function editEntry(entry) {
  const reasons = entry.verdict.reasons;
  sheet(html`<h2>${entry.emoji} ${entry.name}</h2>
    <div class="small">${chip(entry.verdict.level)} ${reasons.join(" · ")}</div>
    <label class="field"><span>Граммы</span><input class="input" id="g" type="number" inputmode="decimal" value="${entry.grams}" min="1" max="3000"></label>
    <div class="pills" style="margin-top:12px">${Object.entries(store.meta.meals).map(([c, m]) => html`<button class="pill ${c === entry.meal ? "on" : ""}" data-m="${c}">${m.emoji} ${m.name}</button>`)}</div>
    <div class="grid-2" style="margin-top:14px"><button class="btn danger" id="del">Удалить</button><button class="btn" id="save">Сохранить</button></div>
    <button class="btn ghost block" style="margin-top:10px" id="open">Карточка продукта</button>`, (el, close) => {
    let meal = entry.meal;
    el.querySelectorAll("[data-m]").forEach((p) => p.addEventListener("click", () => {
      meal = p.dataset.m;
      el.querySelectorAll("[data-m]").forEach((x) => x.classList.toggle("on", x === p));
    }));
    el.querySelector("#save").addEventListener("click", async () => {
      try {
        await api.patch(`/api/diary/${entry.id}`, { grams: Number(el.querySelector("#g").value), meal });
        close(); refresh();
      } catch (error) { showError(error); }
    });
    el.querySelector("#del").addEventListener("click", async () => {
      try {
        await api.del(`/api/diary/${entry.id}`);
        close(); toast("Удалено"); refresh();
      } catch (error) { showError(error); }
    });
    el.querySelector("#open").addEventListener("click", () => { close(); go(`/food/${encodeURIComponent(entry.ref)}`); });
  });
}
