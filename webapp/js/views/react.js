// Запись самочувствия: варианты ответа, симптомы, сила и свой текст.
import { api, q } from "../api.js";
import { back, store } from "../state.js";
import { busy, dayLabel, haptic, html, isoDay, mount, sheet, showError } from "../ui.js";

const MARK_TEXT = { ok: "💚 подходит вам", caution: "💛 осторожно", avoid: "❤️‍🩹 вам не подходит" };

export async function render(root, params) {
  const meta = store.meta;
  const state = {
    day: params.day || isoDay(), meal: params.meal || (params.ref ? "" : "day"), feeling: params.feeling || "",
    symptoms: new Set(), severity: params.feeling === "bad" ? 3 : params.feeling === "mild" ? 1 : 0,
  };
  let title = "Как вы себя чувствуете?";
  if (params.ref) {
    const card = await api.get(`/api/foods/item${q({ ref: params.ref })}`).catch(() => null);
    title = card ? `Как вы перенесли «${card.name}»?` : title;
  }
  mount(root, html`
    <header class="topbar"><div><h1>${title}</h1><div class="sub">${dayLabel(state.day)}</div></div></header>
    ${params.ref ? "" : html`<div class="pills">${[["day", "🗓 Весь день"], ...Object.entries(meta.meals).map(([c, m]) => [c, `${m.emoji} ${m.name}`])]
      .map(([code, label]) => html`<button class="pill ${state.meal === code ? "on" : ""}" data-meal="${code}">${label}</button>`)}</div>`}
    <div class="feel-row" style="margin-top:14px">${Object.entries(meta.feelings).map(([code, f]) =>
      html`<button class="feel ${state.feeling === code ? "on" : ""}" data-feel="${code}"><span>${f.emoji}</span>${f.name}</button>`)}</div>
    <div class="section-title"><h2>Симптомы</h2><span class="small muted">можно несколько</span></div>
    <div class="choices">${Object.entries(meta.symptoms).map(([code, s]) => html`<button class="choice" data-symptom="${code}">${s.emoji} ${s.name}</button>`)}</div>
    <div class="card" style="margin-top:14px" id="sev"><div class="row between"><b>Сила симптомов</b><b id="sevv">${state.severity}/5</b></div>
      <input class="slider" type="range" min="0" max="5" value="${state.severity}" id="severity"></div>
    <label class="field"><span>Своими словами</span><textarea class="input" id="note" maxlength="500" placeholder="Например: тяжесть через час, к вечеру прошло"></textarea></label>
    <button class="btn block sticky-bottom" id="save">Сохранить</button>`);

  root.querySelector("#severity").addEventListener("input", (e) => {
    state.severity = Number(e.target.value);
    root.querySelector("#sevv").textContent = `${state.severity}/5`;
  });
  root.addEventListener("click", async (event) => {
    const el = event.target.closest("[data-meal],[data-feel],[data-symptom],#save");
    if (!el) return;
    haptic("select");
    if (el.dataset.meal) {
      state.meal = el.dataset.meal;
      root.querySelectorAll("[data-meal]").forEach((p) => p.classList.toggle("on", p === el));
    } else if (el.dataset.feel) {
      state.feeling = el.dataset.feel;
      root.querySelectorAll("[data-feel]").forEach((p) => p.classList.toggle("on", p === el));
    } else if (el.dataset.symptom) {
      const code = el.dataset.symptom;
      state.symptoms.has(code) ? state.symptoms.delete(code) : state.symptoms.add(code);
      el.classList.toggle("on");
    } else if (el.id === "save") {
      await busy(el, () => save(root, params, state));
    }
  });
}

async function save(root, params, state) {
  if (!state.feeling) {
    showError(new Error("Выберите, как вы себя чувствуете"));
    return;
  }
  try {
    const res = await api.post("/api/reactions", {
      day: state.day, meal: state.meal && state.meal !== "day" ? state.meal : null, ref: params.ref || null,
      feeling: state.feeling, symptoms: [...state.symptoms], severity: state.severity,
      note: root.querySelector("#note").value.trim(), grams: params.grams ? Number(params.grams) : null,
    });
    haptic("success");
    sheet(html`<div class="center"><div style="font-size:52px">✅</div><h2>Записано</h2>
      ${res.updated.length ? html`<p class="muted">Ваши личные отметки обновлены:</p>
        <div class="card tight list" style="text-align:left">${res.updated.map((u) => html`<div class="item"><span class="grow title">${u.name}</span><span class="small">${MARK_TEXT[u.status]}</span></div>`)}</div>`
        : html`<p class="muted">Спасибо! Чем больше записей, тем точнее анализ.</p>`}
      <button class="btn block" style="margin-top:14px" id="ok">Готово</button></div>`, (el, close) => {
      el.querySelector("#ok").addEventListener("click", () => { close(); back(); });
    });
  } catch (error) {
    showError(error);
  }
}
