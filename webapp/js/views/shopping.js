// Список покупок: из рецептов и вручную.
import { api } from "../api.js";
import { haptic, html, mount, showError } from "../ui.js";

function list(items) {
  if (!items.length) return html`<div class="empty"><div class="big">🛒</div>Список пуст. Добавьте вручную или из рецепта.</div>`;
  return html`<div class="card tight list">${items.map((i) => html`<label class="item">
    <input type="checkbox" data-id="${i.id}" ${i.done ? "checked" : ""} style="width:22px;height:22px;accent-color:var(--accent)">
    <span class="grow" style="${i.done ? "text-decoration:line-through;opacity:.5" : ""}">${i.name}</span>
    <button class="muted" data-del="${i.id}" aria-label="Удалить">✕</button></label>`)}</div>
    ${items.some((i) => i.done) ? html`<button class="btn ghost block sm" style="margin-top:12px" id="clear">Убрать купленное</button>` : ""}`;
}

export async function render(root) {
  mount(root, html`<header class="topbar"><div><h1>Покупки</h1><div class="sub">Только безопасное 🛒</div></div></header>
    <form class="search" id="form"><input id="name" placeholder="Добавить: безлактозный йогурт" maxlength="80"><button class="btn sm">＋</button></form>
    <div id="list" style="margin-top:12px"></div>`);
  const box = root.querySelector("#list");
  const show = (items) => mount(box, list(items));
  const run = async (promise) => {
    try { show(await promise); } catch (error) { showError(error); }
  };
  run(api.get("/api/shopping"));
  root.querySelector("#form").addEventListener("submit", (event) => {
    event.preventDefault();
    const input = root.querySelector("#name");
    if (!input.value.trim()) return;
    run(api.post("/api/shopping", { names: [input.value.trim()] }));
    input.value = "";
    haptic("light");
  });
  box.addEventListener("change", (event) => {
    const id = event.target.dataset.id;
    if (id) run(api.patch(`/api/shopping/${id}`, { done: event.target.checked }));
  });
  box.addEventListener("click", (event) => {
    const del = event.target.closest("[data-del]");
    if (del) { event.preventDefault(); run(api.del(`/api/shopping/${del.dataset.del}`)); }
    if (event.target.id === "clear") run(api.del("/api/shopping"));
  });
}
