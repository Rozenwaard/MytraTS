import json

from litestar import Router
from litestar.connection import Request
from litestar.enums import RequestEncodingType
from litestar.handlers import get, patch
from litestar.params import Body
from litestar.response import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from deps import get_current_user, require_auth
from sql import build_in_clause

MAIN_AFL_DISPLAY_COLUMNS = [
    "task_number", "task_source", "task_type", "work_type_in_task",
    "address", "municipal_district", "house_type", "personal_account",
    "service_object_type", "subscriber_name", "meter_installation_place",
    "meter_status", "meter_ownership", "violations", "comment",
    "executor", "visit_reason", "customer", "task_output", "task_report",
    "grid", "done_day", "reestr_number", "reestr_date", "errors"
]


@get("/main-afl", guards=[require_auth])
async def api_main_afl(
    request: Request, db_session: AsyncSession,
    page: int = 1, per_page: int = 50, sort: str = "", search: str = "",
    order: str = "asc", customer: str = "", task_report: str = "",
    executor_org: str = "", executor_filter: str = "",
    only_completed: bool = False, only_without_reestr: bool = False,
    reestr: str = "", task_type: str = "", done_day: str = "",
) -> Response:
    user = await get_current_user(request, db_session)
    clauses = ["1=1"]
    params: dict = {}

    if user.effective_role in ("оператор", "работник"):
        clauses.append("executor IN (SELECT full_name FROM users WHERE locale = :locale)")
        params["locale"] = user.locale
    elif user.effective_role == "менеджер":
        clauses.append("executor_organization = :dept")
        params["dept"] = user.dept

    if search:
        clauses.append("(task_number LIKE :s OR personal_account LIKE :s OR address LIKE :s)")
        params["s"] = f"%{search}%"
    if customer:
        clauses.append("customer = :customer")
        params["customer"] = customer
    if task_report:
        clauses.append("task_report = :task_report")
        params["task_report"] = task_report
    if only_completed:
        clauses.append("task_report IS NOT NULL AND task_report NOT IN ('Дубли', 'Ручная проверка')")
    if only_without_reestr:
        clauses.append("reestr_number IS NULL")
    if reestr:
        clauses.append("reestr_number = :reestr")
        params["reestr"] = reestr
    if task_type:
        clauses.append("task_type = :task_type")
        params["task_type"] = task_type
    if done_day:
        clauses.append("done_day = :done_day")
        params["done_day"] = done_day
    if executor_org:
        clauses.append("executor_organization = :executor_org")
        params["executor_org"] = executor_org
    if executor_filter:
        clauses.append("executor = :executor_filter")
        params["executor_filter"] = executor_filter

    safe_sort = sort if sort in MAIN_AFL_DISPLAY_COLUMNS else ""
    where_sql = " AND ".join(clauses)
    sort_sql = f" ORDER BY {safe_sort} {'ASC' if order == 'asc' else 'DESC'}" if safe_sort else ""
    columns_sql = ", ".join(MAIN_AFL_DISPLAY_COLUMNS)

    count_result = await db_session.execute(
        text(f"SELECT COUNT(*) FROM main_afl WHERE {where_sql}"), params)
    total = count_result.scalar()

    params["limit"] = per_page
    params["offset"] = (page - 1) * per_page
    result = await db_session.execute(
        text(f"SELECT {columns_sql} FROM main_afl WHERE {where_sql}{sort_sql} LIMIT :limit OFFSET :offset"), params)
    rows = [dict(row._mapping) for row in result]

    return Response(content=json.dumps({"rows": rows, "total": total, "page": page, "per_page": per_page}, ensure_ascii=False, default=str), media_type="application/json")


@patch("/main-afl/task-report", guards=[require_auth])
async def api_update_task_report(
    request: Request, db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    user = await get_current_user(request, db_session)
    if user.effective_role not in ('администратор', 'специалист'):
        return Response(content=json.dumps({"success": False, "error": "Нет прав"}, ensure_ascii=False), media_type="application/json")
    task_numbers = data.get("task_numbers", [])
    task_report = data.get("task_report", "")
    if not task_numbers:
        return Response(content=json.dumps({"success": False, "error": "Не выбраны строки"}, ensure_ascii=False), media_type="application/json")
    names, bind_params = build_in_clause("tr", task_numbers)
    bind_params["tr_val"] = task_report if task_report else None
    result = await db_session.execute(
        text(f"UPDATE main_afl SET task_report = :tr_val, task_detail = 'Ручная правка' WHERE task_number IN ({names})"), bind_params)
    await db_session.commit()
    return Response(content=json.dumps({"success": True, "updated": result.rowcount}, ensure_ascii=False), media_type="application/json")


@get("/main-afl/stats", guards=[require_auth])
async def api_main_afl_stats(request: Request, db_session: AsyncSession) -> Response:
    user = await get_current_user(request, db_session)
    base_where = "1=1"
    params = {}

    if user.effective_role in ("оператор", "работник"):
        base_where += " AND executor IN (SELECT full_name FROM users WHERE locale = :locale)"
        params["locale"] = user.locale
    elif user.effective_role == "менеджер":
        base_where += " AND executor_organization = :dept"
        params["dept"] = user.dept

    cust_result = await db_session.execute(
        text(f"SELECT customer, COUNT(*) FROM main_afl WHERE {base_where} GROUP BY customer"), params)
    customers = {row[0] or "(пусто)": row[1] for row in cust_result}

    plan_result = await db_session.execute(
        text(f"SELECT task_type, COUNT(*) FROM main_afl WHERE {base_where} AND task_type IN ('Плановый', 'Внеплановый') GROUP BY task_type"), params)
    plan_counts = {row[0]: row[1] for row in plan_result}

    with_r = await db_session.execute(
        text(f"SELECT COUNT(*) FROM main_afl WHERE {base_where} AND reestr_number IS NOT NULL AND reestr_number != 'Отклонён'"), params)
    without_r = await db_session.execute(
        text(f"SELECT COUNT(*) FROM main_afl WHERE {base_where} AND reestr_number IS NULL"), params)

    completed = await db_session.execute(
        text(f"SELECT COUNT(*) FROM main_afl WHERE {base_where} AND task_report IS NOT NULL AND task_report NOT IN ('Дубли', 'Ручная проверка')"), params)
    uncompleted = await db_session.execute(
        text(f"SELECT COUNT(*) FROM main_afl WHERE {base_where} AND (task_report IS NULL OR task_report = '' OR task_report IN ('Дубли', 'Ручная проверка'))"), params)

    tr_result = await db_session.execute(
        text(f"SELECT COALESCE(task_report, 'Не выполнено'), COUNT(*) FROM main_afl WHERE {base_where} GROUP BY task_report ORDER BY COUNT(*) DESC"), params)
    task_reports = [{"label": row[0], "count": row[1]} for row in tr_result]

    ex_result = await db_session.execute(
        text(f"""SELECT m.executor, m.cnt, u.locale
                 FROM (SELECT executor, COUNT(*) as cnt FROM main_afl
                       WHERE {base_where} AND executor IS NOT NULL GROUP BY executor) m
                 LEFT JOIN users u ON u.full_name = m.executor
                 ORDER BY m.executor"""), params)
    executors = [{"label": row[0], "count": row[1], "locale": row[2]} for row in ex_result]

    dept_result = await db_session.execute(
        text(f"SELECT executor_organization, COUNT(*) FROM main_afl WHERE {base_where} AND executor_organization IS NOT NULL GROUP BY executor_organization ORDER BY executor_organization"), params)
    depts = [{"label": row[0], "count": row[1]} for row in dept_result]

    dd_result = await db_session.execute(
        text(f"SELECT DISTINCT done_day FROM main_afl WHERE {base_where} AND done_day IS NOT NULL ORDER BY done_day ASC"), params)
    done_days = [row[0] for row in dd_result]

    return Response(content=json.dumps({
        "customers": customers,
        "plan": plan_counts.get("Плановый", 0),
        "unplan": plan_counts.get("Внеплановый", 0),
        "with_reestr": with_r.scalar(),
        "without_reestr": without_r.scalar(),
        "completed": completed.scalar(),
        "uncompleted": uncompleted.scalar(),
        "task_reports": task_reports,
        "executors": executors,
        "depts": depts,
        "done_days": done_days,
    }, ensure_ascii=False), media_type="application/json")


main_afl_router = Router("/api", route_handlers=[
    api_main_afl, api_main_afl_stats, api_update_task_report,
])

