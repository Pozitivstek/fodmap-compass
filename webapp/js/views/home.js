// Главная: огонёк серии, сегодняшний день, вода, подсказки что съесть.
import { api } from "../api.js";
import { go, saveSettings, store } from "../state.js";
import { animateBars, busy, chip, haptic, html, macroBar, mount, num, plural, ring, showError, toast } from "../ui.js";

const GLASS_ML = 250;
const MAX_WATER_STEP = 5000;
const MEAL_WORD = { breakfast: "завтрак", lunch: "обед", dinner: "ужин", snack: "перекус" };

function flame(streak) {
  const n = streak.current;
  const label = n ? `${plural(n, "день", "дня", "дней")} подряд` : "Начните серию сегодня";
  const hint = streak.at_risk ? "Запишите еду сегодня, чтобы огонёк не погас"
    : streak.today_logged ? "Сегодня уже записано — так держать!" : "Первая запись зажжёт огонёк";
  return html`<div class="streak">
    <div class="flame ${n ? "" : "off"}"><span class="f1"></span><span class="f2"></span><span class="f3"></span></div>
    <div><div class="num">${n}</div><div class="label"><b>${label}</b></div>
      <div class="label small">${hint} · рекорд ${streak.best}</div></div>
  </div>`;
}

function week(days) {
  return html`<div class="week">${days.map((d) => html`<div class="${d.logged ? "on" : ""}">${d.weekday}</div>`)}</div>`;
}

function today(summary) {
  const t = summary.totals, g = summary.targets;
  const stack = summary.stack;
  return html`<div class="card">
    <div class="row">${ring(t.kcal, g.kcal)}
      <div class="grow">${macroBar("Белки", t.protein, g.protein, "p")}${macroBar("Жиры", t.fat, g.fat, "f")}
        ${macroBar("Углеводы", t.carbs, g.carbs, "c")}</div></div>
    <div class="row between" style="margin-top:12px"><span class="small muted">FODMAP за день</span>${chip(stack.level, stack.short)}</div>
  </div>`;
}

function water(state) {
  const glasses = Math.max(6, Math.ceil(state.goal / GLASS_ML));
  const full = Math.floor(state.ml / GLASS_ML);
  return html`<div class="card tight"><div class="row between"><b>💧 Вода</b>
      <span class="small muted">${num(state.ml)} из ${num(state.goal)} мл</span></div>
    <div class="water">${Array.from({ length: glasses }, (_, i) =>
      html`<button class="glass ${i < full ? "full" : ""}" data-glass="${i}" aria-label="Стакан ${i + 1}"></button>`)}</div>
  </div>`;
}

function pending(meals, summary) {
  if (!meals.length) return "";
  const meal = meals[meals.length - 1];
  const spec = summary.meals[meal];
  return html`<div class="card"><b>${spec.emoji} Как самочувствие после «${spec.name.toLowerCase()}»?</b>
    <div class="small muted">Ответ обновит ваши личные отметки у продуктов</div>
    <div class="feel-row">${Object.entries(store.meta.feelings).map(([code, f]) =>
      html`<button class="feel" data-feel="${code}" data-meal="${meal}"><span>${f.emoji}</span>${f.name}</button>`)}</div>
  </div>`;
}

function ideas(s) {
  if (!s.recipes.length && !s.snacks.length) return "";
  return html`<div class="section-title"><h2>Что съесть на ${MEAL_WORD[s.meal]}</h2><a href="#/recipes?meal=${s.meal}">Все</a></div>
    <div class="pills" style="gap:12px">${s.recipes.map((r) => html`<button class="card tight" data-recipe="${r.id}" style="flex:none;width:230px;text-align:left">
      <div style="font-size:34px">${r.emoji}</div><b class="ellipsis" style="display:block">${r.title}</b>
      <div class="row between small" style="margin-top:6px"><span class="muted">${r.minutes} мин · ${num(r.per_serving.kcal)} ккал</span>${chip(r.level)}</div>
    </button>`)}</div>
    ${s.snacks.length ? html`<div class="small muted" style="margin:10px 4px 6px">Безопасные перекусы</div>
      <div class="pills">${s.snacks.map((f) => html`<button class="pill" data-food="${f.ref}">${f.emoji} ${f.name}</button>`)}</div>` : ""}`;
}

function badges(fresh) {
  if (!fresh.length) return "";
  return html`<div class="card" style="text-align:center"><div style="font-size:40px">${fresh.map((a) => a.emoji)}</div>
    <b>Новое достижение: ${fresh.map((a) => a.title).join(", ")}</b><div class="small muted">${fresh[0].desc}</div>
    <button class="btn sm ghost" style="margin-top:10px" data-ack="${fresh.map((a) => a.code).join(",")}">Ура!</button></div>`;
}

const actions = html`<div class="tiles" style="margin-top:12px">
  <button class="tile" data-go="/scan"><span class="big">📷</span><b>Сканировать</b><span class="small muted">штрихкод товара</span></button>
  <button class="tile" data-go="/react"><span class="big">🩺</span><b>Самочувствие</b><span class="small muted">как вы сейчас</span></button>
  <button class="tile" data-go="/foods"><span class="big">🔍</span><b>Можно ли?</b><span class="small muted">проверить продукт</span></button>
  <button class="tile" data-go="/insights"><span class="big">📄</span><b>Отчёт врачу</b><span class="small muted">PDF в чат</span></button>
</div>`;

export async function render(root) {
  mount(root, html`<div class="skeleton" style="height:170px"></div><div class="skeleton" style="height:190px;margin-top:12px"></div>`);
  let data;
  try {
    data = await api.get("/api/home");
  } catch (error) {
    showError(error);
    return;
  }
  const name = data.user.first_name || "друг";
  const date = new Date().toLocaleDateString("ru-RU", { weekday: "long", day: "numeric", month: "long" });
  mount(root, html`
    <header class="topbar"><div><h1>Привет, ${name} 👋</h1><div class="sub">${date}</div></div>
      <div class="row" style="gap:8px"><button class="icon-btn" data-go="/shopping" aria-label="Покупки">🛒</button>
      <button class="icon-btn" data-go="/profile" aria-label="Профиль">⚙️</button></div></header>
    <section class="card hero">${flame(data.streak)}${week(data.week)}</section>
    ${badges(data.new_achievements)}
    ${pending(data.pending_reactions, data.summary)}
    <div class="section-title"><h2>Сегодня</h2><a href="#/diary">Дневник</a></div>
    ${today(data.summary)}
    <div style="margin-top:12px">${water(data.summary.water)}</div>
    ${ideas(data.suggestions)}
    ${actions}
    <div class="card" style="margin-top:12px"><b>💡 Совет дня</b><div class="muted" style="margin-top:4px">${data.tip}</div></div>
    <button class="fab" data-go="/add" aria-label="Записать еду">＋</button>`);
  animateBars(root);
  root.homeData = data;
  if (!root.dataset.bound) {
    root.dataset.bound = "1";
    bind(root);
  }
}

function bind(root) {
  root.addEventListener("click", async (event) => {
    const data = root.homeData;
    const el = event.target.closest("[data-go],[data-food],[data-recipe],[data-glass],[data-feel],[data-ack]");
    if (!el) return;
    haptic("light");
    if (el.dataset.go) return go(el.dataset.go);
    if (el.dataset.food) return go(`/food/${encodeURIComponent(el.dataset.food)}`);
    if (el.dataset.recipe) return go(`/recipe/${el.dataset.recipe}`);
    await busy(el, async () => { try {
      if (el.dataset.glass !== undefined) {
        const target = (Number(el.dataset.glass) + 1) * GLASS_ML;
        const state = data.summary.water;
        const delta = Math.max(-MAX_WATER_STEP, Math.min(MAX_WATER_STEP, state.ml >= target ? -GLASS_ML : target - state.ml));
        const res = await api.post("/api/water", { delta_ml: delta });
        state.ml = res.ml;
        root.querySelectorAll(".glass").forEach((g, i) => g.classList.toggle("full", i < Math.floor(res.ml / GLASS_ML)));
        root.querySelector(".water").previousElementSibling.lastElementChild.textContent = `${num(res.ml)} из ${num(res.goal)} мл`;
        if (res.ml >= res.goal && delta > 0) toast("💧 Норма воды выполнена!", "success");
      } else if (el.dataset.feel) {
        const feeling = el.dataset.feel;
        if (feeling === "mild" || feeling === "bad") return go(`/react?meal=${el.dataset.meal}&feeling=${feeling}&day=${data.day}`);
        await api.post("/api/reactions", { day: data.day, meal: el.dataset.meal, feeling });
        toast("Записано! Отметки продуктов обновлены 💚", "success");
        render(root);
      } else if (el.dataset.ack) {
        const seen = new Set([...(store.me.settings.seen_achievements || []), ...el.dataset.ack.split(",")]);
        await saveSettings({ seen_achievements: [...seen] });
        el.closest(".card").remove();
      }
    } catch (error) {
      showError(error);
    } });
  });
}
