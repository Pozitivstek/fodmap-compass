"""PDF-отчёт для гастроэнтеролога или диетолога."""

from __future__ import annotations

import os
import re
from pathlib import Path

from fpdf import FPDF

from app.domain import CONDITIONS, FEELINGS, MEALS, SYMPTOMS, TOLERANCE_STATUSES
from app.storage.diary import DiaryEntry
from app.storage.reactions import Reaction, ToleranceRecord

FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
)
BOLD_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)
EMOJI_RE = re.compile("[\U00010000-\U0010FFFF☀-➿️‍]")
ACCENT = (46, 125, 96)
MUTED = (110, 110, 110)


class ReportError(RuntimeError):
    """Нет шрифта с кириллицей."""


def _font(candidates: tuple[str, ...], env: str) -> str | None:
    paths = [os.getenv(env, ""), *candidates]
    return next((p for p in paths if p and Path(p).exists()), None)


def clean(text: str) -> str:
    return EMOJI_RE.sub("", str(text)).strip()


class _Pdf(FPDF):
    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Main", size=8)
        self.set_text_color(*MUTED)
        self.cell(0, 6, f"ФудКомпас · стр. {self.page_no()} · справочный отчёт, не является диагнозом", align="C")


def _setup() -> _Pdf:
    regular = _font(FONT_CANDIDATES, "PDF_FONT")
    if not regular:
        raise ReportError("Не найден шрифт с кириллицей (установите fonts-dejavu-core или задайте PDF_FONT)")
    bold = _font(BOLD_CANDIDATES, "PDF_FONT_BOLD") or regular
    pdf = _Pdf(format="A4")
    pdf.add_font("Main", "", regular)
    pdf.add_font("Main", "B", bold)
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.set_margins(15, 15, 15)
    pdf.add_page()
    return pdf


def _heading(pdf: FPDF, text: str) -> None:
    pdf.ln(3)
    pdf.set_font("Main", "B", 13)
    pdf.set_text_color(*ACCENT)
    pdf.cell(0, 8, clean(text), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Main", size=10)


def _line(pdf: FPDF, text: str, size: int = 10, color: tuple = (0, 0, 0)) -> None:
    pdf.set_font("Main", size=size)
    pdf.set_text_color(*color)
    pdf.multi_cell(0, 5.5, clean(text), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)


def _summary(pdf: FPDF, insights: dict) -> None:
    avg = insights["averages"]
    _heading(pdf, "Сводка")
    _line(pdf, f"Дней с записями: {insights['logged_days']}. Записей о самочувствии: {insights['reactions_total']}.")
    if insights.get("good_share") is not None:
        _line(pdf, f"Доля записей без симптомов: {round(insights['good_share'] * 100)}%.")
    _line(pdf, f"В среднем за день: {avg['kcal']:.0f} ккал, белки {avg['protein']:.0f} г, жиры {avg['fat']:.0f} г, "
               f"углеводы {avg['carbs']:.0f} г, клетчатка {avg['fiber']:.0f} г.")


def _lists(pdf: FPDF, insights: dict, tolerances: list[ToleranceRecord]) -> None:
    if insights["symptoms"]:
        _heading(pdf, "Частые симптомы")
        _line(pdf, ", ".join(f"{s['name']} — {s['count']}" for s in insights["symptoms"]))
    if insights["suspects"]:
        _heading(pdf, "Возможные триггеры (по дневнику)")
        for s in insights["suspects"]:
            _line(pdf, f"• {s['name']}: симптомы после {s['bad']} из {s['eaten']} приёмов")
    if insights["groups"]:
        _heading(pdf, "FODMAP-группы перед симптомами")
        for g in insights["groups"]:
            _line(pdf, f"• {g['name']}: {g['bad']} из {g['exposures']} раз ({round(g['rate'] * 100)}%)")
    if tolerances:
        _heading(pdf, "Личная переносимость")
        for status in ("avoid", "caution", "ok"):
            names = [t.name + (f" (до {t.tested_g:g} г)" if t.tested_g and status == "ok" else "")
                     for t in tolerances if t.status == status]
            if names:
                _line(pdf, f"{TOLERANCE_STATUSES[status]['name']}: " + ", ".join(names))


def _diary(pdf: FPDF, entries: list[DiaryEntry], reactions: list[Reaction]) -> None:
    _heading(pdf, "Дневник по дням")
    days = sorted({e.day for e in entries} | {r.day for r in reactions}, reverse=True)
    for day in days:
        pdf.set_font("Main", "B", 10)
        pdf.cell(0, 6, day, new_x="LMARGIN", new_y="NEXT")
        for code, meal in MEALS.items():
            items = [e for e in entries if e.day == day and e.meal == code]
            if items:
                _line(pdf, f"{meal['name']}: " + ", ".join(f"{e.name} {e.grams:g} г" for e in items), size=9)
        for r in (r for r in reactions if r.day == day):
            symptoms = ", ".join(SYMPTOMS[s]["name"] for s in r.symptoms if s in SYMPTOMS)
            where = MEALS.get(r.meal or "", {}).get("name", "день")
            text = f"Самочувствие ({where}): {FEELINGS.get(r.feeling, {}).get('name', r.feeling)}"
            text += f"; {symptoms}" if symptoms else ""
            text += f"; сила {r.severity}/5" if r.severity else ""
            text += f"; «{r.note}»" if r.note else ""
            _line(pdf, text, size=9, color=MUTED)


def build_pdf(*, name: str, period: str, conditions: list[str], insights: dict, entries: list[DiaryEntry],
              reactions: list[Reaction], tolerances: list[ToleranceRecord]) -> bytes:
    pdf = _setup()
    pdf.set_font("Main", "B", 18)
    pdf.cell(0, 10, "Отчёт о питании и самочувствии", new_x="LMARGIN", new_y="NEXT")
    labels = ", ".join(CONDITIONS[c]["name"] for c in conditions if c in CONDITIONS) or "не указаны"
    _line(pdf, f"{name or 'Пользователь'} · период: {period}", color=MUTED)
    _line(pdf, f"Ограничения: {labels}", color=MUTED)
    _summary(pdf, insights)
    _lists(pdf, insights, tolerances)
    _diary(pdf, entries, reactions)
    return bytes(pdf.output())
