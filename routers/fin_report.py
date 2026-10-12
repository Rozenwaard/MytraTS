import asyncio
import calendar
import io
import json
import uuid
import zipfile
from datetime import datetime
from urllib.parse import quote

from litestar import Router
from litestar.connection import Request
from litestar.datastructures import UploadFile
from litestar.enums import RequestEncodingType
from litestar.handlers import get, post
from litestar.params import Body
from litestar.response import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from data.config import async_session_factory, story_session_factory, STORY_DB_PATH
from deps import get_current_user, require_auth
from services.archive import archive_period_to_story, fill_consumers
from services.dashboard import generate_recheck_xlsx, pick_pu_type
from services.reestr import generate_dop_report_xlsx_bytes, generate_fin_report_xlsx_bytes
from services.report_check import BALANCE_ERRORS, check_row, join_errors, STOP_FACTOR_REGIONS, STOP_FACTOR_DISTRICTS


def _normal_work_types_clause():
    """IN-условие по «нормальным» видам работ (base-тарифы carte + work_catalog)."""
    return ("task_report IN (SELECT title FROM carte WHERE kind = 'base' "
            "UNION SELECT short FROM work_catalog WHERE kind = 'base')"), {}


def _stop_zone_clause():
    """Зона стоп-фактора (как в дашборде): регион СПб + ЛО Гатчинский район."""
    regions = sorted(STOP_FACTOR_REGIONS)
    districts = sorted(STOP_FACTOR_DISTRICTS)
    r_names = [f"zr{i}" for i in range(len(regions))]
    d_names = [f"zd{i}" for i in range(len(districts))]
    params = {**dict(zip(r_names, regions)), **dict(zip(d_names, districts))}
    r_in = ", ".join(f":{n}" for n in r_names)
    d_in = ", ".join(f":{n}" for n in d_names)
    return f"(region IN ({r_in}) OR municipal_district IN ({d_in}))", params


def _locale_expr():
    return f"COALESCE((SELECT locale FROM users WHERE users.executor_name = main_afl.executor LIMIT 1), '(без локали)')"


COST_JOIN = ("LEFT JOIN carte c ON c.title = main_afl.task_report "
             "LEFT JOIN work_catalog wc ON wc.short = main_afl.task_report")
COST_PRICE = "COALESCE(c.price, wc.price, 0)"


def _period_clause(period: str):
    """Область выборки Финотчёта.

    Пустой period («Выберите период») → строки, ещё НЕ включённые в отчёт
    (report пустой) — то есть текущая незакрытая работа.
    Заданный period → строки этого отчётного периода (report = «ГГГГ ММ»).

    Возвращает (clause, period_fmt, params).
    """
    period_fmt = period.strip().replace("-", " ") if period else ""
    if period_fmt:
        return "report = :period", period_fmt, {"period": period_fmt}
    return "(report IS NULL OR report = '')", "", {}


def _period_end(period: str) -> str:
    """Последний день выбранного периода 'ГГГГ-ММ' в виде 'ГГГГ-ММ-ДД'.

    Нужен для фильтра done_day <= конец периода (done_day хранится как
    'ГГГГ-ММ-ДД', поэтому сравнение строками корректно).
    """
    year, month = (int(x) for x in period.strip().split("-"))
    return f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"


async def _next_period(db_session: AsyncSession) -> str:
    """Следующий отчётный период после последнего в main_afl (формат 'ГГГГ ММ')."""
    result = await db_session.execute(
        text("SELECT MAX(report) FROM main_afl WHERE report GLOB '[0-9][0-9][0-9][0-9] [0-9][0-9]'"))
    latest = result.scalar()
    if latest:
        year, month = (int(x) for x in latest.split(" "))
        month += 1
        if month > 12:
            year += 1
            month = 1
        return f"{year:04d} {month:02d}"
    now = datetime.now()
    return f"{now.year:04d} {now.month:02d}"


async def _card(db_session, where_sql, params, locale_expr):
    """Счётчик + раскладка по locale + сумма стоимости для одной плашки."""
    total = (await db_session.execute(
        text(f"SELECT COUNT(*) FROM main_afl WHERE {where_sql}"), params)).scalar()
    rows = await db_session.execute(
        text(f"SELECT {locale_expr} AS loc, COUNT(*) AS cnt FROM main_afl WHERE {where_sql} GROUP BY {locale_expr} ORDER BY cnt DESC"),
        params)
    cost = (await db_session.execute(
        text(f"SELECT COALESCE(SUM({COST_PRICE}), 0) FROM main_afl {COST_JOIN} WHERE {where_sql}"), params)).scalar()
    return {"total": total, "by_locale": [{"locale": r[0], "count": r[1]} for r in rows], "cost": round(cost or 0, 2)}


async def _story_work_types(period_fmt: str, wt_clause: str, wt_params: dict):
    """Раскладка по видам работ + стоимость для архивного периода (из story_afl)."""
    async with async_session_factory() as main_session:
        await main_session.execute(text("ATTACH DATABASE :path AS story_db"), {"path": STORY_DB_PATH})
        try:
            rows = await main_session.execute(text(
                f"SELECT s.task_report, COUNT(*), COALESCE(c.price, wc.price, 0) AS price "
                f"FROM story_db.story_afl AS s "
                f"LEFT JOIN carte c ON c.title = s.task_report "
                f"LEFT JOIN work_catalog wc ON wc.short = s.task_report "
                f"WHERE s.report = :p AND s.status IN ('Завершено','Закрыто') AND {wt_clause} "
                f"GROUP BY s.task_report ORDER BY COUNT(*) DESC"
            ), {**wt_params, "p": period_fmt})
            work_types = []
            total_cost = 0.0
            for (tr, cnt, price) in rows:
                work_types.append({"label": tr, "count": cnt})
                total_cost += (price or 0.0) * (cnt or 0)

            cust_rows = await main_session.execute(text(
                f"SELECT s.customer, COALESCE(SUM(COALESCE(c.price, wc.price, 0)), 0) "
                f"FROM story_db.story_afl AS s "
                f"LEFT JOIN carte c ON c.title = s.task_report "
                f"LEFT JOIN work_catalog wc ON wc.short = s.task_report "
                f"WHERE s.report = :p AND s.status IN ('Завершено','Закрыто') AND {wt_clause} "
                f"GROUP BY s.customer"
            ), {**wt_params, "p": period_fmt})
            cost_by_cust = {r[0]: (r[1] or 0) for r in cust_rows}
        finally:
            await main_session.execute(text("DETACH DATABASE story_db"))
            await main_session.commit()

    return (
        work_types,
        round(total_cost, 2),
        round(cost_by_cust.get("ПСК", 0), 2),
        round(cost_by_cust.get("РЛЭ", 0), 2),
    )


@get("/fin-report", guards=[require_auth])
async def api_fin_report(request: Request, db_session: AsyncSession, period: str = "") -> Response:
    """Финотчёт: плашки + раскладка по видам работ в выбранной области.

    Без period — всё, что ещё не в отчёте; с period — данные этого отчётного периода
    (для архивного периода — из story_afl).
    """
    user = await get_current_user(request, db_session)
    if user.effective_role != "администратор":
        return Response(content=json.dumps({"error": "Нет прав"}, ensure_ascii=False), media_type="application/json", status_code=403)

    wt_clause, wt_params = _normal_work_types_clause()
    zone_clause, zone_params = _stop_zone_clause()
    locale_expr = _locale_expr()
    period_for_clause = period
    archived = False
    if period:
        period_fmt = period.strip().replace("-", " ")
        has_report = (await db_session.execute(
            text("SELECT COUNT(*) FROM main_afl WHERE report = :p"), {"p": period_fmt})).scalar()
        if not has_report:
            async with story_session_factory() as story_session:
                archived = (await story_session.execute(
                    text("SELECT COUNT(*) FROM story_afl WHERE report = :p"), {"p": period_fmt})).scalar() > 0
            period_for_clause = period if archived else ""

    if archived:
        work_types, total_cost, cost_psk, cost_rle = await _story_work_types(period_fmt, wt_clause, wt_params)
        cards = {
            "completed": {"total": 0, "by_locale": [], "cost": 0},
            "without_reestr": {"total": 0, "by_locale": [], "cost": 0},
            "with_errors": {"total": 0, "by_locale": [], "cost": 0},
            "ready": {"total": 0, "by_locale": [], "cost": 0},
        }
    else:
        p_clause, _period_fmt, p_params = _period_clause(period_for_clause)
        base = {**p_params}
        base_wt = {**base, **wt_params}

        cards = {
            "completed": await _card(db_session, f"{p_clause} AND status IN ('Завершено','Закрыто')", base, locale_expr),
            "without_reestr": await _card(db_session, f"{p_clause} AND status IN ('Завершено','Закрыто') AND {wt_clause} AND reestr_number IS NULL", base_wt, locale_expr),
            "with_errors": await _card(db_session, f"{p_clause} AND status IN ('Завершено','Закрыто') AND {wt_clause} AND reestr_number IS NULL AND (errors IS NOT NULL AND errors != '') AND {zone_clause}", {**base_wt, **zone_params}, locale_expr),
            "ready": await _card(db_session, f"{p_clause} AND status IN ('Завершено','Закрыто') AND reestr_number IS NOT NULL AND reestr_number != 'Отклонён'", base, locale_expr),
        }

        work_types = []
        total_cost = 0.0
        rows = await db_session.execute(
            text(f"SELECT task_report, COUNT(*), {COST_PRICE} AS price FROM main_afl {COST_JOIN} WHERE {p_clause} AND status IN ('Завершено','Закрыто') AND {wt_clause} GROUP BY task_report ORDER BY COUNT(*) DESC"),
            {**wt_params, **p_params})
        for (tr, cnt, price) in rows:
            work_types.append({"label": tr, "count": cnt})
            total_cost += (price or 0.0) * (cnt or 0)

        cust_rows = await db_session.execute(
            text(f"SELECT main_afl.customer, COALESCE(SUM({COST_PRICE}), 0) FROM main_afl {COST_JOIN} WHERE {p_clause} AND status IN ('Завершено','Закрыто') AND {wt_clause} GROUP BY main_afl.customer"),
            {**wt_params, **p_params})
        cost_by_cust = {r[0]: (r[1] or 0) for r in cust_rows}
        cost_psk = round(cost_by_cust.get("ПСК", 0), 2)
        cost_rle = round(cost_by_cust.get("РЛЭ", 0), 2)

    return Response(content=json.dumps({
        "cards": cards,
        "work_types": work_types,
        "total_cost": round(total_cost, 2),
        "cost_psk": cost_psk,
        "cost_rle": cost_rle,
    }, ensure_ascii=False, default=str), media_type="application/json")


@get("/fin-report/periods", guards=[require_auth])
async def api_fin_report_periods(request: Request, db_session: AsyncSession) -> Response:
    """Карусель периодов Финотчёта.

    Месяцы от первого отчёта до «фронтира» — следующего отчётного периода после
    последнего в main_afl (будущий месяц включается как заблокированная плашка,
    can_form = False), максимум 6. default — фронтир. has_rows — есть ли строки в
    main_afl с done_day в этом месяце.
    """
    user = await get_current_user(request, db_session)
    if user.effective_role != "администратор":
        return Response(content=json.dumps({"error": "Нет прав"}, ensure_ascii=False), media_type="application/json", status_code=403)

    row = (await db_session.execute(
        text("SELECT MIN(report), MAX(report) FROM main_afl WHERE report GLOB '[0-9][0-9][0-9][0-9] [0-9][0-9]'"))).one()
    first_unarchived, last_report = row[0], row[1]

    # Архивные месяцы (story_afl) — чтобы карусель не съезжала при архивации.
    async with story_session_factory() as story_session:
        first_report_story = (await story_session.execute(
            text("SELECT MIN(report) FROM story_afl WHERE report GLOB '[0-9][0-9][0-9][0-9] [0-9][0-9]'"))).scalar()
        archived = set((await story_session.execute(
            text("SELECT DISTINCT report FROM story_afl WHERE report GLOB '[0-9][0-9][0-9][0-9] [0-9][0-9]'"))).scalars().all())

    # Самый первый отчёт системы — минимум по main_afl и story_afl.
    first_report = first_unarchived
    if first_report_story and (not first_report or first_report_story < first_report):
        first_report = first_report_story

    def _ym(s: str):
        return tuple(int(x) for x in s.split(" "))

    def _add(y: int, m: int, d: int):
        m += d
        while m < 1:
            m += 12
            y -= 1
        while m > 12:
            m -= 12
            y += 1
        return y, m

    next_period = await _next_period(db_session)  # 'ГГГГ ММ'
    ny, nm = _ym(next_period)

    now = datetime.now()
    # Фронтир — следующий отчётный период после последнего в main_afl. Не ограничиваем
    # текущим календарным месяцем: после «Сформировать отчёт» за текущий месяц фронтир
    # уходит на следующий (будущий) месяц, и в карусели появляется его плашка.
    frontier = (ny, nm)
    # Окно максимум 6: самая старая неархивированная плашка остаётся в карусели
    # (фронтир не уходит дальше first_unarchived + 5).
    if first_unarchived:
        cap = _add(*_ym(first_unarchived), 5)
        frontier = min(frontier, cap)
    fy, fm = frontier

    if first_report:
        py, pm = _ym(first_report)
        n = (fy - py) * 12 + (fm - pm) + 1
        # Сбрасываем архивные месяцы из начала окна, пока больше 6.
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
        periods.append({"value": value, "has_rows": has_rows, "is_current": value == default, "is_archived": is_archived, "category": category, "can_form": can_form})
        m -= 1
        if m == 0:
            m = 12
            y -= 1

    return Response(content=json.dumps({
        "periods": periods,
        "default": default,
    }, ensure_ascii=False), media_type="application/json")


_DEPTS_SQL = (
    "SELECT COALESCE(t.executor_organization, '(без отделения)') AS org, "
    "COUNT(*) AS total, "
    "COALESCE(SUM(CASE WHEN t.reestr_number IS NOT NULL AND t.reestr_number != '' AND t.reestr_number != 'Отклонён' THEN 1 ELSE 0 END), 0) AS successful, "
    "COALESCE(SUM(COALESCE(c.price, wc.price, 0)), 0) AS cost "
    "FROM {table} AS t "
    "LEFT JOIN carte c ON c.title = t.task_report "
    "LEFT JOIN work_catalog wc ON wc.short = t.task_report "
    "WHERE {where} GROUP BY org ORDER BY org"
)


async def _depts_rows(session, table: str, where_clause: str, params: dict) -> list:
    rows = (await session.execute(text(_DEPTS_SQL.format(table=table, where=where_clause)), params)).fetchall()
    return [{"org": r[0], "total": r[1], "successful": r[2], "unsuccessful": r[1] - r[2], "done": 0, "nedopusk": 0, "not_closed": 0, "sum": round(r[3] or 0, 2)} for r in rows]


_DEPTS_UNFORMED_SQL = (
    "SELECT COALESCE(t.executor_organization, '(без отделения)') AS org, "
    "COALESCE(SUM(CASE WHEN t.task_report IS NOT NULL AND t.task_report != '' THEN 1 ELSE 0 END), 0) AS done, "
    "COALESCE(SUM(CASE WHEN t.task_report LIKE 'Недопуск%' THEN 1 ELSE 0 END), 0) AS nedopusk, "
    "COALESCE(SUM(CASE WHEN t.task_report IS NOT NULL AND t.task_report != '' "
    "AND NOT (t.reestr_number IS NOT NULL AND t.reestr_number != '' AND t.reestr_number != 'Отклонён') THEN 1 ELSE 0 END), 0) AS not_closed, "
    "COALESCE(SUM(COALESCE(c.price, wc.price, 0)), 0) AS cost "
    "FROM main_afl AS t "
    "LEFT JOIN carte c ON c.title = t.task_report "
    "LEFT JOIN work_catalog wc ON wc.short = t.task_report "
    "WHERE (t.report IS NULL OR t.report = '') GROUP BY org ORDER BY org"
)


async def _depts_rows_unformed(session) -> list:
    rows = (await session.execute(text(_DEPTS_UNFORMED_SQL))).fetchall()
    # Отбрасываем отделения без выполненных работ (строка «0 0 0,00 ₽»).
    return [{"org": r[0], "total": 0, "successful": 0, "unsuccessful": 0, "done": r[1], "nedopusk": r[2], "not_closed": r[3], "sum": round(r[4] or 0, 2)} for r in rows if r[1]]


def _report_total(result: list) -> dict:
    t = sum(r["total"] for r in result)
    s = sum(r["successful"] for r in result)
    c = sum(r["sum"] for r in result)
    return {"org": "Итого", "total": t, "successful": s, "unsuccessful": t - s, "done": 0, "nedopusk": 0, "not_closed": 0, "sum": round(c, 2)}


def _unformed_total(result: list) -> dict:
    d = sum(r["done"] for r in result)
    nd = sum(r["nedopusk"] for r in result)
    n = sum(r["not_closed"] for r in result)
    c = sum(r["sum"] for r in result)
    return {"org": "Итого", "total": 0, "successful": 0, "unsuccessful": 0, "done": d, "nedopusk": nd, "not_closed": n, "sum": round(c, 2)}


@get("/fin-report/depts", guards=[require_auth])
async def api_fin_report_depts(request: Request, db_session: AsyncSession, period: str = "") -> Response:
    """Статистика по отделениям. Архивный период — по story_afl; месяц без сформированного
    отчёта (текущий/фронтир) — по строкам ещё не в отчёте (report пустой)."""
    user = await get_current_user(request, db_session)
    if user.effective_role != "администратор":
        return Response(content=json.dumps({"error": "Нет прав"}, ensure_ascii=False), media_type="application/json", status_code=403)
    if not period:
        empty = {"org": "", "total": 0, "successful": 0, "unsuccessful": 0, "done": 0, "nedopusk": 0, "not_closed": 0, "sum": 0}
        return Response(content=json.dumps({"rows": [], "total": empty}, ensure_ascii=False), media_type="application/json")
    period_fmt = period.strip().replace("-", " ")
    has_report = (await db_session.execute(
        text("SELECT COUNT(*) FROM main_afl WHERE report = :p"), {"p": period_fmt})).scalar()
    if has_report:
        result = await _depts_rows(db_session, "main_afl", "t.report = :p", {"p": period_fmt})
        total_row = _report_total(result)
    else:
        async with story_session_factory() as story_session:
            archived_count = (await story_session.execute(
                text("SELECT COUNT(*) FROM story_afl WHERE report = :p"), {"p": period_fmt})).scalar()
        if archived_count:
            async with async_session_factory() as main_session:
                await main_session.execute(text("ATTACH DATABASE :path AS story_db"), {"path": STORY_DB_PATH})
                try:
                    result = await _depts_rows(main_session, "story_db.story_afl", "t.report = :p", {"p": period_fmt})
                finally:
                    await main_session.execute(text("DETACH DATABASE story_db"))
                    await main_session.commit()
            total_row = _report_total(result)
        else:
            result = await _depts_rows_unformed(db_session)
            total_row = _unformed_total(result)
    return Response(content=json.dumps({"rows": result, "total": total_row}, ensure_ascii=False), media_type="application/json")


@post("/fin-report/supplement", guards=[require_auth])
async def api_fin_report_supplement(
    request: Request, db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    """«Дополнить отчёт»: строки вне отчёта + done_day ≤ конца периода + правильный номер реестра → report = период."""
    user = await get_current_user(request, db_session)
    if user.effective_role != "администратор":
        return Response(content=json.dumps({"success": False, "error": "Нет прав"}, ensure_ascii=False), media_type="application/json", status_code=403)
    period = (data.get("period") or "").strip()
    customer = (data.get("customer") or "").strip()
    if not period:
        return Response(content=json.dumps({"success": False, "error": "Не выбран период"}, ensure_ascii=False), media_type="application/json")
    period_fmt = period.replace("-", " ")
    period_end = _period_end(period)
    clause = ("UPDATE main_afl SET report = :period WHERE (report IS NULL OR report = '') "
              "AND done_day IS NOT NULL AND done_day <= :period_end "
              "AND reestr_number IS NOT NULL AND reestr_number != '' AND reestr_number != 'Отклонён'")
    params = {"period": period_fmt, "period_end": period_end}
    if customer:
        clause += " AND customer = :customer"
        params["customer"] = customer
    result = await db_session.execute(text(clause), params)
    await db_session.commit()
    return Response(content=json.dumps({"success": True, "updated": result.rowcount}, ensure_ascii=False), media_type="application/json")


@get("/fin-report/supplement-sum", guards=[require_auth])
async def api_fin_report_supplement_sum(request: Request, db_session: AsyncSession, period: str = "") -> Response:
    """Сумма, на которую может вырасти отчёт при «Дополнить отчёт»."""
    user = await get_current_user(request, db_session)
    if user.effective_role != "администратор":
        return Response(content=json.dumps({"error": "Нет прав"}, ensure_ascii=False), media_type="application/json", status_code=403)
    if not period:
        return Response(content=json.dumps({"psk": 0, "rle": 0}, ensure_ascii=False), media_type="application/json")
    period_end = _period_end(period.strip())
    rows = (await db_session.execute(
        text("SELECT main_afl.customer, COALESCE(SUM(COALESCE(c.price, wc.price, 0)), 0) "
             "FROM main_afl "
             "LEFT JOIN carte c ON c.title = main_afl.task_report "
             "LEFT JOIN work_catalog wc ON wc.short = main_afl.task_report "
             "WHERE (report IS NULL OR report = '') AND done_day IS NOT NULL AND done_day <= :period_end "
             "AND reestr_number IS NOT NULL AND reestr_number != '' AND reestr_number != 'Отклонён' "
             "GROUP BY main_afl.customer"),
        {"period_end": period_end})).fetchall()
    cost_by_cust = {r[0]: round(r[1] or 0, 2) for r in rows}
    return Response(content=json.dumps({"psk": cost_by_cust.get("ПСК", 0), "rle": cost_by_cust.get("РЛЭ", 0)}, ensure_ascii=False), media_type="application/json")


archive_progress: dict = {}


@post("/fin-report/archive", guards=[require_auth])
async def api_fin_report_archive(
    request: Request, db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    """«Отправить в архив»: переносит строки периода из main_afl в story_afl (в фоне)."""
    user = await get_current_user(request, db_session)
    if user.effective_role != "администратор":
        return Response(content=json.dumps({"success": False, "error": "Нет прав"}, ensure_ascii=False), media_type="application/json", status_code=403)
    period = (data.get("period") or "").strip()
    if not period:
        return Response(content=json.dumps({"success": False, "error": "Не выбран период"}, ensure_ascii=False), media_type="application/json")
    period_fmt = period.replace("-", " ")
    archive_id = uuid.uuid4().hex
    archive_progress[archive_id] = {"status": "starting", "moved": 0, "consumers": 0}
    asyncio.create_task(_run_archive(archive_id, period_fmt))
    return Response(content=json.dumps({"archive_id": archive_id}, ensure_ascii=False), media_type="application/json")


@get("/fin-report/archive/progress/{archive_id:str}", guards=[require_auth])
async def api_fin_report_archive_progress(archive_id: str) -> Response:
    if archive_id not in archive_progress:
        return Response(content=json.dumps({"status": "not_found"}, ensure_ascii=False), media_type="application/json", status_code=404)
    return Response(content=json.dumps(archive_progress[archive_id], ensure_ascii=False), media_type="application/json")


async def _run_archive(archive_id: str, period_fmt: str):
    try:
        archive_progress[archive_id] = {"status": "moving", "moved": 0, "consumers": 0}
        async with async_session_factory() as main_session:
            moved, metering_points = await archive_period_to_story(main_session, period_fmt)
        archive_progress[archive_id] = {"status": "consumers", "moved": moved, "consumers": 0}
        filled = 0
        try:
            async with story_session_factory() as story_session:
                filled = await fill_consumers(story_session, metering_points)
        except Exception:
            import traceback
            traceback.print_exc()
        archive_progress[archive_id] = {"status": "complete", "moved": moved, "consumers": filled}
    except Exception as e:
        import traceback
        traceback.print_exc()
        archive_progress[archive_id] = {"status": "error", "moved": 0, "consumers": 0, "message": str(e)}


@post("/fin-report/add", guards=[require_auth])
async def api_fin_report_add(
    request: Request, db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    """«Сформировать отчёт»: report = «ГГГГ ММ».

    С выбранным периодом — все строки с правильным номером реестра (не «Отклонён»),
    пустым report и done_day не новее конца периода (пустой done_day не попадает).
    Без периода — строки с правильным номером реестра (пустой report) уходят в
    следующий отчётный период после последнего в main_afl.
    """
    user = await get_current_user(request, db_session)
    if user.effective_role != "администратор":
        return Response(content=json.dumps({"error": "Нет прав"}, ensure_ascii=False), media_type="application/json", status_code=403)

    period = (data.get("period") or "").strip()
    if period:
        period_fmt = period.replace("-", " ")
        period_end = _period_end(period)
        result = await db_session.execute(
            text("UPDATE main_afl SET report = :period WHERE reestr_number IS NOT NULL AND reestr_number != '' AND reestr_number != 'Отклонён' AND (report IS NULL OR report = '') AND done_day IS NOT NULL AND done_day <= :period_end"),
            {"period": period_fmt, "period_end": period_end})
    else:
        period_fmt = await _next_period(db_session)
        result = await db_session.execute(
            text("UPDATE main_afl SET report = :period WHERE reestr_number IS NOT NULL AND reestr_number != '' AND reestr_number != 'Отклонён' AND (report IS NULL OR report = '')"),
            {"period": period_fmt})
    await db_session.commit()

    return Response(content=json.dumps({"success": True, "updated": result.rowcount, "period": period_fmt}, ensure_ascii=False), media_type="application/json")


@post("/fin-report/discrepancies", guards=[require_auth])
async def api_fin_report_discrepancies(
    request: Request, db_session: AsyncSession,
    data: UploadFile = Body(media_type=RequestEncodingType.MULTI_PART),
) -> Response:
    """«Разногласия»: txt с номерами заданий (по одному на строку).

    Для найденных по task_number строк сбрасывает их в неисполненные:
    task_report = NULL, task_detail = 'Разногласия', reestr_number = 'Отклонён',
    reestr_date = NULL, report = NULL, norm = NULL, extra = NULL.
    """
    user = await get_current_user(request, db_session)
    if user.effective_role != "администратор":
        return Response(content=json.dumps({"error": "Нет прав"}, ensure_ascii=False), media_type="application/json", status_code=403)

    if not data or not data.filename.lower().endswith(".txt"):
        return Response(content=json.dumps({"error": "Нужен файл .txt"}, ensure_ascii=False), media_type="application/json", status_code=400)

    raw = await data.read()
    text_content = None
    for enc in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            text_content = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text_content is None:
        return Response(content=json.dumps({"error": "Не удалось прочитать txt (кодировка)"}, ensure_ascii=False), media_type="application/json", status_code=400)

    numbers = [line.strip() for line in text_content.splitlines() if line.strip()]
    if not numbers:
        return Response(content=json.dumps({"error": "Файл пуст"}, ensure_ascii=False), media_type="application/json", status_code=400)

    # Уникальные номера в порядке появления (дубли в файле не считаем дважды).
    unique = list(dict.fromkeys(numbers))

    batch_id = uuid.uuid4().hex
    snapshot = {}
    updated = 0
    not_found = 0

    for tn in unique:
        before = await db_session.execute(
            text("SELECT task_report, task_detail, reestr_number, reestr_date, report, norm, extra FROM main_afl WHERE task_number = :tn"),
            {"tn": tn},
        )
        row = before.mappings().first()
        if row is None:
            not_found += 1
            continue

        # Снимок «до» — для возможности отката.
        snapshot[tn] = dict(row)

        await db_session.execute(
            text("UPDATE main_afl SET task_report = NULL, task_detail = 'Разногласия', reestr_number = 'Отклонён', reestr_date = NULL, report = NULL, norm = NULL, extra = NULL WHERE task_number = :tn"),
            {"tn": tn},
        )
        updated += 1

    if snapshot:
        await db_session.execute(
            text("INSERT INTO discrepancies_log (batch_id, payload, created_at) VALUES (:batch_id, :payload, :created_at)"),
            {"batch_id": batch_id, "payload": json.dumps(snapshot, ensure_ascii=False), "created_at": datetime.now().isoformat(timespec="seconds")},
        )

    await db_session.commit()

    return Response(content=json.dumps({"success": True, "updated": updated, "not_found": not_found, "batch_id": batch_id}, ensure_ascii=False), media_type="application/json")


@post("/fin-report/discrepancies/rollback", guards=[require_auth])
async def api_fin_report_discrepancies_rollback(
    request: Request, db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    """«Откат разногласий»: возвращает значения, сброшенные операцией «Разногласия».

    Восстанавливает task_report/task_detail/reestr_number/reestr_date/report/norm/extra
    для строк из последнего (или указанного batch_id) снимка. Одноразовый: снимок удаляется.
    """
    user = await get_current_user(request, db_session)
    if user.effective_role != "администратор":
        return Response(content=json.dumps({"error": "Нет прав"}, ensure_ascii=False), media_type="application/json", status_code=403)

    batch_id = (data or {}).get("batch_id")

    if batch_id:
        log = await db_session.execute(
            text("SELECT id, payload FROM discrepancies_log WHERE batch_id = :batch_id ORDER BY id DESC LIMIT 1"),
            {"batch_id": batch_id},
        )
    else:
        log = await db_session.execute(
            text("SELECT id, payload FROM discrepancies_log ORDER BY id DESC LIMIT 1"),
        )

    row = log.mappings().first()
    if row is None:
        return Response(content=json.dumps({"error": "Нет снимка для отката"}, ensure_ascii=False), media_type="application/json", status_code=404)

    snapshot = json.loads(row["payload"])
    restored = 0
    for tn, prev in snapshot.items():
        await db_session.execute(
            text(
                "UPDATE main_afl SET task_report = :task_report, task_detail = :task_detail, "
                "reestr_number = :reestr_number, reestr_date = :reestr_date, report = :report, "
                "norm = :norm, extra = :extra WHERE task_number = :tn"
            ),
            {
                "tn": tn,
                "task_report": prev.get("task_report"),
                "task_detail": prev.get("task_detail"),
                "reestr_number": prev.get("reestr_number"),
                "reestr_date": prev.get("reestr_date"),
                "report": prev.get("report"),
                "norm": prev.get("norm"),
                "extra": prev.get("extra"),
            },
        )
        restored += 1

    await db_session.execute(text("DELETE FROM discrepancies_log WHERE id = :id"), {"id": row["id"]})
    await db_session.commit()

    return Response(content=json.dumps({"success": True, "restored": restored}, ensure_ascii=False), media_type="application/json")


@post("/fin-report/discrepancies/discard", guards=[require_auth])
async def api_fin_report_discrepancies_discard(
    request: Request, db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    """«Сохранить» после «Разногласий»: выбрасывает снимок отката (изменения остаются).

    Удаляет строку discrepancies_log для batch_id — откат становится недоступен.
    """
    user = await get_current_user(request, db_session)
    if user.effective_role != "администратор":
        return Response(content=json.dumps({"error": "Нет прав"}, ensure_ascii=False), media_type="application/json", status_code=403)

    batch_id = (data or {}).get("batch_id")
    if not batch_id:
        return Response(content=json.dumps({"error": "Нет batch_id"}, ensure_ascii=False), media_type="application/json", status_code=400)

    await db_session.execute(text("DELETE FROM discrepancies_log WHERE batch_id = :batch_id"), {"batch_id": batch_id})
    await db_session.commit()

    return Response(content=json.dumps({"success": True}, ensure_ascii=False), media_type="application/json")


@post("/fin-report/recheck", guards=[require_auth])
async def api_fin_report_recheck(
    request: Request, db_session: AsyncSession,
    data: UploadFile = Body(media_type=RequestEncodingType.MULTI_PART),
) -> Response:
    """«Повторная проверка»: txt с номерами заданий (по одному на строку).

    Для найденных строк: report/reestr_number/reestr_date = NULL + пересчёт ошибок по общим
    правилам БЕЗ ограничений. Возвращает xlsx: «Ошибки» (номер/ошибки/комментарий),
    «Балансовая принадлежность» (номер/тип/комментарий), «Дата работ» (номер/комментарий).
    Комментарий = «Отправлено в билинг» или «Закрыто» (или пусто).
    """
    user = await get_current_user(request, db_session)
    if user.effective_role != "администратор":
        return Response(content=json.dumps({"error": "Нет прав"}, ensure_ascii=False), media_type="application/json", status_code=403)

    if not data or not data.filename.lower().endswith(".txt"):
        return Response(content=json.dumps({"error": "Нужен файл .txt"}, ensure_ascii=False), media_type="application/json", status_code=400)

    raw = await data.read()
    text_content = None
    for enc in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            text_content = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text_content is None:
        return Response(content=json.dumps({"error": "Не удалось прочитать txt (кодировка)"}, ensure_ascii=False), media_type="application/json", status_code=400)

    numbers = [line.strip() for line in text_content.splitlines() if line.strip()]
    if not numbers:
        return Response(content=json.dumps({"error": "Файл пуст"}, ensure_ascii=False), media_type="application/json", status_code=400)

    updates = []
    report_rows = []
    balance_rows = []
    date_rows = []
    not_found = 0
    for tn in numbers:
        result = await db_session.execute(text("SELECT * FROM main_afl WHERE task_number = :tn"), {"tn": tn})
        row = result.fetchone()
        if row is None:
            not_found += 1
            continue
        row = dict(row._mapping)
        errors = check_row(row)
        updates.append({"e": join_errors(errors), "tn": tn})

        # Признак для колонки «Комментарий» во всех вкладках.
        comment = ""
        if row.get("sent_to_billing") == "Да":
            comment = "Отправлено в билинг"
        elif row.get("status") == "Закрыто":
            comment = "Закрыто"

        general = []
        has_balance = False
        has_date = False
        for e in errors:
            if e in BALANCE_ERRORS:
                has_balance = True
            elif e == "Дата работ":
                has_date = True
            else:
                general.append(e)

        if general:
            report_rows.append((tn, join_errors(general), comment))
        if has_balance:
            pu_type = pick_pu_type(row.get("meter_type_2"), row.get("meter_type_1"), row.get("meter_type"))
            balance_rows.append((tn, pu_type, comment))
        if has_date:
            date_rows.append((tn, comment))

    if updates:
        await db_session.execute(
            text("UPDATE main_afl SET report = NULL, reestr_number = NULL, reestr_date = NULL, errors = :e WHERE task_number = :tn"),
            updates,
        )
    await db_session.commit()

    output = generate_recheck_xlsx(report_rows, balance_rows, date_rows)
    filename = f"Повторная_проверка_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.xlsx"
    return Response(
        content=output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "X-Updated": str(len(updates)),
            "X-Not-Found": str(not_found),
        },
    )


download_progress: dict[str, dict] = {}
download_results: dict[str, bytes] = {}


@post("/fin-report/download", guards=[require_auth])
async def api_fin_report_download_start(request: Request, db_session: AsyncSession, data: dict = Body(media_type=RequestEncodingType.JSON)) -> Response:
    """Старт генерации отчёта: возвращает download_id, файлы собираются в фоне."""
    user = await get_current_user(request, db_session)
    if user.effective_role != "администратор":
        return Response(content=json.dumps({"error": "Нет прав"}, ensure_ascii=False), media_type="application/json", status_code=403)

    period = (data or {}).get("period", "")
    period_fmt = period.strip().replace("-", " ") if period else ""
    if not period_fmt:
        return Response(content=json.dumps({"error": "Выберите период"}, ensure_ascii=False), media_type="application/json", status_code=400)

    download_id = str(uuid.uuid4())
    download_progress[download_id] = {"status": "starting", "done": 0, "total": 6, "progress": 0}
    asyncio.create_task(_run_download(download_id, period_fmt))
    return Response(content=json.dumps({"download_id": download_id}, ensure_ascii=False), media_type="application/json")


@get("/fin-report/download/progress/{download_id:str}", guards=[require_auth])
async def api_fin_report_download_progress(download_id: str) -> Response:
    if download_id not in download_progress:
        return Response(content=json.dumps({"status": "not_found"}, ensure_ascii=False), media_type="application/json", status_code=404)
    return Response(content=json.dumps(download_progress[download_id], ensure_ascii=False), media_type="application/json")


@get("/fin-report/download/result/{download_id:str}", guards=[require_auth])
async def api_fin_report_download_result(download_id: str) -> Response:
    data = download_results.pop(download_id, None)
    if data is None:
        return Response(content=json.dumps({"error": "Ещё не готово"}, ensure_ascii=False), media_type="application/json", status_code=404)
    meta = download_progress.pop(download_id, {})
    filename = meta.get("filename", "Отчёт.zip")
    return Response(content=data, media_type="application/zip",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"})


async def _run_download(download_id: str, period_fmt: str):
    from data.config import async_session_factory
    try:
        async with async_session_factory() as db_session:
            period_tag = period_fmt.replace(" ", "-")
            detail_files = [
                ("Плановый", "СПб", "спбплан"),
                ("Плановый", "ЛО", "лоплан"),
                ("Внеплановый", "СПб", "спбвнеплан"),
                ("Внеплановый", "ЛО", "ловнеплан"),
            ]
            total = 6
            done = 0
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for task_type, region, name in detail_files:
                    data = await generate_fin_report_xlsx_bytes(db_session, period_fmt, task_type, region)
                    zf.writestr(f"Отчёт_{period_tag}_{name}.xlsx", data)
                    done += 1
                    download_progress[download_id] = {"status": "generating", "done": done, "total": total, "progress": int(done / total * 100)}

                for region, name in (("СПб", "спб"), ("ЛО", "ло")):
                    data = await generate_dop_report_xlsx_bytes(db_session, period_fmt, region)
                    zf.writestr(f"Допотчёт_{period_tag}_{name}.xlsx", data)
                    done += 1
                    download_progress[download_id] = {"status": "generating", "done": done, "total": total, "progress": int(done / total * 100)}

            buf.seek(0)
            filename = f"Отчёт_{period_tag}.zip"
            download_results[download_id] = buf.read()
            download_progress[download_id] = {"status": "complete", "done": total, "total": total, "progress": 100, "filename": filename}
    except Exception as e:
        import traceback
        traceback.print_exc()
        download_progress[download_id] = {"status": "error", "done": 0, "total": 6, "progress": 0, "message": str(e)}


fin_report_router = Router("/api", route_handlers=[
    api_fin_report, api_fin_report_periods, api_fin_report_depts, api_fin_report_archive, api_fin_report_archive_progress, api_fin_report_supplement, api_fin_report_supplement_sum, api_fin_report_add, api_fin_report_discrepancies, api_fin_report_discrepancies_rollback, api_fin_report_discrepancies_discard, api_fin_report_recheck,
    api_fin_report_download_start, api_fin_report_download_progress, api_fin_report_download_result,
])
