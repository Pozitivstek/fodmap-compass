// Запуск мини-приложения: Telegram, профиль, маршруты.
import { applyTheme, back, go, loadMe, parse, render, route, savedTheme, store } from "./state.js";
import { api } from "./api.js";
import { esc, tg } from "./ui.js";

route("/home", () => import("./views/home.js"));
route("/foods", () => import("./views/foods.js"));
route("/food/:ref", () => import("./views/food.js"));
route("/scan", () => import("./views/scan.js"));
route("/diary", () => import("./views/diary.js"));
route("/add", () => import("./views/add.js"));
route("/react", () => import("./views/react.js"));
route("/recipes", () => import("./views/recipes.js"));
route("/recipe/:id", () => import("./views/recipe.js"));
route("/insights", () => import("./views/insights.js"));
route("/profile", () => import("./views/profile.js"));
route("/onboarding", () => import("./views/onboarding.js"));
route("/shopping", () => import("./views/shopping.js"));

function setupTelegram() {
  if (!tg) return;
  tg.ready();
  tg.expand();
  try {
    if (tg.isVersionAtLeast?.("7.7")) tg.disableVerticalSwipes();
  } catch { /* старый клиент */ }
  tg.BackButton?.onClick(back);
  tg.onEvent?.("themeChanged", () => applyTheme(store.me?.settings?.theme));
}

function initialRoute() {
  // Кнопки бота открывают приложение с ?route=/food/cat:apple (hash занят параметрами Telegram).
  const fromQuery = new URLSearchParams(location.search).get("route");
  if (fromQuery) return fromQuery;
  const { path } = parse();
  return path.startsWith("/") && !location.hash.includes("tgWebApp") ? location.hash.slice(1) : "/home";
}

async function boot() {
  setupTelegram();
  applyTheme(savedTheme());
  document.getElementById("tabbar").addEventListener("click", (event) => {
    const tab = event.target.closest("[data-tab]");
    if (tab) go(tab.dataset.tab);
  });
  window.addEventListener("popstate", render);
  try {
    const [meta] = await Promise.all([api.get("/api/meta"), loadMe()]);
    store.meta = meta;
  } catch (error) {
    document.getElementById("app").innerHTML = `<div class="splash"><div><div class="logo">🧭</div>
      <h2>Не получилось войти</h2><p class="muted">${esc(error.message)}</p>
      <p class="muted small">Откройте приложение из бота кнопкой «ФудКомпас».</p></div></div>`;
    return;
  }
  const start = store.me.onboarded ? initialRoute() : "/onboarding";
  history.replaceState(null, "", `${location.pathname}#${start}`);
  render();
}

boot();
