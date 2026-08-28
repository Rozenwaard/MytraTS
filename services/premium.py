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
    """Проставляет main_afl.norm по правилам «Тарифы.xlsx» (источник — carte).

    «Дубли» и «Ручная правка» → 0. Замещающие тарифы ставятся вместо базового,
    дополнительные — прибавляются. В конце +5 «Выполнение задания в Алькоре»
    для всех строк, получивших норматив.
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

    # 0. Дубли / Ручная правка → 0
    await run("norm = 0", "task_detail IN ('Дубли', 'Ручная правка')")

    # 1. Базовый тариф (carte.kind='base' по task_report)
    await run(
        "norm = (SELECT absolute FROM carte WHERE carte.kind = 'base' AND carte.title = main_afl.task_report LIMIT 1)",
        "task_report IS NOT NULL AND task_detail NOT IN ('Дубли', 'Ручная правка')",
    )

    # 2. МКД-разбивка: «…БП» в МКД-объектах → 40
    await run(
        f"norm = {BP_MKD}",
        "task_report = 'Выявление безучетного потребления БП' "
        f"AND service_object_type IN ({MKD_IN}) "
        "AND task_detail NOT IN ('Дубли', 'Ручная правка')",
    )

    # 3. Замещающие тарифы (carte.kind='replacement' по detail = task_detail)
    await run(
        "norm = (SELECT absolute FROM carte WHERE carte.kind = 'replacement' AND carte.detail = main_afl.task_detail LIMIT 1)",
        "task_detail IN (SELECT detail FROM carte WHERE carte.kind = 'replacement' AND carte.detail IS NOT NULL) "
        "AND COALESCE(task_type, '') != 'Плановый'",
    )
    await run(
        "norm = (SELECT planned FROM carte WHERE carte.kind = 'replacement' AND carte.detail = main_afl.task_detail LIMIT 1)",
        "task_detail IN (SELECT detail FROM carte WHERE carte.kind = 'replacement' AND carte.detail IS NOT NULL) "
        "AND task_type = 'Плановый'",
    )

    # 4. Дополнительные тарифы (carte.kind='additional' по detail = task_detail)
    await run(
        "norm = norm + (SELECT absolute FROM carte WHERE carte.kind = 'additional' AND carte.detail = main_afl.task_detail LIMIT 1)",
        "task_detail IN (SELECT detail FROM carte WHERE carte.kind = 'additional' AND carte.detail IS NOT NULL)",
    )

    # 5. «Выполнение задания в Алькоре» +5 — всем, кто получил норматив
    await run(
        f"norm = norm + (SELECT absolute FROM carte WHERE carte.title = '{ALCOR_TITLE}' LIMIT 1)",
        "task_detail NOT IN ('Дубли', 'Ручная правка') AND norm IS NOT NULL",
    )


async def apply_manual_norm(db_session: AsyncSession, task_numbers: list[str]) -> None:
    """Норматив после ручной смены вида работ: базовый тариф + «Выполнение задания в Алькоре»."""
    names, params = build_in_clause("n", task_numbers)

    # Базовый тариф + МКД-разбивка
    await db_session.execute(text(f"""
        UPDATE main_afl SET norm = CASE
            WHEN task_report = 'Выявление безучетного потребления БП'
                 AND service_object_type IN ({MKD_IN}) THEN {BP_MKD}
            WHEN task_report = 'Выявление безучетного потребления БП' THEN {BP_IZHS}
            ELSE (SELECT absolute FROM carte WHERE carte.kind = 'base' AND carte.title = main_afl.task_report LIMIT 1)
        END
        WHERE task_number IN ({names})
    """), params)

    # +5 «Выполнение задания в Алькоре»
    await db_session.execute(text(f"""
        UPDATE main_afl SET norm = norm + (SELECT absolute FROM carte WHERE carte.title = '{ALCOR_TITLE}' LIMIT 1)
        WHERE task_number IN ({names}) AND norm IS NOT NULL
    """), params)


async def aggregate_utalo(db_session: AsyncSession, period: str) -> int:
    """Агрегирует main_afl в utalo за период (done_day в периоде, реестр реальный, норматив есть).

    Группировка: работник (по executor = users.full_name) × вид работ. Перезаписывает
    строки затрагиваемого периода.
    """
    prefix = period.replace(" ", "-")
    await db_session.execute(text("DELETE FROM utalo WHERE period = :p"), {"p": period})
    await db_session.execute(text("""
        INSERT INTO utalo (period, staff_id, full_name, position, dept, task_report, count, norm_sum)
        SELECT :p, u.staff_id, u.full_name, u.position, u.dept, m.task_report, COUNT(*), COALESCE(SUM(m.norm), 0)
        FROM main_afl m
        JOIN users u ON u.full_name = m.executor
        WHERE m.done_day LIKE :prefix
          AND m.reestr_number IS NOT NULL AND m.reestr_number != 'Отклонён'
          AND m.norm IS NOT NULL
        GROUP BY u.staff_id, u.full_name, u.position, u.dept, m.task_report
    """), {"p": period, "prefix": prefix + "%"})
    await db_session.commit()
    return (await db_session.execute(text("SELECT COUNT(*) FROM utalo WHERE period = :p"), {"p": period})).scalar()
