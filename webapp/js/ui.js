// Небольшой набор UI-помощников: безопасные шаблоны, шторки, тосты, графические элементы.
export const tg = window.Telegram?.WebApp;

const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
export const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ESCAPES[ch]);

// Шаблон: все подстановки экранируются, кроме результатов html`` и raw().
export const raw = (value) => ({ __html: String(value) });
const piece = (value) => {
  if (value === null || value === undefined || value === false) return "";
  if (Array.isArray(value)) return value.map(piece).join("");
  if (typeof value === "object" && "__html" in value) return value.__html;
  return esc(value);
};
export const html = (strings, ...values) =>
  raw(strings.reduce((out, chunk, i) => out + chunk + (i < values.length ? piece(values[i]) : ""), ""));
export const mount = (el, template) => {
  el.innerHTML = template.__html;
  return el;
};

export function haptic(kind = "light") {
  try {
    if (kind === "success" || kind === "error" || kind === "warning") tg?.HapticFeedback?.notificationOccurred(kind);
    else if (kind === "select") tg?.HapticFeedback?.selectionChanged();
    else tg?.HapticFeedback?.impactOccurred(kind);
  } catch { /* старые клиенты Telegram */ }
}

export function toast(message, kind = "") {
  const node = document.createElement("div");
  node.className = "toast";
  node.textContent = message;
  document.body.appendChild(node);
  if (kind) haptic(kind);
  setTimeout(() => node.remove(), 2700);
}

// Блокирует кнопку на время запроса: двойное нажатие не должно дважды записать еду или реакцию.
export async function busy(el, action) {
  if (!el || el.dataset.busy) return undefined;
  el.dataset.busy = "1";
  el.classList.add("is-busy");
  try {
    return await action();
  } finally {
    delete el.dataset.busy;
    el.classList.remove("is-busy");
  }
}

export function showError(error) {
  toast(error?.message || "Что-то пошло не так", "error");
}

export function sheet(template, onMount) {
  const layer = document.getElementById("layer");
  const wrap = document.createElement("div");
  wrap.className = "sheet-wrap";
  wrap.innerHTML = `<div class="shade"></div><div class="sheet" role="dialog" aria-modal="true"><div class="grab"></div>${template.__html}</div>`;
  layer.appendChild(wrap);
  const close = () => wrap.remove();
  wrap.querySelector(".shade").addEventListener("click", close);
  onMount?.(wrap.querySelector(".sheet"), close);
  return close;
}

export async function confirmAction(text) {
  if (tg?.showConfirm && tg.isVersionAtLeast?.("6.2")) {
    return new Promise((resolve) => tg.showConfirm(text, resolve));
  }
  return window.confirm(text);
}

export const num = (value, digits = 0) => {
  const n = Number(value || 0);
  return n.toLocaleString("ru-RU", { maximumFractionDigits: digits, minimumFractionDigits: 0 });
};

export function plural(n, one, few, many) {
  const mod10 = n % 10, mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}

export const LEVEL = {
  green: { title: "Можно", emoji: "🟢" },
  yellow: { title: "Осторожно", emoji: "🟡" },
  red: { title: "Нельзя", emoji: "🔴" },
  grey: { title: "Не для вас", emoji: "⚪" },
};

export const chip = (level, text) => html`<span class="chip ${level}">${text || LEVEL[level]?.title || ""}</span>`;

export function ring(value, target, label = "ккал") {
  const r = 48, c = 2 * Math.PI * r;
  const share = target ? Math.min(value / target, 1) : 0;
  return html`<div class="ring">
    <svg width="112" height="112" viewBox="0 0 112 112">
      <circle class="track" cx="56" cy="56" r="${r}" fill="none" stroke-width="10"></circle>
      <circle class="value" cx="56" cy="56" r="${r}" fill="none" stroke-width="10"
        stroke-dasharray="${c}" stroke-dashoffset="${c}" data-offset="${c * (1 - share)}"></circle>
    </svg>
    <div class="inner"><div><b>${num(value)}</b><small>из ${num(target)} ${label}</small></div></div>
  </div>`;
}

export function macroBar(label, value, target, cls) {
  const share = target ? Math.min(100, (value / target) * 100) : 0;
  return html`<div class="macro"><div class="top"><span class="muted">${label}</span>
    <span><b>${num(value)}</b> / ${num(target)} г</span></div>
    <div class="bar ${cls}"><i data-width="${share}%"></i></div></div>`;
}

// Плавно «наливает» кольца и шкалы после вставки в DOM.
export function animateBars(root) {
  requestAnimationFrame(() => requestAnimationFrame(() => {
    root.querySelectorAll("[data-offset]").forEach((el) => { el.style.strokeDashoffset = el.dataset.offset; });
    root.querySelectorAll("[data-width]").forEach((el) => { el.style.width = el.dataset.width; });
  }));
}

export function emojiBox(item) {
  if (item.image) return html`<span class="emoji"><img src="${item.image}" alt="" loading="lazy" width="44" height="44"></span>`;
  return html`<span class="emoji">${item.emoji || "🍽️"}</span>`;
}

export function foodRow(item, extra = "") {
  const v = item.verdict || {};
  const personal = v.personal ? html`<span class="personal">${v.personal === "ok" ? "💚 подходит вам" : v.personal === "avoid" ? "❤️‍🩹 вам не подошло" : "💛 осторожно"}</span>` : "";
  const safe = v.safe_g ? `до ${num(v.safe_g)} г` : v.safe_g === 0 ? "избегать" : "";
  return html`<button class="item" data-food="${item.ref}">
    ${emojiBox(item)}
    <span class="grow"><span class="title ellipsis" style="display:block">${item.name}</span>
      <span class="meta ellipsis" style="display:block">${item.brand ? item.brand + " · " : ""}${safe || `${num(item.kcal)} ккал / 100 г`} ${extra}</span>
      ${personal}</span>
    ${chip(v.level || "grey", v.title)}
  </button>`;
}

export function dayLabel(iso) {
  const today = new Date();
  const date = new Date(`${iso}T12:00:00`);
  const diff = Math.round((new Date(today.toDateString()) - new Date(date.toDateString())) / 864e5);
  if (diff === 0) return "Сегодня";
  if (diff === 1) return "Вчера";
  return date.toLocaleDateString("ru-RU", { day: "numeric", month: "long", weekday: "short" });
}

export function isoDay(date = new Date()) {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

export function shiftDay(iso, delta) {
  const date = new Date(`${iso}T12:00:00`);
  date.setDate(date.getDate() + delta);
  return isoDay(date);
}
