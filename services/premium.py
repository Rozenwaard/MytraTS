import io as io_module

from openpyxl import Workbook
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sql import build_in_clause


# ─── Нормативы (минуты) — источник истины: таблица carte ───
# carte.kind:    'base' (базовый тариф), 'replacement' (замещающий), 'additional' (дополнительный).
# carte.planned: норматив при task_type='Плановый' (NULL = как absolute).
# carte.detail:  task_detail, которым сопоставляется код/причина (NULL у base).

MKD_OBJECT_TYPES = ("Квартира", "Коммунальная квартира", "Дом блокированной застройки")
MKD_IN = ", ".join(f"'{t}'" for t in MKD_OBJECT_TYPES)
BP_MKD = 40   # «Выявление безучетного потребления БП МКД»
BP_IZHS = 60  # «Выявление безучетного потребления БП ИЖС»

ALCOR_TITLE = "Выполнение задания в Алькоре"


async def apply_norms(db_session: AsyncSession, task_numbers: list[str] | None = None) -> None:
    """Проставляет main_afl.norm (база) и main_afl.extra (доп.) по «Тарифы.xlsx».

    norm — основной вид работ (carte.kind='base'); extra — остальное
    («Код …», «Причина…», «+5 Выполнение задания в Алькоре»).
    «Дубли» и «Ручная правка» → norm=0, extra=0.
    """
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

    # Сброс
    await run("norm = NULL, extra = NULL", "1=1")

    # 0. Дубли / Ручная правка → 0
    await run("norm = 0, extra = 0", "task_detail IN ('Дубли', 'Ручная правка')")

    # 1. Базовый тариф (norm)
    await run(
        "norm = (SELECT absolute FROM carte WHERE carte.kind = 'base' AND carte.title = main_afl.task_report LIMIT 1), extra = 0",
        "task_report IS NOT NULL AND task_detail NOT IN ('Дубли', 'Ручная правка')",
    )

    # 2. МКД-разбивка (norm = 40)
    await run(
        f"norm = {BP_MKD}, extra = 0",
        "task_report = 'Выявление безучетного потребления БП' "
        f"AND service_object_type IN ({MKD_IN}) AND task_detail NOT IN ('Дубли', 'Ручная правка')",
    )

    # 3. Замещающие тарифы: norm=0, extra=тариф
    await run(
        "norm = 0, extra = (SELECT absolute FROM carte WHERE carte.kind = 'replacement' AND carte.detail = main_afl.task_detail LIMIT 1)",
        "task_detail IN (SELECT detail FROM carte WHERE carte.kind = 'replacement' AND carte.detail IS NOT NULL) "
        "AND COALESCE(task_type, '') != 'Плановый'",
    )
    await run(
        "norm = 0, extra = (SELECT planned FROM carte WHERE carte.kind = 'replacement' AND carte.detail = main_afl.task_detail LIMIT 1)",
        "task_detail IN (SELECT detail FROM carte WHERE carte.kind = 'replacement' AND carte.detail IS NOT NULL) "
        "AND task_type = 'Плановый'",
    )

    # 4. Дополнительные тарифы: extra += тариф
    await run(
        "extra = extra + (SELECT absolute FROM carte WHERE carte.kind = 'additional' AND carte.detail = main_afl.task_detail LIMIT 1)",
        "task_detail IN (SELECT detail FROM carte WHERE carte.kind = 'additional' AND carte.detail IS NOT NULL)",
    )

    # 5. «Выполнение задания в Алькоре» +5 → extra
    # (дублям по task_report не начисляем, даже если их task_detail был позже перезаписан)
    await run(
        f"extra = extra + (SELECT absolute FROM carte WHERE carte.title = '{ALCOR_TITLE}' LIMIT 1)",
        "COALESCE(task_report, '') <> 'Дубли' AND task_detail NOT IN ('Дубли', 'Ручная правка') AND (norm IS NOT NULL OR extra IS NOT NULL)",
    )


async def apply_manual_norm(db_session: AsyncSession, task_numbers: list[str]) -> None:
    """Норматив после ручной смены вида работ: norm = базовый тариф, extra = «+5 Алькор»."""
    names, params = build_in_clause("n", task_numbers)
    await db_session.execute(text(f"""
        UPDATE main_afl SET
            norm = CASE
                WHEN task_report = 'Выявление безучетного потребления БП'
                     AND service_object_type IN ({MKD_IN}) THEN {BP_MKD}
                WHEN task_report = 'Выявление безучетного потребления БП' THEN {BP_IZHS}
                ELSE (SELECT absolute FROM carte WHERE carte.kind = 'base' AND carte.title = main_afl.task_report LIMIT 1)
            END,
            extra = (SELECT absolute FROM carte WHERE carte.title = '{ALCOR_TITLE}' LIMIT 1)
        WHERE task_number IN ({names})
    """), params)


async def aggregate_utalo(db_session: AsyncSession) -> int:
    """Агрегирует все main_afl (norm != 0 или extra != 0) в utalo.

    База: task_report = основной вид работ, norm_sum = norm.
    Доп.: task_report = источник extra («Код …» или «Выполнение задания в Алькоре»), norm_sum = extra.
    """
    await db_session.execute(text("DELETE FROM utalo"))
    await db_session.execute(text("""
        INSERT INTO utalo (period, staff_id, full_name, position, dept, task_report, count, norm_sum)
        SELECT SUBSTR(m.done_day, 1, 4) || ' ' || SUBSTR(m.done_day, 6, 2),
               u.staff_id, u.full_name, u.position, u.dept, m.task_report,
               COUNT(*), SUM(m.norm)
        FROM main_afl m
        JOIN users u ON u.full_name = m.executor
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
        JOIN users u ON u.full_name = m.executor
        WHERE m.extra != 0 AND m.done_day IS NOT NULL
        GROUP BY 1, 2, 3, 4, 5, 6
    """))
    await db_session.commit()
    return (await db_session.execute(text("SELECT COUNT(*) FROM utalo"))).scalar()


def generate_premium_xlsx_bytes(alcor_rows, project_rows) -> bytes:
    """Xlsx отчёта по нормативам: вкладки «Алькор» (база) и «Проект» (доп.)."""
    headers = ["ФИО", "Должность", "Отделение", "Работа", "Количество", "Норматив"]
    wb = Workbook()
    ws_alcor = wb.active
    ws_alcor.title = "Алькор"
    ws_project = wb.create_sheet("Проект")

    for ws, rows in ((ws_alcor, alcor_rows), (ws_project, project_rows)):
        ws.append(headers)
        for row in rows:
            ws.append(list(row))

    output = io_module.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.read()
