"""РЛЭ: расчёт периодов по заказчику РЛЭ («Проверка, осмотр ПУ»).

Методика: окно 28 дней назад от последнего воскресенья. Берём только строки
`main_afl` с `work_type_in_task = 'Проверка, осмотр ПУ'`. Окно делим на четыре
недельных периода (для страницы раздела) и на два двухнедельных (для выгрузки
xlsx). Работников считаем пропорцией за день: «все работы / все работники» =
«(РЛЭ + «Проверка, осмотр ПУ») / работники РЛЭ». Доля РЛЭ = минуты (РЛЭ +
«Проверка, осмотр ПУ») / минуты всех видов работ за день; работники РЛЭ за день =
все уникальные исполнители дня × долю РЛЭ; затем усредняем по рабочим дням.

Блок периода (4 подколонки на сеть): «Работы», «Удельно», «В день»,
«Работники». «Работники» сети = доля в минутах РЛЭ × работники РЛЭ;
работники РЛЭ = работники всего × (минуты РЛЭ / минуты всего).
"""

import io
from datetime import date, timedelta

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy import text

WINDOW_DAYS = 28
WEEK_DAYS = 7
WORK_DAYS_PER_WEEK = 5
CHECK_WORK_TYPE = "Проверка, осмотр ПУ"
EXCLUDED_TASK_REPORTS = "('Дубли', 'Ручная проверка')"


def _fmt_dd_mm(d: date) -> str:
    return f"{d.day:02d}.{d.month:02d}"


def _last_sunday(today: date) -> date:
    """Последнее воскресенье (не позже today)."""
    return today - timedelta(days=(today.weekday() + 1) % 7)


def _period_bounds(today: date | None = None) -> tuple[date, date]:
    """Окно 28 дней: [последнее воскресенье − 27 дней, последнее воскресенье]."""
    today = today or date.today()
    end = _last_sunday(today)
    start = end - timedelta(days=WINDOW_DAYS - 1)
    return start, end


def _split(start: date, end: date, days: int) -> list[tuple[date, date]]:
    periods: list[tuple[date, date]] = []
    d = start
    while d <= end:
        d2 = d + timedelta(days=days - 1)
        periods.append((d, d2))
        d = d2 + timedelta(days=1)
    return periods


def weekly_periods(today: date | None = None) -> list[tuple[date, date]]:
    """Четыре недельных периода окна 28 дней (для страницы раздела)."""
    start, end = _period_bounds(today)
    return _split(start, end, WEEK_DAYS)


def biweekly_periods(today: date | None = None) -> list[tuple[date, date]]:
    """Два двухнедельных периода окна 28 дней (для выгружаемого xlsx)."""
    start, end = _period_bounds(today)
    return _split(start, end, 2 * WEEK_DAYS)


async def compute_period_stats(db_session, d1: date, d2: date) -> dict:
    """Статистика периода [d1, d2] по work_type_in_task = «Проверка, осмотр ПУ»."""
    d1_s, d2_s = d1.isoformat(), d2.isoformat()
    stats = {
        "week": d1.isocalendar()[1],
        "range": f"{_fmt_dd_mm(d1)}–{_fmt_dd_mm(d2)}",
    }

    customer_rows = (await db_session.execute(text("""
        SELECT customer, SUM(COALESCE(norm, 0) + COALESCE(extra, 0))
        FROM main_afl
        WHERE done_day BETWEEN :d1 AND :d2 AND work_type_in_task = :wt
        GROUP BY customer
    """), {"d1": d1_s, "d2": d2_s, "wt": CHECK_WORK_TYPE})).fetchall()
    totals = {r[0]: (r[1] or 0) for r in customer_rows}
    rle = totals.get("РЛЭ", 0)

    # Пропорция за день: «все работы / все работники» = «РЛЭ+проверка / работники РЛЭ».
    # workers — все уникальные исполнители дня (по всем видам работ);
    # rle_min — минуты (РЛЭ + «Проверка, осмотр ПУ»); total_min — минуты всех видов работ.
    # Итог — среднее по рабочим дням (5 в неделе / 10 в двухнедельном).
    daily_rows = (await db_session.execute(text("""
        SELECT m.done_day,
               COUNT(DISTINCT m.executor) AS workers,
               SUM(CASE WHEN m.work_type_in_task = :wt AND m.customer = 'РЛЭ'
                        THEN COALESCE(m.norm, 0) + COALESCE(m.extra, 0) ELSE 0 END) AS rle_min,
               SUM(COALESCE(m.norm, 0) + COALESCE(m.extra, 0)) AS total_min
        FROM main_afl m
        WHERE m.done_day BETWEEN :d1 AND :d2
        GROUP BY m.done_day
    """), {"d1": d1_s, "d2": d2_s, "wt": CHECK_WORK_TYPE})).fetchall()
    workers_days = 0.0
    for _day, all_workers, rle_check_min, total_all_min in daily_rows:
        if total_all_min:
            workers_days += (all_workers or 0) * (rle_check_min or 0) / total_all_min
    calendar_days = (d2 - d1).days + 1
    work_days = calendar_days * WORK_DAYS_PER_WEEK // WEEK_DAYS
    workers_for_rle = (workers_days / work_days) if work_days else 0.0

    minute_rows = (await db_session.execute(text("""
        SELECT grid, SUM(COALESCE(norm, 0) + COALESCE(extra, 0))
        FROM main_afl
        WHERE done_day BETWEEN :d1 AND :d2 AND work_type_in_task = :wt
          AND customer = 'РЛЭ'
        GROUP BY grid
    """), {"d1": d1_s, "d2": d2_s, "wt": CHECK_WORK_TYPE})).fetchall()
    grid_minutes = {r[0]: (r[1] or 0) for r in minute_rows}

    work_rows = (await db_session.execute(text(f"""
        SELECT grid, COUNT(task_report)
        FROM main_afl
        WHERE done_day BETWEEN :d1 AND :d2 AND work_type_in_task = :wt
          AND customer = 'РЛЭ'
          AND task_report IS NOT NULL AND task_report NOT IN {EXCLUDED_TASK_REPORTS}
        GROUP BY grid
    """), {"d1": d1_s, "d2": d2_s, "wt": CHECK_WORK_TYPE})).fetchall()
    grid_works = {r[0]: (r[1] or 0) for r in work_rows}

    cells: dict[str, dict] = {}
    total_works = 0
    for grid in sorted(set(grid_minutes) | set(grid_works)):
        minutes = grid_minutes.get(grid, 0)
        works = grid_works.get(grid, 0)
        share = (minutes / rle) if rle else 0.0
        grid_workers = share * workers_for_rle
        per_executor = (works / grid_workers) if grid_workers else 0.0
        per_day = per_executor / WORK_DAYS_PER_WEEK
        cells[grid] = {
            "count": works,
            "per_executor": round(per_executor, 1),
            "per_day": round(per_day, 1),
            "workers": round(grid_workers, 1),
        }
        total_works += works

    stats["cells"] = cells
    stats["total_works"] = total_works
    stats["workers_for_rle"] = round(workers_for_rle, 1)
    total_per_executor = (total_works / workers_for_rle) if workers_for_rle else 0.0
    total_per_day = total_per_executor / WORK_DAYS_PER_WEEK
    stats["total_per_executor"] = round(total_per_executor, 1)
    stats["total_per_day"] = round(total_per_day, 1)
    return stats


def generate_rle_xlsx_bytes(periods_stats: list[dict]) -> bytes:
    """Xlsx: сквозная колонка филиалов + блоки периодов (по 4 подколонки)."""
    grids = sorted({g for ws in periods_stats for g in ws["cells"]})

    wb = Workbook()
    ws = wb.active
    ws.title = "РЛЭ"

    thin = Side(style="thin")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    header_fill = PatternFill("solid", fgColor="D9E1F2")
    week_fill = PatternFill("solid", fgColor="E2EFDA")
    bold = Font(bold=True)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)

    ws.cell(row=1, column=1, value="Филиал")
    ws.merge_cells(start_row=1, start_column=1, end_row=2, end_column=1)

    col = 2
    for ws_ in periods_stats:
        ws.cell(row=1, column=col, value=ws_["range"])
        ws.merge_cells(start_row=1, start_column=col, end_row=1, end_column=col + 3)
        ws.cell(row=2, column=col, value="Работы")
        ws.cell(row=2, column=col + 1, value="Удельно")
        ws.cell(row=2, column=col + 2, value="В день")
        ws.cell(row=2, column=col + 3, value="Работники")
        col += 4

    row = 3
    for grid in grids:
        ws.cell(row=row, column=1, value=grid)
        col = 2
        for ws_ in periods_stats:
            cell = ws_["cells"].get(
                grid, {"count": 0, "per_executor": 0.0, "per_day": 0.0, "workers": 0.0}
            )
            ws.cell(row=row, column=col, value=cell["count"])
            ws.cell(row=row, column=col + 1, value=cell["per_executor"])
            ws.cell(row=row, column=col + 2, value=cell["per_day"])
            ws.cell(row=row, column=col + 3, value=cell["workers"])
            col += 4
        row += 1

    # Итоговая строка: «Всего» + Работы / Удельно / В день / Работники.
    ws.cell(row=row, column=1, value="Всего")
    col = 2
    for ws_ in periods_stats:
        ws.cell(row=row, column=col, value=ws_["total_works"])
        ws.cell(row=row, column=col + 1, value=ws_["total_per_executor"])
        ws.cell(row=row, column=col + 2, value=ws_["total_per_day"])
        ws.cell(row=row, column=col + 3, value=ws_["workers_for_rle"])
        col += 4

    max_col = 1 + len(periods_stats) * 4
    max_row = 2 + len(grids) + 1
    for cells in ws.iter_rows(min_row=1, max_row=max_row, min_col=1, max_col=max_col):
        for cell in cells:
            cell.border = border
            if cell.row == 1:
                cell.font = bold
                cell.alignment = center
                if cell.column > 1:
                    cell.fill = week_fill
            elif cell.row == 2:
                cell.font = bold
                cell.alignment = center
                cell.fill = header_fill
            if cell.row == max_row or (cell.column == 1 and cell.row > 2):
                cell.font = bold

    ws.column_dimensions["A"].width = 14
    for c in range(2, max_col + 1):
        ws.column_dimensions[get_column_letter(c)].width = 13
    ws.freeze_panes = "B3"

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()
