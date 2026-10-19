"""Личная переносимость: как реакции меняют отметку продукта именно у этого человека."""

from __future__ import annotations

from dataclasses import replace

from app.clock import utc_iso
from app.domain import FEELINGS
from app.storage.reactions import ToleranceRecord

STATUSES = ("ok", "caution", "avoid")


def is_bad(feeling: str, severity: int = 0) -> bool:
    return FEELINGS.get(feeling, {}).get("weight", 0) > 0 or severity >= 3


def derive_status(ok: int, mild: int, bad: int) -> str:
    if bad >= 2 or (bad >= 1 and ok == 0):
        return "avoid"
    if bad + mild > ok:
        return "caution"
    return "ok"


def apply_reaction(existing: ToleranceRecord | None, ref: str, name: str, feeling: str,
                   grams: float | None) -> ToleranceRecord:
    weight = FEELINGS.get(feeling, {"weight": 0})["weight"]
    base = existing or ToleranceRecord(ref=ref, name=name, status="ok", tested_g=None, ok_count=0,
                                       mild_count=0, bad_count=0, manual=False, note="", updated_at="")
    ok = base.ok_count + (weight == 0)
    mild = base.mild_count + (weight == 1)
    bad = base.bad_count + (weight >= 2)
    tested = base.tested_g
    if weight == 0 and grams:
        tested = max(tested or 0.0, grams)
    status = base.status if base.manual else derive_status(ok, mild, bad)
    return replace(base, name=name or base.name, status=status, tested_g=tested, ok_count=ok, mild_count=mild,
                   bad_count=bad, updated_at=utc_iso())


def set_manual(existing: ToleranceRecord | None, ref: str, name: str, status: str,
               tested_g: float | None, note: str) -> ToleranceRecord:
    if status not in STATUSES:
        raise ValueError(f"unknown status {status}")
    base = existing or ToleranceRecord(ref=ref, name=name, status=status, tested_g=None, ok_count=0,
                                       mild_count=0, bad_count=0, manual=True, note="", updated_at="")
    return replace(base, name=name or base.name, status=status, tested_g=tested_g, manual=True,
                   note=note, updated_at=utc_iso())


def pick_suspects(foods: list[tuple[str, str, float, bool]], feeling: str) -> list[tuple[str, str, float]]:
    """foods: (ref, name, grams, is_risky). При плохом самочувствии виноваты рискованные продукты,
    а если таких нет — все. При хорошем — все продукты приёма пищи получают «подходит»."""
    if not is_bad(feeling) or not any(risky for *_, risky in foods):
        return [(ref, name, grams) for ref, name, grams, _ in foods]
    return [(ref, name, grams) for ref, name, grams, risky in foods if risky]
