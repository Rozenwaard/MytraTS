from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sql import build_in_clause


async def apply_norms(db_session: AsyncSession, task_numbers: list[str] | None = None) -> None:
    """Проставляет main_afl.norm = carte.absolute по совпадению task_report = carte.title.

    Только для строк с реальным номером реестра (не «Отклонён»). Если task_report не
    найден в carte — norm становится NULL. При task_numbers — только по этим строкам.
    """
    where = "reestr_number IS NOT NULL AND reestr_number != 'Отклонён'"
    params: dict = {}
    if task_numbers:
        names, bind_params = build_in_clause("n", task_numbers)
        where += f" AND task_number IN ({names})"
        params.update(bind_params)
    await db_session.execute(
        text(f"UPDATE main_afl SET norm = (SELECT absolute FROM carte WHERE carte.title = main_afl.task_report LIMIT 1) WHERE {where}"),
        params)


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
