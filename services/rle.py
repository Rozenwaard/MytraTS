"""РЛЭ: расчёт недельных блоков «кол-во работ / на исполнителя / в день».

Методика — из эталонного xlsx (feel.xlsx): для каждой недели считаем минуты
(norm + extra) по заказчикам и число исполнителей, а по каждой сети (grid) —
долю в минутах РЛЭ и количество работ. Блок недели = «кол-во работ»,
«на исполнителя», «в день» (рабочая неделя = 5 дней).

Недели считаются от 27-й (начало производственного года, июль) до последней
полной недели на момент запроса.
"""

import io
from datetime import date

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy import text

WEEK_START = 27
WORK_DAYS_PER_WEEK = 5
EXCLUDED_TASK_REPORTS = "('Дубли', 'Ручная проверка')"


def _fmt_dd_mm(s: str) -> str:
    return f"{s[8:10]}.{s[5:7]}"


async def _scalar(db_session, sql: str, params: dict):
    return (await db_session.execute(text(sql), params)).scalar()


async def _max_week(db_session, year: int) -> int:
    value = await _scalar(db_session, "SELECT MAX(week) FROM calendar WHERE year = :y", {"y": year})
    return value or 53


async def _week_range(db_session, year: int, week: int):
    row = (await db_session.execute(
        text("SELECT MIN(d), MAX(d) FROM calendar WHERE year = :y AND week = :w"),
        {"y": year, "w": week})).first()
    return (row[0], row[1]) if row else (None, None)


async def build_week_sequence(db_session) -> list[tuple[int, int]]:
    """Список (year, week) от недели 27 производственного года до последней полной недели."""
    today = date.today()
    row = (await db_session.execute(
        text("SELECT year, week FROM calendar WHERE d = :d"),
        {"d": today.isoformat()})).first()
    if not row:
        return []
    today_year, today_week = row
    start_year = today_year if today_week >= WEEK_START else today_year - 1

    last = (await db_session.execute(
        text("SELECT year, week FROM calendar GROUP BY year, week "
             "HAVING MAX(d) < :d ORDER BY MAX(d) DESC LIMIT 1"),
        {"d": today.isoformat()})).first()
    if not last:
        return []

    sequence: list[tuple[int, int]] = []
    year, week = start_year, WEEK_START
    for _ in range(70):
        sequence.append((year, week))
        if (year, week) == (last[0], last[1]):
            break
        if week >= await _max_week(db_session, year):
            year, week = year + 1, 1
        else:
            week += 1
    return sequence


async def compute_week_stats(db_session, year: int, week: int) -> dict:
    """Статистика одной недели: минуты по заказчикам, исполнители, сети (grid)."""
    d1, d2 = await _week_range(db_session, year, week)
    stats = {
        "year": year,
        "week": week,
        "range": f"{_fmt_dd_mm(d1)}–{_fmt_dd_mm(d2)}" if d1 and d2 else "",
    }

    customer_rows = (await db_session.execute(text("""
        SELECT customer, SUM(COALESCE(norm, 0) + COALESCE(extra, 0))
        FROM main_afl m JOIN calendar c ON c.d = m.done_day
        WHERE c.year = :y AND c.week = :w
        GROUP BY customer
    """), {"y": year, "w": week})).fetchall()
    totals = {r[0]: (r[1] or 0) for r in customer_rows}
    psk = totals.get("ПСК", 0)
    rle = totals.get("РЛЭ", 0)
    total = psk + rle

    executors = (await _scalar(db_session, """
        SELECT COUNT(DISTINCT m.executor)
        FROM main_afl m JOIN calendar c ON c.d = m.done_day
        WHERE c.year = :y AND c.week = :w
    """, {"y": year, "w": week})) or 0
    executors_for_rle = (executors * rle / total) if total else 0.0

    minute_rows = (await db_session.execute(text("""
        SELECT grid, SUM(COALESCE(norm, 0) + COALESCE(extra, 0))
        FROM main_afl m JOIN calendar c ON c.d = m.done_day
        WHERE c.year = :y AND c.week = :w AND customer = 'РЛЭ'
        GROUP BY grid
    """), {"y": year, "w": week})).fetchall()
    grid_minutes = {r[0]: (r[1] or 0) for r in minute_rows}

    work_rows = (await db_session.execute(text(f"""
        SELECT grid, COUNT(task_report)
        FROM main_afl m JOIN calendar c ON c.d = m.done_day
        WHERE c.year = :y AND c.week = :w AND customer = 'РЛЭ'
          AND task_report IS NOT NULL AND task_report NOT IN {EXCLUDED_TASK_REPORTS}
        GROUP BY grid
    """), {"y": year, "w": week})).fetchall()
    grid_works = {r[0]: (r[1] or 0) for r in work_rows}

    cells: dict[str, dict] = {}
    total_works = 0
    for grid in sorted(set(grid_minutes) | set(grid_works)):
        minutes = grid_minutes.get(grid, 0)
        works = grid_works.get(grid, 0)
        share = (minutes / rle) if rle else 0.0
        grid_executors = share * executors_for_rle
        per_executor = (works / grid_executors) if grid_executors else 0.0
        per_day = per_executor / WORK_DAYS_PER_WEEK
        cells[grid] = {
            "count": works,
            "per_executor": round(per_executor, 1),
            "per_day": round(per_day, 1),
        }
        total_works += works

    stats["cells"] = cells
    stats["total_works"] = total_works
    stats["executors_for_rle"] = round(executors_for_rle, 1)
    return stats


def generate_rle_xlsx_bytes(weeks_stats: list[dict]) -> bytes:
    """Xlsx: сквозная колонка филиалов + недельные блоки (по 3 подколонки)."""
    grids = sorted({g for ws in weeks_stats for g in ws["cells"]})

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
    for ws_ in weeks_stats:
        ws.cell(row=1, column=col, value=f"Неделя {ws_['week']}")
        ws.merge_cells(start_row=1, start_column=col, end_row=1, end_column=col + 2)
        ws.cell(row=2, column=col, value="Работы")
        ws.cell(row=2, column=col + 1, value="Удельно")
        ws.cell(row=2, column=col + 2, value="В день")
        col += 3

    row = 3
    for grid in grids:
        ws.cell(row=row, column=1, value=grid)
        col = 2
        for ws_ in weeks_stats:
            cell = ws_["cells"].get(grid, {"count": 0, "per_executor": 0.0, "per_day": 0.0})
            ws.cell(row=row, column=col, value=cell["count"])
            ws.cell(row=row, column=col + 1, value=cell["per_executor"])
            ws.cell(row=row, column=col + 2, value=cell["per_day"])
            col += 3
        row += 1

    # Итоговая строка: «Всего работ» + на каждую неделю «Исполнителей»
    ws.cell(row=row, column=1, value="Всего работ")
    col = 2
    for ws_ in weeks_stats:
        ws.cell(row=row, column=col, value=ws_["total_works"])
        ws.cell(row=row, column=col + 1, value="Работников")
        ws.cell(row=row, column=col + 2, value=ws_["executors_for_rle"])
        col += 3

    max_col = 1 + len(weeks_stats) * 3
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
