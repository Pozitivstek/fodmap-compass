// Общее состояние (профиль, справочники), темы и hash-роутер.
import { api } from "./api.js";
import { tg } from "./ui.js";

export const store = { meta: null, me: null };

const TAB_ROOTS = ["/home", "/foods", "/diary", "/recipes", "/insights"];
const THEME_BG = {
  light: "#f6f8fc", dark: "#0f1420", mint: "#effaf5", sunset: "#fff5ef", ocean: "#072033",
  lavender: "#f6f3ff", forest: "#0f1d16", graphite: "#141414",
};
export const THEME_NAMES = {
  auto: "Как в Telegram", light: "Светлая", dark: "Тёмная", mint: "Мята", sunset: "Закат",
  ocean: "Океан", lavender: "Лаванда", forest: "Лес", graphite: "Графит",
};

export const THEME_SWATCHES = {
  auto: ["#f6f8fc", "#0f1420", "#4f7cff"], light: ["#f6f8fc", "#4f7cff", "#2fc4b2"], dark: ["#0f1420", "#7aa2ff", "#3ddcc1"],
  mint: ["#effaf5", "#10b981", "#5eead4"], sunset: ["#fff5ef", "#ff6b4a", "#ffb547"], ocean: ["#072033", "#2ec5ff", "#5b8cff"],
  lavender: ["#f6f3ff", "#8b5cf6", "#ec4899"], forest: ["#0f1d16", "#4ade80", "#bef264"], graphite: ["#141414", "#f2f2f2", "#737373"],
};

export function resolveTheme(theme) {
  if (theme && theme !== "auto") return theme;
  const dark = tg?.colorScheme === "dark" || window.matchMedia?.("(prefers-color-scheme: dark)").matches;
  return dark ? "dark" : "light";
}

const THEME_KEY = "fodmap-theme";

export function savedTheme() {
  try {
    return localStorage.getItem(THEME_KEY) || "auto";
  } catch {
    return "auto";
  }
}

export function applyTheme(theme) {
  try {
    localStorage.setItem(THEME_KEY, theme || "auto");
  } catch { /* приватный режим — просто не запоминаем */ }
  const resolved = resolveTheme(theme);
  document.documentElement.dataset.theme = resolved;
  try {
    tg?.setHeaderColor?.(THEME_BG[resolved]);
    tg?.setBackgroundColor?.(THEME_BG[resolved]);
    tg?.setBottomBarColor?.(THEME_BG[resolved]);
  } catch { /* старые клиенты */ }
}

export async function loadMe() {
  store.me = await api.get("/api/me");
  applyTheme(store.me.settings.theme);
  return store.me;
}

export async function saveSettings(patch) {
  store.me = await api.put("/api/me", patch);
  applyTheme(store.me.settings.theme);
  return store.me;
}

// ---------- роутер ----------
const routes = [];
const leaveHandlers = [];
let current = null;

// Вызывается при уходе с текущего экрана (например, чтобы выключить камеру).
export function onLeave(fn) {
  leaveHandlers.push(fn);
}

export function route(pattern, loader) {
  const keys = [];
  const regex = new RegExp(`^${pattern.replace(/:(\w+)/g, (_, key) => { keys.push(key); return "([^/?]+)"; })}$`);
  routes.push({ regex, keys, loader });
}

export function parse(hash = location.hash) {
  const [path, query = ""] = hash.replace(/^#/, "").split("?");
  return { path: path || "/home", query: Object.fromEntries(new URLSearchParams(query)) };
}

export function go(path, { replace = false } = {}) {
  const target = `#${path}`;
  if (replace) history.replaceState(null, "", target);
  else if (location.hash !== target) history.pushState(null, "", target);
  render();
}

export function back() {
  if (history.length > 1) history.back();
  else go("/home", { replace: true });
}

export async function render() {
  const { path, query } = parse();
  const match = routes.map((r) => ({ r, m: path.match(r.regex) })).find((x) => x.m);
  const view = document.getElementById("app");
  const tabbar = document.getElementById("tabbar");
  if (!match) return go("/home", { replace: true });
  const params = Object.fromEntries(match.r.keys.map((key, i) => [key, decodeURIComponent(match.m[i + 1])]));
  const token = Symbol(path);
  current = token;
  leaveHandlers.splice(0).forEach((fn) => { try { fn(); } catch { /* уже остановлено */ } });
  const isRoot = TAB_ROOTS.includes(path);
  tabbar.classList.toggle("hidden", path === "/onboarding");
  tabbar.querySelectorAll(".tab").forEach((tab) => tab.classList.toggle("on", path.startsWith(tab.dataset.tab)));
  if (tg?.BackButton) isRoot || path === "/onboarding" ? tg.BackButton.hide() : tg.BackButton.show();
  const module = await match.r.loader();
  if (current !== token) return;
  view.innerHTML = "";
  const page = document.createElement("div");
  page.className = "view";
  view.appendChild(page);
  window.scrollTo(0, 0);
  await module.render(page, { ...params, ...query });
}
