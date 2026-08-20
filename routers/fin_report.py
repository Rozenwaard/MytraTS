import json

from litestar import Router
from litestar.connection import Request
from litestar.enums import RequestEncodingType
from litestar.handlers import get, post
from litestar.params import Body
from litestar.response import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from deps import get_current_user, require_auth
from services.dashboard import DASHBOARD_WORK_TYPES, WORK_TYPE_RATES


def _normal_work_types_clause():
    """IN-условие по «нормальным» видам работ (10 типов дашборда)."""
    names = [f"wt{i}" for i in range(len(DASHBOARD_WORK_TYPES))]
    params = dict(zip(names, DASHBOARD_WORK_TYPES))
    clause = f"task_report IN ({', '.join(':' + n for n in names)})"
    return clause, params


def _locale_expr():
    return "COALESCE((SELECT locale FROM users WHERE users.full_name = main_afl.executor LIMIT 1), '(без локали)')"


async def _card(db_session, where_sql, params, locale_expr):
    """Счётчик + раскладка по locale для одной плашки."""
    total = (await db_session.execute(
        text(f"SELECT COUNT(*) FROM main_afl WHERE {where_sql}"), params)).scalar()
    rows = await db_session.execute(
        text(f"SELECT {locale_expr} AS loc, COUNT(*) AS cnt FROM main_afl WHERE {where_sql} GROUP BY {locale_expr} ORDER BY cnt DESC"),
        params)
    return {"total": total, "by_locale": [{"locale": r[0], "count": r[1]} for r in rows]}


@get("/fin-report", guards=[require_auth])
async def api_fin_report(request: Request, db_session: AsyncSession, period: str = "") -> Response:
    """Финотчёт: плашки + раскладка по видам работ выбранного периода."""
    user = await get_current_user(request, db_session)
    if user.effective_role != "администратор":
        return Response(content=json.dumps({"error": "Нет прав"}, ensure_ascii=False), media_type="application/json", status_code=403)

    wt_clause, wt_params = _normal_work_types_clause()
    locale_expr = _locale_expr()

    cards = {
        "completed": await _card(db_session, "status IN ('Завершено','Закрыто')", {}, locale_expr),
        "without_reestr": await _card(db_session, f"{wt_clause} AND reestr_number IS NULL", wt_params, locale_expr),
        "with_errors": await _card(db_session, f"{wt_clause} AND reestr_number IS NULL AND (errors IS NOT NULL AND errors != '')", wt_params, locale_expr),
        "ready": await _card(db_session, "reestr_number IS NOT NULL AND reestr_number != 'Отклонён'", {}, locale_expr),
    }

    work_types = []
    total_cost = 0.0
    period_fmt = period.strip().replace("-", " ") if period else ""
    if period_fmt:
        rows = await db_session.execute(
            text(f"SELECT task_report, COUNT(*) FROM main_afl WHERE report = :period AND {wt_clause} GROUP BY task_report ORDER BY COUNT(*) DESC"),
            {**wt_params, "period": period_fmt})
        for (tr, cnt) in rows:
            work_types.append({"label": tr, "count": cnt})
            total_cost += WORK_TYPE_RATES.get(tr, 0.0) * (cnt or 0)

    return Response(content=json.dumps({
        "cards": cards,
        "work_types": work_types,
        "total_cost": round(total_cost, 2),
    }, ensure_ascii=False, default=str), media_type="application/json")


@post("/fin-report/add", guards=[require_auth])
async def api_fin_report_add(
    request: Request, db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    """«Добавить в отчёт»: проставляет report = «ГГГГ ММ» строкам с реестром и пустым report."""
    user = await get_current_user(request, db_session)
    if user.effective_role != "администратор":
        return Response(content=json.dumps({"error": "Нет прав"}, ensure_ascii=False), media_type="application/json", status_code=403)

    period = (data.get("period") or "").strip()
    if not period:
        return Response(content=json.dumps({"error": "Выберите период"}, ensure_ascii=False), media_type="application/json", status_code=400)

    period_fmt = period.replace("-", " ")
    result = await db_session.execute(
        text("UPDATE main_afl SET report = :period WHERE reestr_number IS NOT NULL AND reestr_number != 'Отклонён' AND (report IS NULL OR report = '')"),
        {"period": period_fmt})
    await db_session.commit()

    return Response(content=json.dumps({"success": True, "updated": result.rowcount, "period": period_fmt}, ensure_ascii=False), media_type="application/json")


fin_report_router = Router("/api", route_handlers=[api_fin_report, api_fin_report_add])
