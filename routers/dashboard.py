import json
from collections import Counter
from urllib.parse import quote

from litestar import Router
from litestar.connection import Request
from litestar.handlers import get
from litestar.response import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from deps import get_current_user, require_auth
from services.dashboard import build_scope, generate_errors_xlsx, generate_balance_xlsx, pick_pu_type
from services.report_check import split_errors


@get("/dashboard/summary", guards=[require_auth])
async def api_dashboard_summary(request: Request, db_session: AsyncSession, dept: str = "") -> Response:
    user = await get_current_user(request, db_session)
    clauses, params = build_scope(user, dept)
    where = " AND ".join(clauses)

    result = await db_session.execute(text(f"SELECT errors FROM main_afl WHERE {where}"), params)
    counter = Counter()
    total_with_errors = 0
    for (errors_text,) in result:
        if errors_text:
            total_with_errors += 1
            for e in split_errors(errors_text):
                counter[e] += 1

    errors_list = [{"label": label, "count": count} for label, count in counter.most_common()]
    return Response(content=json.dumps({
        "total_with_errors": total_with_errors,
        "total_errors": sum(counter.values()),
        "errors": errors_list,
    }, ensure_ascii=False), media_type="application/json")


@get("/dashboard/errors-report", guards=[require_auth])
async def api_dashboard_errors_report(request: Request, db_session: AsyncSession, dept: str = "") -> Response:
    user = await get_current_user(request, db_session)
    clauses, params = build_scope(user, dept)
    where = " AND ".join(clauses)

    result = await db_session.execute(
        text(f"SELECT task_number, errors FROM main_afl WHERE {where} ORDER BY task_number"), params)
    rows = [(r[0], r[1]) for r in result]

    output = generate_errors_xlsx(rows)
    filename = "Отчёт_об_ошибках.xlsx"
    return Response(content=output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"})


@get("/dashboard/balance-report", guards=[require_auth])
async def api_dashboard_balance_report(request: Request, db_session: AsyncSession, dept: str = "") -> Response:
    user = await get_current_user(request, db_session)
    clauses, params = build_scope(user, dept)
    clauses.append("errors LIKE :be")
    params["be"] = "%Балансовая принадлежность%"
    where = " AND ".join(clauses)

    result = await db_session.execute(
        text(f"SELECT task_number, meter_type_2, meter_type_1, meter_type FROM main_afl WHERE {where} ORDER BY task_number"), params)
    rows = [(r[0], pick_pu_type(r[1], r[2], r[3])) for r in result]

    output = generate_balance_xlsx(rows)
    filename = "Балансовая_принадлежность.xlsx"
    return Response(content=output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"})


dashboard_router = Router("/api", route_handlers=[
    api_dashboard_summary, api_dashboard_errors_report, api_dashboard_balance_report,
])
