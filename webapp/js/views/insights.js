// Аналитика: самочувствие по дням, подозреваемые продукты, FODMAP-группы, личные отметки, отчёт.
import { api, q } from "../api.js";
import { go } from "../state.js";
import { html, mount, num, plural, raw, showError, toast } from "../ui.js";

const SCORE_COLOR = ["var(--green)", "var(--green)", "var(--yellow)", "var(--yellow)", "var(--red)", "var(--red)"];
const MARKS = { ok: "💚 Подходит", caution: "💛 Осторожно", avoid: "❤️‍🩹 Не подходит" };

function dayChart(days) {
  const w = 340, h = 150, pad = 18;
  const step = (w - pad) / days.length;
  const maxKcal = Math.max(1, ...days.map((d) => d.kcal));
  const bars = days.map((d, i) => {
    const x = pad + i * step + step * 0.18;
    const bw = step * 0.64;
    if (d.score === null) {
      return `<rect x="${x}" y="${h - 26}" width="${bw}" height="4" rx="2" fill="var(--surface-2)"></rect>`;
    }
    const bh = 10 + (d.score / 5) * (h - 50);
    return `<rect x="${x}" y="${h - 22 - bh}" width="${bw}" height="${bh}" rx="5" fill="${SCORE_COLOR[d.score]}" opacity=".85"></rect>`;
  }).join("");
  const line = days.map((d, i) => `${pad + i * step + step / 2},${h - 22 - (d.kcal / maxKcal) * (h - 50)}`).join(" ");
  const labels = days.map((d, i) => (i % Math.ceil(days.length / 7) === 0
    ? `<text x="${pad + i * step + step / 2}" y="${h - 6}" text-anchor="middle">${d.day.slice(8)}.${d.day.slice(5, 7)}</text>` : "")).join("");
  return `<svg class="chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="Самочувствие и калории по дням">${bars}
    <polyline points="${line}" fill="none" stroke="var(--accent)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" opacity=".8"></polyline>${labels}</svg>`;
}

function rateBar(rate, cls = "load") {
  return html`<div class="bar ${cls}" style="margin-top:4px"><i style="width:${Math.round(rate * 100)}%"></i></div>`;
}

export async function render(root, params) {
  const days = Number(params.days || 14);
  mount(root, html`<div class="skeleton" style="height:320px"></div>`);
  let d;
  try {
    d = await api.get(`/api/insights${q({ days })}`);
  } catch (error) {
    showError(error);
    return;
  }
  const good = d.good_share === null ? "—" : `${Math.round(d.good_share * 100)}%`;
  const byStatus = (s) => d.tolerances.filter((t) => t.status === s);
  mount(root, html`
    <header class="topbar"><div><h1>Анализ</h1><div class="sub">Что влияет на ваше самочувствие</div></div></header>
    <div class="pills">${[7, 14, 30, 90].map((n) => html`<button class="pill ${n === days ? "on" : ""}" data-days="${n}">${n} ${plural(n, "день", "дня", "дней")}</button>`)}</div>
    <div class="grid-3" style="margin-top:10px">
      <div class="card stat"><b>${d.logged_days}</b><small>${plural(d.logged_days, "день", "дня", "дней")} с записями</small></div>
      <div class="card stat"><b>${good}</b><small>без симптомов</small></div>
      <div class="card stat"><b>${num(d.averages.kcal)}</b><small>ккал в среднем</small></div></div>
    <div class="card" style="margin-top:12px"><b>Самочувствие по дням</b>${raw(dayChart(d.days))}
      <div class="legend"><span style="--c:var(--green)">хорошо</span><span style="--c:var(--yellow)">дискомфорт</span>
        <span style="--c:var(--red)">плохо</span><span style="--c:var(--accent)">калории</span></div></div>
    ${d.suspects.length ? html`<div class="section-title"><h2>🕵️ Возможные триггеры</h2></div>
      <div class="card">${d.suspects.map((s) => html`<button class="item" data-food="${s.ref}" style="display:block">
        <div class="row between"><b>${s.emoji} ${s.name}</b><span class="small muted">${s.bad} из ${s.eaten}</span></div>${rateBar(s.rate)}</button>`)}
        <p class="small muted">Симптомы после продукта — ещё не доказательство. Проверьте его отдельно, в безопасной порции.</p></div>`
      : html`<div class="card" style="margin-top:12px"><b>🕵️ Триггеры пока не найдены</b><div class="small muted">Отмечайте самочувствие после еды — через несколько дней здесь появятся подозреваемые продукты.</div></div>`}
    ${d.groups.length ? html`<div class="section-title"><h2>FODMAP-группы перед симптомами</h2></div>
      <div class="card">${d.groups.map((g) => html`<div style="margin-bottom:10px"><div class="row between small"><b>${g.name}</b>
        <span class="muted">${g.bad} из ${g.exposures}</span></div>${rateBar(g.rate)}</div>`)}</div>` : ""}
    ${d.symptoms.length ? html`<div class="section-title"><h2>Частые симптомы</h2></div>
      <div class="card">${d.symptoms.map((s) => html`<div class="row between" style="margin-bottom:6px"><span>${s.emoji} ${s.name}</span><b>${s.count}</b></div>`)}</div>` : ""}
    ${d.safe.length ? html`<div class="section-title"><h2>💚 Хорошо переносите</h2></div>
      <div class="pills">${d.safe.map((s) => html`<button class="pill" data-food="${s.ref}">${s.emoji} ${s.name}</button>`)}</div>` : ""}
    ${d.tolerances.length ? html`<div class="section-title"><h2>Мои отметки</h2></div><div class="card">
      ${["avoid", "caution", "ok"].map((s) => byStatus(s).length ? html`<div style="margin-bottom:10px"><b class="small">${MARKS[s]}</b>
        <div class="pills" style="margin-top:6px;flex-wrap:wrap">${byStatus(s).map((t) => html`<button class="pill" data-food="${t.ref}">${t.name}</button>`)}</div></div>` : "")}</div>` : ""}
    <div class="section-title"><h2>Достижения</h2></div>
    <div class="card badges">${d.progress.achievements.map((a) => html`<div class="badge ${a.earned ? "on" : ""}" title="${a.desc}">
      <div class="b">${a.emoji}</div>${a.title}<div>${a.progress}/${a.goal}</div></div>`)}</div>
    <div class="card hero" style="margin-top:14px"><div style="position:relative;z-index:1"><b style="font-size:18px">📄 Отчёт для врача</b>
      <div class="small" style="opacity:.9;margin:4px 0 12px">PDF за ${days} ${plural(days, "день", "дня", "дней")}: питание, симптомы, триггеры, ваши отметки. Бот пришлёт файл в чат.</div>
      <button class="btn ghost" id="report" style="background:rgba(255,255,255,.9);color:#111">Получить PDF</button></div></div>`);

  root.addEventListener("click", async (event) => {
    const el = event.target.closest("[data-days],[data-food],#report");
    if (!el) return;
    if (el.dataset.days) return go(`/insights?days=${el.dataset.days}`, { replace: true });
    if (el.dataset.food) return go(`/food/${encodeURIComponent(el.dataset.food)}`);
    el.disabled = true;
    try {
      const res = await api.post("/api/report", { days: Math.max(7, days) });
      if (res instanceof Blob) {
        const url = URL.createObjectURL(res);
        window.open(url, "_blank");
      } else {
        toast("Отчёт отправлен в чат с ботом 📄", "success");
      }
    } catch (error) {
      showError(error);
    } finally {
      el.disabled = false;
    }
  });
}
