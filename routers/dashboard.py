import json
from collections import Counter
from datetime import datetime
from urllib.parse import quote

from litestar import Router
from litestar.connection import Request
from litestar.handlers import get
from litestar.response import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from deps import get_current_user, require_auth
from services.dashboard import build_scope, generate_errors_xlsx, generate_balance_xlsx, generate_task_numbers_xlsx, pick_pu_type
from services.report_check import split_errors


@get("/dashboard/summary", guards=[require_auth])
async def api_dashboard_summary(request: Request, db_session: AsyncSession, dept: str = "") -> Response:
    user = await get_current_user(request, db_session)
    clauses, params = build_scope(user, dept)
    zone_where = " AND ".join(clauses)

    total_rows = (await db_session.execute(
        text(f"SELECT COUNT(*) FROM main_afl WHERE {zone_where}"), params)).scalar()

    err_clauses = clauses + ["(errors IS NOT NULL AND errors != '')"]
    err_where = " AND ".join(err_clauses)
    with_errors = (await db_session.execute(
        text(f"SELECT COUNT(*) FROM main_afl WHERE {err_where}"), params)).scalar()

    billed_count = (await db_session.execute(
        text(f"SELECT COUNT(*) FROM main_afl WHERE {err_where} AND sent_to_billing = 'Да'"), params)).scalar()
    unbilled_count = (await db_session.execute(
        text(f"SELECT COUNT(*) FROM main_afl WHERE {err_where} AND sent_to_billing = 'Нет'"), params)).scalar()

    unbilled_err_where = f"{err_where} AND sent_to_billing = 'Нет'"
    result = await db_session.execute(text(f"SELECT errors FROM main_afl WHERE {unbilled_err_where}"), params)
    counter = Counter()
    for (errors_text,) in result:
        if errors_text:
            for e in split_errors(errors_text):
                counter[e] += 1

    errors_list = [{"label": label, "count": count} for label, count in counter.most_common()]
    return Response(content=json.dumps({
        "total_rows": total_rows,
        "with_errors": with_errors,
        "billed_count": billed_count,
        "unbilled_count": unbilled_count,
        "total_errors": sum(counter.values()),
        "errors": errors_list,
    }, ensure_ascii=False), media_type="application/json")


@get("/dashboard/errors-report", guards=[require_auth])
async def api_dashboard_errors_report(request: Request, db_session: AsyncSession, dept: str = "") -> Response:
    user = await get_current_user(request, db_session)
    clauses, params = build_scope(user, dept)
    clauses.append("(errors IS NOT NULL AND errors != '')")
    clauses.append("sent_to_billing = 'Нет'")
    where = " AND ".join(clauses)

    result = await db_session.execute(
        text(f"SELECT task_number, errors FROM main_afl WHERE {where} ORDER BY task_number"), params)
    rows = [(r[0], r[1]) for r in result]

    output = generate_errors_xlsx(rows)
    filename = f"Отчёт_об_ошибках_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.xlsx"
    return Response(content=output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"})


@get("/dashboard/balance-report", guards=[require_auth])
async def api_dashboard_balance_report(request: Request, db_session: AsyncSession, dept: str = "") -> Response:
    user = await get_current_user(request, db_session)
    clauses, params = build_scope(user, dept)
    clauses.append("errors LIKE :be")
    clauses.append("sent_to_billing = 'Нет'")
    params["be"] = "%Балансовая принадлежность%"
    where = " AND ".join(clauses)

    result = await db_session.execute(
        text(f"SELECT task_number, meter_type_2, meter_type_1, meter_type FROM main_afl WHERE {where} ORDER BY task_number"), params)
    rows = [(r[0], pick_pu_type(r[1], r[2], r[3])) for r in result]

    output = generate_balance_xlsx(rows)
    filename = f"Балансовая_принадлежность_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.xlsx"
    return Response(content=output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"})


@get("/dashboard/date-report", guards=[require_auth])
async def api_dashboard_date_report(request: Request, db_session: AsyncSession, dept: str = "") -> Response:
    user = await get_current_user(request, db_session)
    clauses, params = build_scope(user, dept)
    clauses.append("errors LIKE :dw")
    clauses.append("sent_to_billing = 'Нет'")
    params["dw"] = "%Дата работ%"
    where = " AND ".join(clauses)

    result = await db_session.execute(
        text(f"SELECT task_number FROM main_afl WHERE {where} ORDER BY task_number"), params)
    rows = [r[0] for r in result]

    output = generate_task_numbers_xlsx(rows)
    filename = f"Дата_работ_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.xlsx"
    return Response(content=output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"})


@get("/dashboard/verified-report", guards=[require_auth])
async def api_dashboard_verified_report(request: Request, db_session: AsyncSession, dept: str = "") -> Response:
    user = await get_current_user(request, db_session)
    clauses, params = build_scope(user, dept)
    clauses.append("verified = 'Нет'")
    clauses.append("sent_to_billing = 'Нет'")
    where = " AND ".join(clauses)

    result = await db_session.execute(
        text(f"SELECT task_number FROM main_afl WHERE {where} ORDER BY task_number"), params)
    rows = [r[0] for r in result]

    output = generate_task_numbers_xlsx(rows)
    filename = f"Отметка_о_проверке_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.xlsx"
    return Response(content=output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"})


dashboard_router = Router("/api", route_handlers=[
    api_dashboard_summary, api_dashboard_errors_report, api_dashboard_balance_report,
    api_dashboard_date_report, api_dashboard_verified_report,
])
