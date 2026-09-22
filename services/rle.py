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
from collections import defaultdict
from datetime import date, datetime, timedelta

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from python_calamine import CalamineWorkbook
from sqlalchemy import text

from sql import build_in_clause

WINDOW_DAYS = 28
WEEK_DAYS = 7
WORK_DAYS_PER_WEEK = 5
CHECK_WORK_TYPE = "Проверка, осмотр ПУ"
EXCLUDED_TASK_REPORTS = "('Дубли', 'Ручная проверка')"

# ─── 1С-файл (дополнительные работы/работники РЛЭ) ───
# TDSheet: C=2 «Заказчик.Входит в группу» (ЛЭ→РЛЭ, иначе ПСК), D=3 филиал/сеть,
# F=5 «Поручение контрагента» (работа), H=7 «Дата работ», Q=16 «Непосредственные исполнители».
FILE_SHEET_DATA = "TDSheet"       # строки работ
COL_CUSTOMER_GROUP = 2            # C
COL_BRANCH = 3                    # D
COL_WORK = 5                      # F
COL_DATE = 7                      # H
COL_EXECUTOR = 16                 # Q

# Соответствие названий работ файла («Поручение контрагента») → carte.title.
# Вкладки «Лист2» в боевом файле нет — маппинг зашит в код.
WORK_MAP = {
    "Акт о недопуске": "Недопуск",
    "Бытовая заявка": "Бытовые заявки",
    "Допуск ПУ": "Допуск ПУ ЮЛ",
    "Допуск ПУ БП": "Допуск ПУ в МКД",
    "Допуск ПУ ИЖС": "Допуск ПУ в ИЖС",
    "Доставка уведомлений": "Разнос уведомлений",
    "Жалоба на некач. эл.": "Жалобы на качество",
    "Замеры": "Чтение профиля ПУ",
    "Инструментальная проверка": "Инструментальная проверка",
    "Неучтенное потребление ЮЛ": "Выявление безучетного потребления ЮЛ",
    "Осмотр": "Осмотр ЮЛ",
    "Периодический контроль ЮЛ": "Периодический контроль ЮЛ",
    "Снятие показаний": "Снятие показаний ЮЛ",
}

# «тхвэс» в файле — это «ТхЭС» в mytra (см. нормирование сетей в процессоре).
BRANCH_NORM = {"ТхвЭС": "ТхЭС"}

# Две таблицы сводного отчёта: «интересующие виды» из main_afl + из 1С-файла.
KSP_MAIN_TYPES = ("Проверка, осмотр ПУ",)
KSP_FILE_TITLES = ("Бытовые заявки", "Снятие показаний ЮЛ")
IP_MAIN_TYPES = ("Инструментальная проверка",)
IP_FILE_TITLES = ("Инструментальная проверка",)

# Для сводного отчёта РЛЭ «Инструментальная проверка» = 2 × 105 мин (работает пара),
# даже там, где в файле указан один исполнитель. Это множитель только для отчёта;
# carte.absolute (105) не меняем.
IP_WORK_MINUTES = 210


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


def _norm(name: str) -> str:
    """Нормализация ФИО «ё/е» для сравнения (данные в БД/файле не меняем)."""
    return (name or "").strip().replace("ё", "е").replace("Ё", "Е")


def _parse_date(value) -> date | None:
    """«12.09.2026» / «2026-09-12» / date / datetime → date, иначе None."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_rle_file(content: bytes) -> list[dict]:
    """Парсит 1С-файл TDSheet → псевдо-строки {date, grid, work, workers, customer}.

    Соответствие названий работ файла («Поручение контрагента») таблице `carte.title`
    зашито в `WORK_MAP` (вкладки «Лист2» в боевом файле нет). Берём ВСЕ строки:
    заказчик C = «ЛЭ» → `РЛЭ`, иначе → `ПСК`. Колонки: C заказчик, D филиал,
    F работа, H дата, Q исполнители (через «;»).
    """
    try:
        wb = CalamineWorkbook.from_filelike(io.BytesIO(content))
        data = wb.get_sheet_by_name(FILE_SHEET_DATA).to_python()
    except Exception:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        data = [list(row) for row in wb[FILE_SHEET_DATA].iter_rows(values_only=True)]

    rows: list[dict] = []
    for row in data[1:]:
        if not row or len(row) <= COL_EXECUTOR:
            continue
        group = str(row[COL_CUSTOMER_GROUP]).strip() if len(row) > COL_CUSTOMER_GROUP else ""
        customer = "РЛЭ" if group == "ЛЭ" else "ПСК"
        work_file = str(row[COL_WORK]).strip() if len(row) > COL_WORK else ""
        work_title = WORK_MAP.get(work_file)
        day = _parse_date(row[COL_DATE]) if len(row) > COL_DATE else None
        if day is None:
            continue
        grid = str(row[COL_BRANCH]).strip() if len(row) > COL_BRANCH else ""
        grid = BRANCH_NORM.get(grid, grid)
        workers = [_norm(w) for w in str(row[COL_EXECUTOR]).split(";")] if row[COL_EXECUTOR] else []
        workers = [w for w in workers if w]
        rows.append({"date": day, "grid": grid, "work": work_title, "workers": workers, "customer": customer})
    return rows


async def build_file_minutes(db_session) -> dict[str, int]:
    """Минуты работ файла по carte.absolute + множитель 2 для «Инструментальной проверки»."""
    minutes = dict((await db_session.execute(
        text("SELECT title, COALESCE(absolute, 0) FROM carte WHERE kind = 'base'"))).fetchall())
    minutes["Инструментальная проверка"] = IP_WORK_MINUTES
    return minutes


async def compute_merged_period_stats(db_session, d1: date, d2: date, file_rows: list[dict],
                                      main_types: tuple[str, ...], file_titles: tuple[str, ...],
                                      file_minutes: dict[str, int]) -> dict:
    """Статистика периода по интересующим видам работ (main_afl + 1С-файл).

    Работники(филиал) = Σ по дням [фокусные минуты дня(филиал) / все минуты дня(филиал)]
    / рабочих дней. «Всего» — без фильтра по филиалу.
    """
    d1_s, d2_s = d1.isoformat(), d2.isoformat()
    stats = {"week": d1.isocalendar()[1], "range": f"{_fmt_dd_mm(d1)}–{_fmt_dd_mm(d2)}"}

    file_in = [r for r in file_rows if d1 <= r["date"] <= d2]
    file_total_dg: dict = defaultdict(int)
    file_focus_dg: dict = defaultdict(int)
    file_grid_works: dict = defaultdict(int)
    file_workers: dict = defaultdict(set)
    for r in file_in:
        key = (r["date"].isoformat(), r["grid"])
        minutes = file_minutes.get(r["work"], 0)
        file_total_dg[key] += minutes
        if r["workers"]:
            file_workers[key].update(r["workers"])
        if r["customer"] == "РЛЭ" and r["work"] in file_titles:
            file_focus_dg[key] += minutes
            file_grid_works[r["grid"]] += 1

    names, types_params = build_in_clause("t", main_types)
    base = {"d1": d1_s, "d2": d2_s}

    # Все минуты (main_afl) по дням и сетям.
    main_total_rows = (await db_session.execute(text("""
        SELECT done_day, grid, SUM(COALESCE(norm, 0) + COALESCE(extra, 0))
        FROM main_afl WHERE done_day BETWEEN :d1 AND :d2 GROUP BY done_day, grid
    """), base)).fetchall()
    main_total_dg = {(r[0], r[1]): (r[2] or 0) for r in main_total_rows if r[1]}

    # Фокусные минуты (main_afl) по дням и сетям.
    main_focus_rows = (await db_session.execute(text(f"""
        SELECT done_day, grid, SUM(COALESCE(norm, 0) + COALESCE(extra, 0))
        FROM main_afl WHERE done_day BETWEEN :d1 AND :d2
          AND work_type_in_task IN ({names}) AND customer = 'РЛЭ'
        GROUP BY done_day, grid
    """), {**base, **types_params})).fetchall()
    main_focus_dg = {(r[0], r[1]): (r[2] or 0) for r in main_focus_rows if r[1]}

    # Работы (фокусные) по сетям (main_afl).
    grid_work_rows = (await db_session.execute(text(f"""
        SELECT grid, COUNT(task_report)
        FROM main_afl
        WHERE done_day BETWEEN :d1 AND :d2 AND work_type_in_task IN ({names})
          AND customer = 'РЛЭ'
          AND task_report IS NOT NULL AND task_report NOT IN {EXCLUDED_TASK_REPORTS}
        GROUP BY grid
    """), {**base, **types_params})).fetchall()
    grid_works = {r[0]: (r[1] or 0) for r in grid_work_rows if r[0]}

    # Уникальные работники дня: по филиалу (branch_workers) и всего (all_workers).
    exec_rows = (await db_session.execute(text("""
        SELECT done_day, grid, executor FROM main_afl
        WHERE done_day BETWEEN :d1 AND :d2 AND executor IS NOT NULL AND executor != ''
    """), base)).fetchall()
    branch_workers: dict = defaultdict(set)
    all_workers: dict = defaultdict(set)
    for day, grid, executor in exec_rows:
        all_workers[day].add(_norm(executor))
        if grid:
            branch_workers[(day, grid)].add(_norm(executor))
    for key, workers in file_workers.items():
        day, grid = key
        all_workers[day].update(workers)
        branch_workers[key].update(workers)

    day_total = defaultdict(lambda: defaultdict(int))
    day_focus = defaultdict(lambda: defaultdict(int))
    for (day, grid), v in main_total_dg.items():
        day_total[day][grid] += v
    for (day, grid), v in file_total_dg.items():
        day_total[day][grid] += v
    for (day, grid), v in main_focus_dg.items():
        day_focus[day][grid] += v
    for (day, grid), v in file_focus_dg.items():
        day_focus[day][grid] += v

    calendar_days = (d2 - d1).days + 1
    work_days = calendar_days * WORK_DAYS_PER_WEEK // WEEK_DAYS

    all_grids = set(grid_works) | set(file_grid_works)
    for day in day_focus:
        all_grids.update(day_focus[day].keys())

    cells: dict[str, dict] = {}
    total_works = 0
    for grid in sorted(all_grids):
        workers_sum = 0.0
        for day in day_total:
            total = day_total[day].get(grid, 0)
            if total:
                workers_sum += len(branch_workers.get((day, grid), set())) * (day_focus[day].get(grid, 0) / total)
        workers = (workers_sum / work_days) if work_days else 0.0
        works = grid_works.get(grid, 0) + file_grid_works.get(grid, 0)
        per_executor = (works / workers) if workers else 0.0
        per_day = (per_executor / work_days) if work_days else 0.0
        cells[grid] = {
            "count": works,
            "per_executor": round(per_executor, 1),
            "per_day": round(per_day, 1),
            "workers": round(workers, 1),
        }
        total_works += works

    # «Всего» — без фильтра по филиалу.
    total_workers_sum = 0.0
    for day in day_total:
        f = sum(day_focus[day].values())
        t = sum(day_total[day].values())
        if t:
            total_workers_sum += len(all_workers.get(day, set())) * (f / t)
    total_workers = (total_workers_sum / work_days) if work_days else 0.0

    stats["cells"] = cells
    stats["total_works"] = total_works
    stats["workers_for_rle"] = round(total_workers, 1)
    total_per_executor = (total_works / total_workers) if total_workers else 0.0
    total_per_day = (total_per_executor / work_days) if work_days else 0.0
    stats["total_per_executor"] = round(total_per_executor, 1)
    stats["total_per_day"] = round(total_per_day, 1)
    return stats


def _fill_period_sheet(ws, periods_stats: list[dict]) -> None:
    """Заполняет лист: сквозная колонка филиалов + блоки периодов (по 4 подколонки)."""
    grids = sorted({g for ws in periods_stats for g in ws["cells"]})

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


def generate_rle_xlsx_bytes(periods_stats: list[dict]) -> bytes:
    """Xlsx: сквозная колонка филиалов + блоки периодов (по 4 подколонки)."""
    wb = Workbook()
    ws = wb.active
    ws.title = "РЛЭ"
    _fill_period_sheet(ws, periods_stats)
    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()


def generate_merged_rle_xlsx_bytes(ksp_stats: list[dict], ip_stats: list[dict]) -> bytes:
    """Сводный xlsx РЛЭ: две таблицы — «КСП» и «ИП»."""
    wb = Workbook()
    ws_ksp = wb.active
    ws_ksp.title = "КСП"
    _fill_period_sheet(ws_ksp, ksp_stats)

    ws_ip = wb.create_sheet("ИП")
    _fill_period_sheet(ws_ip, ip_stats)

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()


# ─── «Реестр показаний» (показания и нарушения РЛЭ за месяц) ───
READINGS_HEADERS = [
    "Филиал", "Задание", "Поручение", "Абонент", "Объект", "Район", "Адрес",
    "ПУ", "Номер", "День", "Ночь", "Нарушение", "Расшифровка", "Выполнение",
    "Билинг", "Результат", "Отчёт", "Дополнительно",
]
# «Расшифровка» = meter_malfunction + три следующие за ним колонки main_afl.
VIOLATION_DETAIL_FIELDS = (
    "meter_malfunction", "unauthorized_interference",
    "unauthorized_connection", "additional_violations",
)
MONTH_NAMES = ["", "январь", "февраль", "март", "апрель", "май", "июнь",
               "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]


def _cell(value) -> str:
    """None → пустая строка, иначе str (все колонки реестра — Text)."""
    return "" if value is None else str(value)


def _first_reading(*values) -> str:
    """Первое непустое показание (None/''/'-' пропускаем), иначе '-'."""
    for v in values:
        if v is not None and str(v).strip() not in ("", "-"):
            return str(v)
    return "-"


async def fetch_readings_register_rows(db_session, year_month: str) -> list[list]:
    """Строки «Реестра показаний»: РЛЭ + непустой task_report + done_day в месяце.

    Показания «День»/«Ночь» ищем сначала в t1/t2, затем в t1_1/t2_1 (какие найдутся).
    «Расшифровка» = склейка meter_malfunction + 3 следующих колонок через '; '.
    """
    result = await db_session.execute(text("""
        SELECT grid, created_at, work_type_in_task, personal_account,
               service_object_type, municipal_district, address,
               meter_model, meter_serial_number,
               t1, t2, t1_1, t2_1, violations,
               meter_malfunction, unauthorized_interference,
               unauthorized_connection, additional_violations,
               done_day, sent_to_billing, task_output, task_report, task_detail
        FROM main_afl
        WHERE customer = 'РЛЭ'
          AND task_report IS NOT NULL AND task_report != ''
          AND SUBSTR(done_day, 1, 7) = :ym
        ORDER BY done_day, created_at
    """), {"ym": year_month})

    rows = []
    for r in result.fetchall():
        m = dict(r._mapping)
        detail = "; ".join(
            _cell(m[field]) for field in VIOLATION_DETAIL_FIELDS
            if m[field] is not None and str(m[field]).strip() != ""
        )
        rows.append([
            _cell(m["grid"]), _cell(m["created_at"]), _cell(m["work_type_in_task"]),
            _cell(m["personal_account"]), _cell(m["service_object_type"]),
            _cell(m["municipal_district"]), _cell(m["address"]),
            _cell(m["meter_model"]), _cell(m["meter_serial_number"]),
            _first_reading(m["t1"], m["t1_1"]),
            _first_reading(m["t2"], m["t2_1"]),
            _cell(m["violations"]), detail, _cell(m["done_day"]),
            _cell(m["sent_to_billing"]), _cell(m["task_output"]),
            _cell(m["task_report"]), _cell(m["task_detail"]),
        ])
    return rows


def generate_readings_violations_xlsx(rows: list[list]) -> bytes:
    """Xlsx «Реестр показаний и нарушений»: шапка + данные."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(READINGS_HEADERS)
    for row in rows:
        ws.append(row)
    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()
