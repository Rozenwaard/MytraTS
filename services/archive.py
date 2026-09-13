"""Архивация строк: mytra.main_afl → story.story_afl → story.consumers.

Запускается по cron 22-го числа в 22:00 (см. archive.py).
"""

from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from data.config import STORY_DB_PATH
from data.story_models import StoryAfl

# Колонки story_afl без id — зеркало main_afl (минус 18 «лишних»).
STORY_AFL_COLUMNS = [c.name for c in StoryAfl.__table__.columns if c.name != 'id']

# Поля consumers (без id и metering_point).
CONSUMER_FIELDS = [
    'address', 'municipal_district', 'house_type', 'personal_account',
    'contract_status', 'contract_created_at', 'service_object_type',
    'subscriber_name', 'subscriber_type', 'subscriber_phone',
    'meter_model', 'meter_serial_number', 'manufacture_year',
    'last_verification_date', 'meter_tariff_rate', 'integer_capacity',
    'fractional_capacity', 'calibration_interval', 'rated_current',
    'rated_voltage', 'meter_installation_place', 'meter_status',
    'meter_ownership', 'seals',
]

_CHUNK = 900


def last_report_period(today: date) -> tuple[str, str]:
    """«Последний отчёт» = предыдущий месяц. Возвращает ('YYYY MM', 'YYYY-MM')."""
    month = today.month - 1
    year = today.year
    if month == 0:
        month = 12
        year -= 1
    return f"{year} {month:02d}", f"{year}-{month:02d}"


def _where_clause() -> str:
    """Группа A (report < последний) ИЛИ группа B (пустой report + З% + Отклонён + done_day ≤ последний месяц)."""
    # TODO: report='Отклонён' (ставит report.py) не попадает ни в A, ни в B — разобраться,
    # откатывать ли эту пометку в report.py (вдруг она нужна).
    a = "report IS NOT NULL AND report != '' AND report < :report_str"
    b = ("(report IS NULL OR report = '') AND status LIKE 'З%' "
         "AND reestr_number = 'Отклонён' AND SUBSTR(done_day, 1, 7) <= :month_str")
    return f"({a}) OR ({b})"


def _base_params(report_str: str, month_str: str) -> dict:
    return {"report_str": report_str, "month_str": month_str}


async def preview(main_session: AsyncSession, report_str: str, month_str: str) -> tuple[int, int]:
    """Сколько строк уедет и сколько разных точек учёта затронуто (без изменений)."""
    where = _where_clause()
    params = _base_params(report_str, month_str)
    total = (await main_session.execute(
        text(f"SELECT COUNT(*) FROM main_afl WHERE {where}"), params)).scalar()
    mps = (await main_session.execute(
        text(f"SELECT COUNT(DISTINCT metering_point) FROM main_afl "
             f"WHERE {where} AND metering_point IS NOT NULL AND metering_point != ''"), params)).scalar()
    return int(total or 0), int(mps or 0)


async def archive_main_to_story(
    main_session: AsyncSession,
    report_str: str, month_str: str,
    story_db_path: str = STORY_DB_PATH,
) -> tuple[int, list[str]]:
    """Переносит (группа A + B) из mytra.main_afl в story.story_afl и удаляет из main_afl.

    Кросс-БД перенос делаем через ATTACH: main_afl и story_afl оказываются в одном соединении,
    поэтому `INSERT … SELECT` + `DELETE` выполняются атомарно (быстрее и надёжнее, чем
    материализация строк в Python). Возвращает (число строк, список metering_point).
    """
    where = _where_clause()
    params = _base_params(report_str, month_str)
    cols = ", ".join(STORY_AFL_COLUMNS)

    mps = (await main_session.execute(
        text(f"SELECT DISTINCT metering_point FROM main_afl "
             f"WHERE {where} AND metering_point IS NOT NULL AND metering_point != ''"), params)).scalars().all()

    await main_session.execute(text("ATTACH DATABASE :path AS story_db"), {"path": story_db_path})
    try:
        ins = await main_session.execute(
            text(f"INSERT OR IGNORE INTO story_db.story_afl ({cols}) "
                 f"SELECT {cols} FROM main_afl WHERE {where}"), params)
        await main_session.execute(text(f"DELETE FROM main_afl WHERE {where}"), params)
        await main_session.commit()
    except Exception:
        await main_session.rollback()
        raise
    finally:
        await main_session.execute(text("DETACH DATABASE story_db"))
        await main_session.commit()

    return int(ins.rowcount or 0), list(mps)


async def fill_consumers(story_session: AsyncSession, metering_points: list[str]) -> int:
    """Для каждого metering_point берёт самую свежую строку story_afl и апсёртит в consumers."""
    if not metering_points:
        return 0

    upsert_sql = (
        f"INSERT INTO consumers (metering_point, {', '.join(CONSUMER_FIELDS)}) "
        f"VALUES (:mp, {', '.join(':f_' + f for f in CONSUMER_FIELDS)}) "
        f"ON CONFLICT(metering_point) DO UPDATE SET "
        f"{', '.join(f + ' = excluded.' + f for f in CONSUMER_FIELDS)}"
    )

    total = 0
    for i in range(0, len(metering_points), _CHUNK):
        chunk = metering_points[i:i + _CHUNK]
        ph = ", ".join(f":mp{j}" for j in range(len(chunk)))
        params = {f"mp{j}": v for j, v in enumerate(chunk)}

        rows = (await story_session.execute(
            text(
                f"SELECT metering_point, {', '.join(CONSUMER_FIELDS)} FROM ("
                f"SELECT metering_point, {', '.join(CONSUMER_FIELDS)}, "
                f"ROW_NUMBER() OVER (PARTITION BY metering_point "
                f"ORDER BY done_day DESC, created_at DESC, work_end_date DESC) AS rn "
                f"FROM story_afl WHERE metering_point IN ({ph})"
                f") WHERE rn = 1"
            ), params)).fetchall()

        for row in rows:
            d = dict(row._mapping)
            await story_session.execute(
                text(upsert_sql),
                {"mp": d["metering_point"], **{f"f_{f}": d[f] for f in CONSUMER_FIELDS}}
            )
        total += len(rows)

    await story_session.commit()
    return total
