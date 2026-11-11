"""Карусель отчётных периодов (месяцев) — общая для Финотчёта и РЛЭ.

Логика зеркалит /fin-report/periods (routers/fin_report.py): месяцы от первого
отчёта до «фронтира» (следующего отчётного периода после последнего в main_afl),
максимум 6. Держать в синхроне с routers/fin_report.py.
"""

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from data.config import story_session_factory

_REPORT_GLOB = "[0-9][0-9][0-9][0-9] [0-9][0-9]"


def _ym(s: str) -> tuple[int, int]:
    return tuple(int(x) for x in s.split(" "))


def _add(y: int, m: int, d: int) -> tuple[int, int]:
    m += d
    while m < 1:
        m += 12
        y -= 1
    while m > 12:
        m -= 12
        y += 1
    return y, m


async def _next_period(db_session: AsyncSession) -> str:
    """Следующий отчётный период после последнего в main_afl (формат 'ГГГГ ММ')."""
    latest = (await db_session.execute(
        text(f"SELECT MAX(report) FROM main_afl WHERE report GLOB '{_REPORT_GLOB}'"))).scalar()
    if latest:
        year, month = (int(x) for x in latest.split(" "))
        month += 1
        if month > 12:
            year += 1
            month = 1
        return f"{year:04d} {month:02d}"
    now = datetime.now()
    return f"{now.year:04d} {now.month:02d}"


async def compute_report_periods(db_session: AsyncSession) -> dict:
    """Список отчётных периодов (карусель) + default (фронтир)."""
    row = (await db_session.execute(
        text(f"SELECT MIN(report), MAX(report) FROM main_afl WHERE report GLOB '{_REPORT_GLOB}'"))).one()
    first_unarchived, last_report = row[0], row[1]

    async with story_session_factory() as story_session:
        first_report_story = (await story_session.execute(
            text(f"SELECT MIN(report) FROM story_afl WHERE report GLOB '{_REPORT_GLOB}'"))).scalar()
        archived = set((await story_session.execute(
            text(f"SELECT DISTINCT report FROM story_afl WHERE report GLOB '{_REPORT_GLOB}'"))).scalars().all())

    first_report = first_unarchived
    if first_report_story and (not first_report or first_report_story < first_report):
        first_report = first_report_story

    next_period = await _next_period(db_session)
    ny, nm = _ym(next_period)

    now = datetime.now()
    frontier = (ny, nm)
    if first_unarchived:
        cap = _add(*_ym(first_unarchived), 5)
        frontier = min(frontier, cap)
    fy, fm = frontier

    if first_report:
        py, pm = _ym(first_report)
        n = (fy - py) * 12 + (fm - pm) + 1
        while n > 6 and f"{py:04d} {pm:02d}" in archived:
            py, pm = _add(py, pm, 1)
            n -= 1
    else:
        n = 1
    count = n

    default = f"{fy:04d}-{fm:02d}"

    periods = []
    y, m = fy, fm
    for _ in range(count):
        value = f"{y:04d}-{m:02d}"
        has_rows = (await db_session.execute(
            text("SELECT COUNT(*) FROM main_afl WHERE done_day LIKE :p"),
            {"p": f"{y:04d}-{m:02d}%"})).scalar() > 0
        if value == default:
            category = "current"
        elif value.replace("-", " ") == last_report:
            category = "previous"
        else:
            category = "old"
        is_archived = value.replace("-", " ") in archived
        can_form = (y, m) <= (now.year, now.month)
        periods.append({
            "value": value,
            "has_rows": has_rows,
            "is_current": value == default,
            "is_archived": is_archived,
            "category": category,
            "can_form": can_form,
        })
        m -= 1
        if m == 0:
            m = 12
            y -= 1

    return {"periods": periods, "default": default}
