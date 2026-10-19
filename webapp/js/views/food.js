// Карточка продукта: светофор порции, КБЖУ, FODMAP-группы, личная отметка, запись в дневник.
import { api, q } from "../api.js";
import { go, render as refresh, store } from "../state.js";
import { LEVEL, busy, chip, haptic, html, isoDay, mount, num, showError, tg, toast } from "../ui.js";

const MARKS = {
  ok: { emoji: "💚", text: "Подходит мне" }, caution: { emoji: "💛", text: "Осторожно" },
  avoid: { emoji: "❤️‍🩹", text: "Не подходит" },
};

// Повторяет серверную логику порции, чтобы ползунок реагировал мгновенно.
export function levelFor(card, grams) {
  const v = card.verdict;
  if (v.allergy) return "red";
  const t = card.tolerance;
  if (t && t.status === "avoid") return "red";
  if (t && t.status === "caution") return "yellow";
  if (t && t.status === "ok") return t.tested_g && grams > t.tested_g ? "yellow" : "green";
  const lactoseFree = (card.tags || []).includes("lactose_free");
  const relevant = card.groups.filter((g) => g.relevant && !(lactoseFree && g.code === "lac"));
  const base = v.level === "grey" ? "grey" : card.unknown ? "yellow" : "green";
  if (!relevant.length) return base;
  if (card.estimated) return card.low_g === null ? "red" : "yellow";
  if (card.low_g === null) return "red";
  const high = card.high_g || card.low_g * 2;
  const level = grams <= card.low_g ? "green" : grams < high ? "yellow" : "red";
  return base === "grey" && level === "green" ? "grey" : level;
}

function scale(card, max) {
  if (card.low_g === null || !card.groups.some((g) => g.relevant)) return "";
  const high = card.high_g || card.low_g * 2;
  const pct = (x) => Math.min(100, (x / max) * 100);
  return html`<div class="portion-scale">
    <i style="left:0;width:${pct(card.low_g)}%;background:var(--green)"></i>
    <i style="left:${pct(card.low_g)}%;width:${pct(high) - pct(card.low_g)}%;background:var(--yellow)"></i>
    <i style="left:${pct(high)}%;right:0;background:var(--red)"></i></div>
    <div class="row between small muted" style="margin-top:4px"><span>0</span><span>${num(card.low_g)} г</span><span>${num(high)} г</span><span>${num(max)} г</span></div>`;
}

function nutrients(card, grams) {
  const k = grams / 100, p = card.per100;
  return html`<div class="nutri">
    <div><b>${num(p.kcal * k)}</b><small>ккал</small></div><div><b>${num(p.protein * k, 1)}</b><small>белки</small></div>
    <div><b>${num(p.fat * k, 1)}</b><small>жиры</small></div><div><b>${num(p.carbs * k, 1)}</b><small>углеводы</small></div></div>`;
}

const LIVE_TEXT = {
  green: "В такой порции — безопасно",
  yellow: "Больше безопасной порции: возможны симптомы",
  red: "Слишком много: высокий риск симптомов",
  grey: "Не подходит вашему рациону",
};

function liveText(grams, level) {
  return `${num(grams)} г — ${LIVE_TEXT[level].toLowerCase()}`;
}

function verdictBox(card, level, grams) {
  const v = card.verdict;
  return html`<div class="verdict ${level}" id="verdict">
    <h2>${LEVEL[level].emoji} ${LEVEL[level].title}</h2>
    <div id="live"><b>${liveText(grams, level)}</b></div>
    <ul style="margin-top:6px">${v.reasons.map((r) => html`<li>${r}</li>`)}</ul>
    ${v.safe_g ? html`<div style="margin-top:8px"><b>Безопасная порция: до ${num(v.safe_g)} г</b></div>` : ""}
    ${v.safe_g === 0 ? html`<div style="margin-top:8px"><b>Безопасной порции нет — лучше заменить</b></div>` : ""}
  </div>`;
}

function details(card) {
  const groups = card.groups.length
    ? html`<div class="groups">${card.groups.map((g) => html`<span class="group ${g.relevant ? "rel" : ""}" title="${g.desc}">${g.name}</span>`)}</div>`
    : html`<span class="chip green">FODMAP не обнаружены</span>`;
  const allergens = card.allergens.length
    ? html`<div class="groups">${card.allergens.map((a) => html`<span class="group ${a.hit ? "rel" : ""}">${a.name}</span>`)}</div>`
    : html`<span class="muted small">Основных аллергенов нет</span>`;
  return html`<div class="card"><b>Что внутри</b>
    <div class="small muted" style="margin:8px 0 6px">FODMAP-группы ${card.estimated ? "(оценка по составу)" : ""}</div>${groups}
    <div class="small muted" style="margin:12px 0 6px">Аллергены</div>${allergens}
    ${card.note ? html`<p class="small muted" style="margin:12px 0 0">ℹ️ ${card.note}</p>` : ""}
    ${card.ingredients ? html`<details style="margin-top:10px"><summary class="small">Состав с упаковки</summary><p class="small muted">${card.ingredients}</p></details>` : ""}
  </div>`;
}

function personal(card) {
  const t = card.tolerance;
  const feelings = store.meta.feelings;
  return html`<div class="card"><div class="row between"><b>Мой опыт</b>
      ${t ? html`<span class="chip plain">${MARKS[t.status].emoji} ${MARKS[t.status].text}${t.manual ? " · вручную" : ""}</span>` : html`<span class="small muted">ещё не проверяли</span>`}</div>
    ${t ? html`<div class="small muted" style="margin-top:4px">${t.ok_count} раз без симптомов · ${t.mild_count} с лёгкими · ${t.bad_count} с сильными${t.tested_g ? ` · подходило до ${num(t.tested_g)} г` : ""}</div>` : ""}
    <div class="small muted" style="margin-top:12px">Как вы перенесли этот продукт?</div>
    <div class="feel-row">${Object.entries(feelings).map(([code, f]) => html`<button class="feel" data-feel="${code}"><span>${f.emoji}</span>${f.name}</button>`)}</div>
    <div class="small muted" style="margin-top:12px">Или отметьте сами</div>
    <div class="choices" style="margin-top:6px">${Object.entries(MARKS).map(([code, m]) => html`<button class="choice ${t?.status === code && t?.manual ? "on" : ""}" data-mark="${code}">${m.emoji} ${m.text}</button>`)}
      ${t ? html`<button class="choice" data-mark="reset">↺ Сбросить</button>` : ""}</div>
    ${card.history.length ? html`<div class="small muted" style="margin-top:12px">История: ${card.history.slice(0, 5).map((h) => `${h.day.slice(5).split("-").reverse().join(".")} ${feelings[h.feeling]?.emoji || ""}`).join(" · ")}</div>` : ""}
  </div>`;
}

function swaps(card) {
  if (!card.swaps.length) return "";
  return html`<div class="section-title"><h2>Чем заменить</h2></div><div class="card tight list">${card.swaps.map((s) =>
    html`<button class="item" data-food="${s.ref}"><span class="emoji">${s.emoji}</span><span class="grow title">${s.name}</span>${chip(s.verdict.level)}</button>`)}</div>`;
}

export async function render(root, params) {
  mount(root, html`<div class="skeleton" style="height:240px"></div>`);
  let card;
  try {
    card = await api.get(`/api/foods/item${q({ ref: params.ref })}`);
  } catch (error) {
    mount(root, html`<div class="empty"><div class="big">😕</div>${error.message}</div>`);
    return;
  }
  const meal = params.meal || "snack";
  const max = Math.max(300, Math.round(((card.high_g || card.low_g || 100) * 2.5) / 10) * 10);
  let grams = Number(params.grams) || card.portion.grams;
  mount(root, html`
    <section class="card food-hero">
      ${card.image ? html`<img class="photo" src="${card.image}" alt="" width="120" height="120">` : html`<div class="big-emoji">${card.emoji}</div>`}
      <h1>${card.name}</h1><div class="muted small">${card.brand ? card.brand + " · " : ""}${card.category_emoji} ${card.category_name}</div>
      ${verdictBox(card, grams === card.verdict.grams ? card.verdict.level : levelFor(card, grams), grams)}
    </section>
    <div class="card" style="margin-top:12px">
      <div class="row between"><b>Порция</b><span class="grams" id="grams">${num(grams)} г</span></div>
      ${card.portion.label ? html`<div class="small muted">Обычно: ${card.portion.label} ≈ ${num(card.portion.grams)} г</div>` : ""}
      <input class="slider" id="slider" type="range" min="1" max="${max}" step="1" value="${grams}" aria-label="Граммы">
      ${scale(card, max)}
      <div style="margin-top:12px" id="nutri">${nutrients(card, grams)}</div>
      <div class="pills" style="margin-top:14px">${Object.entries(store.meta.meals).map(([code, m]) =>
        html`<button class="pill ${code === meal ? "on" : ""}" data-meal="${code}">${m.emoji} ${m.name}</button>`)}</div>
      <button class="btn block" style="margin-top:10px" id="add">＋ Записать в дневник</button>
    </div>
    ${personal(card)}
    ${details(card)}
    ${swaps(card)}
    <div class="center" style="margin:18px 0"><button class="btn ghost sm" id="web">🌐 Рецепты с этим продуктом в интернете</button></div>`);

  const state = { meal };
  const slider = root.querySelector("#slider");
  slider.addEventListener("input", () => {
    grams = Number(slider.value);
    root.querySelector("#grams").textContent = `${num(grams)} г`;
    mount(root.querySelector("#nutri"), nutrients(card, grams));
    const level = levelFor(card, grams);
    const box = root.querySelector("#verdict");
    box.querySelector("#live b").textContent = liveText(grams, level);
    if (!box.classList.contains(level)) {
      box.className = `verdict ${level}`;
      box.querySelector("h2").textContent = `${LEVEL[level].emoji} ${LEVEL[level].title}`;
      haptic("select");
    }
  });
  root.querySelector("#web").addEventListener("click", () => {
    const url = `https://yandex.ru/search/?text=${encodeURIComponent(`low FODMAP рецепт ${card.name}`)}`;
    tg?.openLink ? tg.openLink(url) : window.open(url, "_blank");
  });
  root.addEventListener("click", async (event) => {
    const el = event.target.closest("[data-meal],[data-feel],[data-mark],[data-food],#add");
    if (!el) return;
    await busy(el, async () => { try {
      if (el.dataset.meal) {
        state.meal = el.dataset.meal;
        root.querySelectorAll("[data-meal]").forEach((p) => p.classList.toggle("on", p === el));
      } else if (el.id === "add") {
        await api.post("/api/diary", { ref: card.ref, day: params.day || isoDay(), meal: state.meal, grams });
        toast(`Записано: ${card.name}, ${num(grams)} г`, "success");
      } else if (el.dataset.feel) {
        const feeling = el.dataset.feel;
        if (feeling === "mild" || feeling === "bad") {
          return go(`/react?ref=${encodeURIComponent(card.ref)}&feeling=${feeling}&grams=${grams}`);
        }
        await reactTo(card, feeling, grams, params);
        return refresh();
      } else if (el.dataset.mark) {
        if (el.dataset.mark === "reset") await api.del(`/api/foods/tolerance${q({ ref: card.ref })}`);
        else await api.put(`/api/foods/tolerance${q({ ref: card.ref })}`, { status: el.dataset.mark, name: card.name, tested_g: el.dataset.mark === "ok" ? grams : null });
        toast("Отметка сохранена", "success");
        return refresh();
      } else if (el.dataset.food) {
        go(`/food/${encodeURIComponent(el.dataset.food)}`);
      }
    } catch (error) {
      showError(error);
    } });
  });
}

async function reactTo(card, feeling, grams, params) {
  const res = await api.post("/api/reactions", { day: params.day || isoDay(), ref: card.ref, feeling, grams });
  const record = res.updated[0];
  toast(record ? `${MARKS[record.status].emoji} ${card.name}: ${MARKS[record.status].text.toLowerCase()}` : "Записано", "success");
}
