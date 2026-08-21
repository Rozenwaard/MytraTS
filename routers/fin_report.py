import io
import json
import zipfile
from urllib.parse import quote

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
from services.reestr import generate_fin_report_xlsx_bytes


def _normal_work_types_clause():
    """IN-условие по «нормальным» видам работ (10 типов дашборда)."""
    names = [f"wt{i}" for i in range(len(DASHBOARD_WORK_TYPES))]
    params = dict(zip(names, DASHBOARD_WORK_TYPES))
    clause = f"task_report IN ({', '.join(':' + n for n in names)})"
    return clause, params


def _locale_expr():
    return "COALESCE((SELECT locale FROM users WHERE users.full_name = main_afl.executor LIMIT 1), '(без локали)')"


def _cost_expr():
    """SQL-выражение стоимости строки: расценка по task_report (0 — если расценки нет)."""
    parts: list[str] = []
    params: dict = {}
    for i, (wt, rate) in enumerate(WORK_TYPE_RATES.items()):
        wt_p = f"cost_wt{i}"
        rate_p = f"cost_rate{i}"
        parts.append(f"WHEN task_report = :{wt_p} THEN :{rate_p}")
        params[wt_p] = wt
        params[rate_p] = rate
    return "CASE " + " ".join(parts) + " ELSE 0 END", params


async def _card(db_session, where_sql, params, locale_expr, cost_expr):
    """Счётчик + раскладка по locale + сумма стоимости для одной плашки."""
    total = (await db_session.execute(
        text(f"SELECT COUNT(*) FROM main_afl WHERE {where_sql}"), params)).scalar()
    rows = await db_session.execute(
        text(f"SELECT {locale_expr} AS loc, COUNT(*) AS cnt FROM main_afl WHERE {where_sql} GROUP BY {locale_expr} ORDER BY cnt DESC"),
        params)
    cost = (await db_session.execute(
        text(f"SELECT COALESCE(SUM({cost_expr}), 0) FROM main_afl WHERE {where_sql}"), params)).scalar()
    return {"total": total, "by_locale": [{"locale": r[0], "count": r[1]} for r in rows], "cost": round(cost or 0, 2)}


@get("/fin-report", guards=[require_auth])
async def api_fin_report(request: Request, db_session: AsyncSession, period: str = "") -> Response:
    """Финотчёт: плашки + раскладка по видам работ выбранного периода."""
    user = await get_current_user(request, db_session)
    if user.effective_role != "администратор":
        return Response(content=json.dumps({"error": "Нет прав"}, ensure_ascii=False), media_type="application/json", status_code=403)

    wt_clause, wt_params = _normal_work_types_clause()
    locale_expr = _locale_expr()
    cost_expr, cost_params = _cost_expr()

    cards = {
        "completed": await _card(db_session, "status IN ('Завершено','Закрыто')", cost_params, locale_expr, cost_expr),
        "without_reestr": await _card(db_session, f"{wt_clause} AND reestr_number IS NULL", {**wt_params, **cost_params}, locale_expr, cost_expr),
        "with_errors": await _card(db_session, f"{wt_clause} AND reestr_number IS NULL AND (errors IS NOT NULL AND errors != '')", {**wt_params, **cost_params}, locale_expr, cost_expr),
        "ready": await _card(db_session, "reestr_number IS NOT NULL AND reestr_number != 'Отклонён'", cost_params, locale_expr, cost_expr),
    }

    work_types = []
    total_cost = 0.0
    cost_psk = 0.0
    cost_rle = 0.0
    period_fmt = period.strip().replace("-", " ") if period else ""
    if period_fmt:
        rows = await db_session.execute(
            text(f"SELECT task_report, COUNT(*) FROM main_afl WHERE report = :period AND {wt_clause} GROUP BY task_report ORDER BY COUNT(*) DESC"),
            {**wt_params, "period": period_fmt})
        for (tr, cnt) in rows:
            work_types.append({"label": tr, "count": cnt})
            total_cost += WORK_TYPE_RATES.get(tr, 0.0) * (cnt or 0)

        cust_rows = await db_session.execute(
            text(f"SELECT customer, COALESCE(SUM({cost_expr}), 0) FROM main_afl WHERE report = :period AND {wt_clause} GROUP BY customer"),
            {**wt_params, **cost_params, "period": period_fmt})
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


@get("/fin-report/download", guards=[require_auth])
async def api_fin_report_download(request: Request, db_session: AsyncSession, period: str = "") -> Response:
    """«Скачать отчёт»: ZIP с двумя xlsx (Плановый/Внеплановый по task_type)."""
    user = await get_current_user(request, db_session)
    if user.effective_role != "администратор":
        return Response(content=json.dumps({"error": "Нет прав"}, ensure_ascii=False), media_type="application/json", status_code=403)

    period_fmt = period.strip().replace("-", " ") if period else ""
    if not period_fmt:
        return Response(content=json.dumps({"error": "Выберите период"}, ensure_ascii=False), media_type="application/json", status_code=400)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for task_type in ("Плановый", "Внеплановый"):
            data = await generate_fin_report_xlsx_bytes(db_session, period_fmt, task_type)
            zf.writestr(f"Отчёт_{period_fmt.replace(' ', '-')}_{task_type}.xlsx", data)
    buf.seek(0)

    filename = f"Отчёт_{period_fmt.replace(' ', '-')}.zip"
    return Response(content=buf.read(), media_type="application/zip",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"})


fin_report_router = Router("/api", route_handlers=[api_fin_report, api_fin_report_add, api_fin_report_download])
