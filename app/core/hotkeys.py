"""Номера быстрого запуска: Ctrl+1…9 для программ, Ctrl+Alt+1…9 для наборов.

Работают только внутри окна Centurio. Глобальных сочетаний у программы нет:
системные клавиши перехватывали Ctrl+1…9 у браузеров и офиса, а Ctrl+Alt+N
на раскладках с AltGr не давал набирать символы.
"""
from __future__ import annotations

QUICK_SLOTS = 9
APP_PATTERN = "Ctrl+{}"
SET_PATTERN = "Ctrl+Alt+{}"


def _numbered(records, pattern: str, wanted) -> dict[str, str]:
    picked = [rec["id"] for rec in records if wanted(rec)][:QUICK_SLOTS]
    return {rid: pattern.format(n) for n, rid in enumerate(picked, start=1)}


def quick_accels(apps) -> dict[str, str]:
    return _numbered(apps, APP_PATTERN, lambda a: a.get("quick"))


def set_accels(sets) -> dict[str, str]:
    return _numbered(sets, SET_PATTERN, lambda rec: True)


def resolve_accels(apps, sets) -> tuple[dict[str, str], dict[str, str]]:
    return quick_accels(apps), set_accels(sets)


def free_quick_slot(apps) -> int:
    used = len(quick_accels(apps))
    return used + 1 if used < QUICK_SLOTS else 0


def slot_target(accels: dict[str, str], digit: str) -> str | None:
    """id записи, которой достался номер `digit` в `accels`, или None."""
    return next((rid for rid, accel in accels.items()
                 if accel.rsplit("+", 1)[-1] == digit), None)
