import json

from litestar import Router
from litestar.connection import Request
from litestar.handlers import get
from litestar.response import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from deps import get_current_user, require_auth


@get("/executor-organizations", guards=[require_auth])
async def api_executor_organizations(db_session: AsyncSession) -> Response:
    result = await db_session.execute(text(
        "SELECT DISTINCT executor_organization FROM main_afl WHERE executor_organization IS NOT NULL ORDER BY executor_organization"))
    orgs = [row[0] for row in result]
    return Response(content=json.dumps(orgs, ensure_ascii=False), media_type="application/json")


@get("/executors", guards=[require_auth])
async def api_executors(request: Request, db_session: AsyncSession) -> Response:
    user = await get_current_user(request, db_session)
    if user.effective_role in ("оператор", "работник"):
        result = await db_session.execute(text(
            "SELECT DISTINCT executor FROM main_afl WHERE executor IN (SELECT full_name FROM users WHERE locale = :locale) AND executor IS NOT NULL ORDER BY executor"),
            {"locale": user.locale})
    elif user.effective_role == "менеджер":
        result = await db_session.execute(text(
            "SELECT DISTINCT executor FROM main_afl WHERE executor_organization = :dept AND executor IS NOT NULL ORDER BY executor"),
            {"dept": user.dept})
    else:
        result = await db_session.execute(text(
            "SELECT DISTINCT executor FROM main_afl WHERE executor IS NOT NULL ORDER BY executor"))
    executors = [row[0] for row in result]
    return Response(content=json.dumps(executors, ensure_ascii=False), media_type="application/json")


@get("/task-reports", guards=[require_auth])
async def api_task_reports(request: Request, db_session: AsyncSession) -> Response:
    user = await get_current_user(request, db_session)
    query = """SELECT DISTINCT task_report FROM main_afl WHERE task_report IS NOT NULL
            AND task_report NOT IN ('Диспетчеризация', 'Дубли', 'Ручная проверка')"""
    params = {}
    if user.effective_role in ("оператор", "работник"):
        query += " AND executor IN (SELECT full_name FROM users WHERE locale = :locale)"
        params["locale"] = user.locale
    elif user.effective_role == "менеджер":
        query += " AND executor_organization = :dept"
        params["dept"] = user.dept
    query += " ORDER BY task_report"
    result = await db_session.execute(text(query), params)
    reports = [row[0] for row in result]
    return Response(content=json.dumps(reports, ensure_ascii=False), media_type="application/json")


lookups_router = Router("/api", route_handlers=[
    api_executor_organizations, api_executors, api_task_reports,
])
