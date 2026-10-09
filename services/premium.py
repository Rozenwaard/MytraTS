import io as io_module
from collections import defaultdict

from openpyxl import Workbook, load_workbook
from python_calamine import CalamineWorkbook
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sql import build_in_clause

from services.processor import CUTOVER_DAY


# ─── Нормативы (минуты) ───
# done_day <  CUTOVER_DAY → carte (старый справочник): absolute / planned / detail.
# done_day >= CUTOVER_DAY → work_catalog (новый справочник): norm / planned / detail (short=task_report).

MKD_OBJECT_TYPES = ("Квартира", "Коммунальная квартира", "Дом блокированной застройки")
MKD_IN = ", ".join(f"'{t}'" for t in MKD_OBJECT_TYPES)
BP_MKD = 40   # «Выявление безучетного потребления БП МКД»
BP_IZHS = 60  # «Выявление безучетного потребления БП ИЖС»

ALCOR_TITLE = "Выполнение задания в Алькоре"


_IN_CHUNK = 32500


# ─── 1С-файл (вкладка «1С» отчёта по нормативам) ───
# TDSheet: «Поручение контрагента» (8), «Непосредственный исполнитель1» (18),
# «Непосредственный исполнитель2» (19). Нормативы — временный словарь (из «Лист2» файла).
WORK_NORM_1C = {
    "Бытовая заявка": 30,
    "Допуск ПУ": 80,
    "Допуск ПУ ИЖС": 40,
    "Доставка уведомлений": 5,
    "Жалоба на некач. эл.": 65,
    "Замеры": 80,
    "Инструментальная проверка": 105,
    "Неучтенное потребление ЮЛ": 120,
    "Осмотр": 90,
    "Периодический контроль ЮЛ": 30,
    "Снятие показаний": 35,
}
COL_1C_WORK = 8
COL_1C_EXECUTOR1 = 18
COL_1C_EXECUTOR2 = 19


def _norm_name(name):
    """Нормализация ФИО «ё/е» для сравнения (как в rle._norm)."""
    return (name or "").strip().replace("ё", "е").replace("Ё", "Е")


def _read_1c_sheet(content: bytes) -> list[list]:
    """Читает TDSheet из 1С-файла (calamine, fallback openpyxl)."""
    try:
        wb = CalamineWorkbook.from_filelike(io_module.BytesIO(content))
        return [list(row) for row in wb.get_sheet_by_name("TDSheet").to_python()]
    except Exception:
        wb = load_workbook(io_module.BytesIO(content), read_only=True, data_only=True)
        return [list(row) for row in wb["TDSheet"].iter_rows(values_only=True)]


async def build_1c_rows(db_session: AsyncSession, content: bytes) -> list[list]:
    """Строки вкладки «1С»: [ФИО, Должность, Отделение, Работа, Количество, Норматив].

    «Непосредственный исполнитель2» (если заполнен) — самостоятельная строка.
    Должность/отделение — из users по full_name (сравнение «ё/е»).
    """
    sheet = _read_1c_sheet(content)
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for row in sheet[1:]:
        if not row:
            continue
        work = str(row[COL_1C_WORK]).strip() if len(row) > COL_1C_WORK and row[COL_1C_WORK] else ""
        if not work:
            continue
        for idx in (COL_1C_EXECUTOR1, COL_1C_EXECUTOR2):
            if len(row) > idx and row[idx]:
                executor = str(row[idx]).strip()
                if executor:
                    counts[(executor, work)] += 1

    if not counts:
        return []

    users = (await db_session.execute(text("SELECT full_name, position, dept FROM users"))).fetchall()
    user_by_name = {}
    for full_name, position, dept in users:
        user_by_name[_norm_name(full_name)] = (position or "", dept or "")

    rows = []
    for (executor, work), count in sorted(counts.items(), key=lambda kv: (_norm_name(kv[0][0]), kv[0][1])):
        position, dept = user_by_name.get(_norm_name(executor), ("", ""))
        rows.append([executor, position, dept, work, count, count * WORK_NORM_1C.get(work, 0)])
    return rows


async def apply_norms(db_session: AsyncSession, task_numbers: list[str] | None = None) -> None:
    """Проставляет main_afl.norm (база) и main_afl.extra (доп.).

    done_day <  CUTOVER_DAY — по старому справочнику carte;
    done_day >= CUTOVER_DAY — по новому справочнику work_catalog.
    norm — основной вид работ; extra — остальное («Код …», «Причина…», «+5 Алькор»).
    «Дубли» и «Ручная проверка» → norm=0, extra=0.
    """
    if task_numbers:
        # Бьём на чанки, чтобы не упереться в лимит SQLite по числу bind-параметров.
        for i in range(0, len(task_numbers), _IN_CHUNK):
            await _apply_norms_scoped(db_session, task_numbers[i:i + _IN_CHUNK])
    else:
        await _apply_norms_scoped(db_session, None)


async def _apply_norms_scoped(db_session: AsyncSession, task_numbers: list[str] | None) -> None:
    scope = ""
    scope_params: dict = {}
    if task_numbers:
        names, bind = build_in_clause("n", task_numbers)
        scope = f" AND task_number IN ({names})"
        scope_params.update(bind)

    async def run(set_clause: str, condition: str) -> None:
        await db_session.execute(
            text(f"UPDATE main_afl SET {set_clause} WHERE {condition}{scope}"),
            dict(scope_params),
        )

    old = f"done_day < '{CUTOVER_DAY}'"     # старый справочник carte
    new = f"done_day >= '{CUTOVER_DAY}'"    # новый справочник work_catalog

    # Сброс
    await run("norm = NULL, extra = NULL", "1=1")

    # 0. Дубли / Ручная проверка → 0
    await run("norm = 0, extra = 0", "task_detail IN ('Дубли', 'Ручная проверка')")

    # 1. Базовый тариф (norm)
    await run(
        "norm = (SELECT absolute FROM carte WHERE carte.kind = 'base' AND carte.title = main_afl.task_report LIMIT 1), extra = 0",
        f"task_report IS NOT NULL AND COALESCE(task_detail, '') NOT IN ('Дубли', 'Ручная проверка') AND {old}",
    )
    await run(
        "norm = (SELECT norm FROM work_catalog WHERE work_catalog.kind = 'base' AND work_catalog.short = main_afl.task_report LIMIT 1), extra = 0",
        f"task_report IS NOT NULL AND COALESCE(task_detail, '') NOT IN ('Дубли', 'Ручная проверка') AND {new}",
    )

    # 1a. «Перепрограммирование ПУ»: вид работ остаётся «Бытовые заявки», но норматив 50 (старый справочник).
    await run(
        "norm = 50",
        f"work_type_in_task = 'Перепрограммирование ПУ' AND task_report = 'Бытовые заявки' AND COALESCE(task_detail, '') NOT IN ('Дубли', 'Ручная проверка') AND {old}",
    )

    # 2. «Акт неучтённого потребления» → замещающий норматив «Выявление безучетного потребления»
    # (не вид работ, влияет только на нормативы): ИЖС = 60, МКД = 40.
    # Оверрайд только если оригинальный норматив не выше безучётного.
    await run(
        f"norm = CASE WHEN service_object_type IN ({MKD_IN}) THEN {BP_MKD} ELSE {BP_IZHS} END, extra = 0",
        f"task_detail = 'Акт неучтённого потребления' "
        f"AND COALESCE(norm, 0) <= CASE WHEN service_object_type IN ({MKD_IN}) THEN {BP_MKD} ELSE {BP_IZHS} END",
    )

    # 3. Замещающие тарифы: norm=0, extra=тариф
    await run(
        "norm = 0, extra = (SELECT absolute FROM carte WHERE carte.kind = 'replacement' AND carte.detail = main_afl.task_detail LIMIT 1)",
        f"task_detail IN (SELECT detail FROM carte WHERE carte.kind = 'replacement' AND carte.detail IS NOT NULL) AND COALESCE(task_type, '') != 'Плановый' AND {old}",
    )
    await run(
        "norm = 0, extra = (SELECT planned FROM carte WHERE carte.kind = 'replacement' AND carte.detail = main_afl.task_detail LIMIT 1)",
        f"task_detail IN (SELECT detail FROM carte WHERE carte.kind = 'replacement' AND carte.detail IS NOT NULL) AND task_type = 'Плановый' AND {old}",
    )
    await run(
        "norm = 0, extra = (SELECT norm FROM work_catalog WHERE work_catalog.kind = 'replacement' AND work_catalog.detail = main_afl.task_detail LIMIT 1)",
        f"task_detail IN (SELECT detail FROM work_catalog WHERE work_catalog.kind = 'replacement' AND work_catalog.detail IS NOT NULL) AND COALESCE(task_type, '') != 'Плановый' AND {new}",
    )
    await run(
        "norm = 0, extra = (SELECT planned FROM work_catalog WHERE work_catalog.kind = 'replacement' AND work_catalog.detail = main_afl.task_detail LIMIT 1)",
        f"task_detail IN (SELECT detail FROM work_catalog WHERE work_catalog.kind = 'replacement' AND work_catalog.detail IS NOT NULL) AND task_type = 'Плановый' AND {new}",
    )

    # 4. Дополнительные тарифы: extra += тариф
    await run(
        "extra = extra + (SELECT absolute FROM carte WHERE carte.kind = 'additional' AND carte.detail = main_afl.task_detail LIMIT 1)",
        f"task_detail IN (SELECT detail FROM carte WHERE carte.kind = 'additional' AND carte.detail IS NOT NULL) AND {old}",
    )
    await run(
        "extra = extra + (SELECT norm FROM work_catalog WHERE work_catalog.kind = 'additional' AND work_catalog.detail = main_afl.task_detail LIMIT 1)",
        f"task_detail IN (SELECT detail FROM work_catalog WHERE work_catalog.kind = 'additional' AND work_catalog.detail IS NOT NULL) AND {new}",
    )

    # 5. «Выполнение задания в Алькоре» +5 → extra
    # (дублям по task_report не начисляем, даже если их task_detail был позже перезаписан)
    await run(
        f"extra = extra + (SELECT absolute FROM carte WHERE carte.title = '{ALCOR_TITLE}' LIMIT 1)",
        f"COALESCE(task_report, '') <> 'Дубли' AND COALESCE(task_detail, '') NOT IN ('Дубли', 'Ручная проверка') AND (norm IS NOT NULL OR extra IS NOT NULL) AND {old}",
    )
    await run(
        f"extra = extra + (SELECT norm FROM work_catalog WHERE work_catalog.short = '{ALCOR_TITLE}' LIMIT 1)",
        f"COALESCE(task_report, '') <> 'Дубли' AND COALESCE(task_detail, '') NOT IN ('Дубли', 'Ручная проверка') AND (norm IS NOT NULL OR extra IS NOT NULL) AND {new}",
    )


async def apply_manual_norm(db_session: AsyncSession, task_numbers: list[str]) -> None:
    """Норматив после ручной смены вида работ: norm = базовый тариф, extra = «+5 Алькор».

    При пустом `task_report` (смена на «без вида работ») норматив не начисляем:
    norm=0, extra=0 — иначе строка получала бы +5 «Выполнение задания в Алькоре»
    без основного вида работ.
    """
    names, params = build_in_clause("n", task_numbers)
    await db_session.execute(text(f"""
        UPDATE main_afl SET
            norm = CASE
                WHEN task_report IS NULL THEN 0
                WHEN done_day < '{CUTOVER_DAY}' THEN (SELECT absolute FROM carte WHERE carte.kind = 'base' AND carte.title = main_afl.task_report LIMIT 1)
                WHEN done_day >= '{CUTOVER_DAY}' THEN (SELECT norm FROM work_catalog WHERE work_catalog.short = main_afl.task_report LIMIT 1)
                ELSE 0
            END,
            extra = CASE
                WHEN task_report IS NULL THEN 0
                WHEN done_day < '{CUTOVER_DAY}' THEN (SELECT absolute FROM carte WHERE carte.title = '{ALCOR_TITLE}' LIMIT 1)
                WHEN done_day >= '{CUTOVER_DAY}' THEN (SELECT norm FROM work_catalog WHERE work_catalog.short = '{ALCOR_TITLE}' LIMIT 1)
                ELSE 0
            END
        WHERE task_number IN ({names})
    """), params)


async def aggregate_utalo(db_session: AsyncSession) -> int:
    """Агрегирует все main_afl (norm != 0 или extra != 0) в utalo.

    База: task_report = основной вид работ, norm_sum = norm.
    Доп.: task_report = источник extra («Код …» или «Выполнение задания в Алькоре»), norm_sum = extra.
    """
    await db_session.execute(text("DELETE FROM utalo"))
    await db_session.execute(text(f"""
        INSERT INTO utalo (period, staff_id, full_name, position, dept, task_report, count, norm_sum)
        SELECT SUBSTR(m.done_day, 1, 4) || ' ' || SUBSTR(m.done_day, 6, 2),
               u.staff_id, u.full_name, u.position, u.dept, m.task_report,
               COUNT(*), SUM(m.norm)
        FROM main_afl m
        JOIN users u ON u.executor_name = m.executor
        WHERE m.norm != 0 AND m.done_day IS NOT NULL
        GROUP BY 1, 2, 3, 4, 5, 6

        UNION ALL

        SELECT SUBSTR(m.done_day, 1, 4) || ' ' || SUBSTR(m.done_day, 6, 2),
               u.staff_id, u.full_name, u.position, u.dept,
               COALESCE(
                   (SELECT c.title FROM carte c WHERE c.detail = m.task_detail AND c.detail IS NOT NULL LIMIT 1),
                   'Выполнение задания в Алькоре'
               ),
               COUNT(*), SUM(m.extra)
        FROM main_afl m
        JOIN users u ON u.executor_name = m.executor
        WHERE m.extra != 0 AND m.done_day IS NOT NULL
        GROUP BY 1, 2, 3, 4, 5, 6
    """))
    await db_session.commit()
    return (await db_session.execute(text("SELECT COUNT(*) FROM utalo"))).scalar()


def generate_premium_xlsx_bytes(line_rows, s1c_rows, alcor_rows, project_rows) -> bytes:
    """Xlsx отчёта по нормативам: вкладки «Линия», «1С», «Алькор» (база) и «Проект» (доп.)."""
    wb = Workbook()

    ws_line = wb.active
    ws_line.title = "Линия"
    ws_line.append(["Табель", "ФИО", "Должность", "Отделение", "Время"])
    for row in line_rows:
        ws_line.append(list(row))

    headers = ["ФИО", "Должность", "Отделение", "Работа", "Количество", "Норматив"]

    ws_1c = wb.create_sheet("1С")
    ws_1c.append(headers)
    for row in s1c_rows:
        ws_1c.append(list(row))

    ws_alcor = wb.create_sheet("Алькор")
    ws_project = wb.create_sheet("Проект")

    for ws, rows in ((ws_alcor, alcor_rows), (ws_project, project_rows)):
        ws.append(headers)
        for row in rows:
            ws.append(list(row))

    output = io_module.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.read()
