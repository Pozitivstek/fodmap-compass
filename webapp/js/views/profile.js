// Профиль и настройки: ограничения, питание, тело и цели, тема, напоминания, данные.
import { api } from "../api.js";
import { THEME_NAMES, THEME_SWATCHES as SWATCHES, go, render as refresh, saveSettings, store } from "../state.js";
import { confirmAction, haptic, html, mount, num, showError, toast } from "../ui.js";

const MEAL_TIMES = ["breakfast", "lunch", "dinner"];

function choices(items, selected, attr) {
  return html`<div class="choices">${Object.entries(items).map(([code, item]) => html`<button class="choice ${selected.includes(code) ? "on" : ""}" data-${attr}="${code}">
    ${item.emoji || ""} ${item.name}${item.desc ? html`<small>${item.desc}</small>` : ""}</button>`)}</div>`;
}

function wordsField(id, label, words, placeholder) {
  return html`<label class="field"><span>${label}</span><input class="input" id="${id}" value="${words.join(", ")}" placeholder="${placeholder}"></label>`;
}

function themePicker(current) {
  return html`<div class="themes">${Object.entries(THEME_NAMES).map(([code, name]) => html`<button class="theme-swatch ${code === current ? "on" : ""}" data-theme-pick="${code}">
    <div class="sw">${SWATCHES[code].map((c) => html`<i style="background:${c}"></i>`)}</div>${name}</button>`)}</div>`;
}

export async function render(root) {
  const me = store.me;
  const s = me.settings;
  const meta = store.meta;
  const body = s.body || {};
  const rem = s.reminders || {};
  mount(root, html`
    <header class="topbar"><div><h1>Профиль</h1><div class="sub">${me.first_name || ""}${me.username ? ` · @${me.username}` : ""}</div></div></header>
    <div class="section-title"><h2>Мои ограничения</h2></div>
    <div class="card">${choices(meta.conditions, s.conditions, "cond")}</div>
    <div class="section-title"><h2>Питание</h2></div>
    <div class="card">${choices(meta.diet_styles, [s.diet_style], "diet")}
      ${wordsField("dislikes", "Не ем / не люблю (через запятую)", s.dislikes, "грибы, кинза, печень")}
      ${wordsField("likes", "Люблю (рецепты с этим — выше)", s.likes, "курица, рис, клубника")}
      <button class="btn block sm" style="margin-top:12px" id="save-words">Сохранить</button></div>
    <div class="section-title"><h2>Переносимые группы FODMAP</h2></div>
    <div class="card"><div class="small muted" style="margin-bottom:8px">Если после этапа повторного введения группа переносится хорошо — отметьте её, и она перестанет ограничивать оценки.</div>
      ${choices(meta.groups, s.tolerated_groups, "tolgroup")}</div>
    <div class="section-title"><h2>Тело и цели</h2></div>
    <div class="card">
      <div class="choices">${[["female", "👩 Женский"], ["male", "👨 Мужской"]].map(([c, n]) => html`<button class="choice ${body.sex === c ? "on" : ""}" data-sex="${c}">${n}</button>`)}</div>
      <div class="grid-3"><label class="field"><span>Год рождения</span><input class="input" id="birth_year" inputmode="numeric" value="${body.birth_year || ""}"></label>
        <label class="field"><span>Рост, см</span><input class="input" id="height" inputmode="decimal" value="${body.height || ""}"></label>
        <label class="field"><span>Вес, кг</span><input class="input" id="weight" inputmode="decimal" value="${body.weight || ""}"></label></div>
      <label class="field"><span>Активность</span><select class="input" id="activity">${Object.entries(meta.activity).map(([c, a]) => html`<option value="${c}" ${body.activity === c ? "selected" : ""}>${a.name}</option>`)}</select></label>
      <label class="field"><span>Цель</span><select class="input" id="goal">${Object.entries(meta.goals).map(([c, g]) => html`<option value="${c}" ${(body.goal || "keep") === c ? "selected" : ""}>${g.name}</option>`)}</select></label>
      <label class="field"><span>Вода в день, мл (рекомендуем ${num(me.suggested_water_ml)})</span><input class="input" id="water" inputmode="numeric" value="${s.water_goal_ml}"></label>
      <div class="small muted" style="margin-top:10px">Норма: <b>${num(me.targets.kcal)} ккал</b> · Б ${num(me.targets.protein)} · Ж ${num(me.targets.fat)} · У ${num(me.targets.carbs)} г</div>
      <button class="btn block sm" style="margin-top:12px" id="save-body">Пересчитать норму</button></div>
    <div class="section-title"><h2>Тема оформления</h2></div>
    <div class="card">${themePicker(s.theme)}</div>
    <div class="section-title"><h2>Напоминания в боте</h2></div>
    <div class="card">
      <label class="row between"><b>Напоминать</b><input type="checkbox" id="rem-on" ${rem.enabled ? "checked" : ""}></label>
      <div class="grid-3">${MEAL_TIMES.map((m) => html`<label class="field"><span>${meta.meals[m].emoji} ${meta.meals[m].name}</span>
        <input class="input" type="time" data-time="${m}" value="${rem.meals?.[m] || ""}"></label>`)}</div>
      <label class="row between" style="margin-top:12px"><span>💧 Про воду</span><input type="checkbox" id="rem-water" ${rem.water ? "checked" : ""}></label>
      <label class="row between" style="margin-top:8px"><span>🔥 Вечером, если день пустой</span><input type="checkbox" id="rem-evening" ${rem.evening ? "checked" : ""}></label>
      <label class="field"><span>Спросить о самочувствии после еды через</span><select class="input" id="rem-after">
        ${[[0, "не спрашивать"], [60, "1 час"], [120, "2 часа"], [150, "2,5 часа"], [180, "3 часа"], [240, "4 часа"]].map(([v, n]) =>
          html`<option value="${v}" ${Number(rem.after_meal_minutes) === v ? "selected" : ""}>${n}</option>`)}</select></label>
      <button class="btn block sm" style="margin-top:12px" id="save-rem">Сохранить напоминания</button></div>
    <div class="section-title"><h2>Ещё</h2></div>
    <div class="card list">
      <button class="item" data-go="/shopping"><span class="emoji">🛒</span><span class="grow title">Список покупок</span><span class="muted">›</span></button>
      <button class="item" data-go="/insights"><span class="emoji">📊</span><span class="grow title">Мои отметки и отчёт врачу</span><span class="muted">›</span></button>
      <button class="item" data-go="/onboarding"><span class="emoji">🧭</span><span class="grow title">Пройти знакомство заново</span><span class="muted">›</span></button>
      <button class="item" id="wipe"><span class="emoji">🗑</span><span class="grow title" style="color:var(--red)">Удалить все мои данные</span></button></div>
    <p class="small muted center" style="margin:18px 8px">ФудКомпас — справочник, а не врач. Порции основаны на открытых данных Monash University и Diet vs Disease. При тяжёлых симптомах обратитесь к гастроэнтерологу.</p>`);
  bind(root);
}

function words(root, id) {
  return root.querySelector(`#${id}`).value.split(",").map((w) => w.trim()).filter(Boolean);
}

function picked(root, attr) {
  return [...root.querySelectorAll(`[data-${attr}].on`)].map((el) => el.dataset[attr]);
}

async function save(patch, message = "Сохранено") {
  try {
    await saveSettings(patch);
    toast(message, "success");
    return true;
  } catch (error) {
    showError(error);
    return false;
  }
}

function bind(root) {
  root.addEventListener("click", async (event) => {
    const el = event.target.closest("[data-cond],[data-diet],[data-tolgroup],[data-sex],[data-theme-pick],[data-go],button[id]");
    if (!el) return;
    haptic("select");
    if (el.dataset.cond || el.dataset.tolgroup) {
      el.classList.toggle("on");
      const key = el.dataset.cond ? "conditions" : "tolerated_groups";
      return save({ [key]: picked(root, el.dataset.cond ? "cond" : "tolgroup") });
    }
    if (el.dataset.diet) {
      root.querySelectorAll("[data-diet]").forEach((c) => c.classList.toggle("on", c === el));
      return save({ diet_style: el.dataset.diet });
    }
    if (el.dataset.sex) return root.querySelectorAll("[data-sex]").forEach((c) => c.classList.toggle("on", c === el));
    if (el.dataset.themePick) {
      root.querySelectorAll("[data-theme-pick]").forEach((c) => c.classList.toggle("on", c === el));
      return save({ theme: el.dataset.themePick }, `Тема: ${THEME_NAMES[el.dataset.themePick]}`);
    }
    if (el.dataset.go) return go(el.dataset.go);
    const handlers = {
      "save-words": () => save({ dislikes: words(root, "dislikes"), likes: words(root, "likes") }),
      "save-body": async () => {
        const n = (id) => Number(String(root.querySelector(`#${id}`).value).replace(",", ".")) || null;
        const ok = await save({
          body: { sex: picked(root, "sex")[0] || null, birth_year: n("birth_year"), height: n("height"), weight: n("weight"),
            activity: root.querySelector("#activity").value, goal: root.querySelector("#goal").value },
          water_goal_ml: n("water") || 2000,
        }, "Норма пересчитана");
        if (ok) refresh();
      },
      "save-rem": () => save({ reminders: {
        enabled: root.querySelector("#rem-on").checked, water: root.querySelector("#rem-water").checked,
        evening: root.querySelector("#rem-evening").checked, after_meal_minutes: Number(root.querySelector("#rem-after").value),
        meals: Object.fromEntries([...root.querySelectorAll("[data-time]")].map((i) => [i.dataset.time, i.value])),
      } }),
      wipe: async () => {
        if (!(await confirmAction("Удалить дневник, отметки и настройки без возможности восстановления?"))) return;
        await api.del("/api/me");
        location.reload();
      },
    };
    try {
      await handlers[el.id]?.();
    } catch (error) {
      showError(error);
    }
  });
}
