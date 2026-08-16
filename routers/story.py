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
from sql import build_in_clause

STORY_DISPLAY_COLUMNS = [
    "task_number", "task_type", "work_type_in_task", "created_at",
    "address", "municipal_district", "house_type", "personal_account",
    "subscriber_name", "meter_installation_place", "meter_status",
    "violations", "comment", "executor", "executor_organization",
    "visit_reason", "customer", "task_output", "task_report", "task_detail",
    "grid", "done_day", "reestr_number", "reestr_date", "report"
]


@get("/story-afl", guards=[require_auth])
async def api_story_afl(
    request: Request, db_session: AsyncSession,
    page: int = 1, per_page: int = 50, search: str = "",
    period_month: str = "", period_year: str = "", customer: str = "",
    task_report: str = "", task_type: str = "", grid: str = "",
    house_type: str = "", municipal_district: str = "",
    meter_installation_place: str = "", executor_organization: str = "",
    executor: str = "", report: str = "", task_detail: str = "",
) -> Response:
    user = await get_current_user(request, db_session)
    clauses = ["1=1"]
    params: dict = {}

    if search:
        clauses.append("(task_number LIKE :s OR personal_account LIKE :s OR address LIKE :s)")
        params["s"] = f"%{search}%"
    if period_month and period_year:
        clauses.append("done_day LIKE :period")
        params["period"] = f"{period_year}-{period_month.zfill(2)}%"

    for field in ["customer", "task_report", "task_type", "grid", "house_type",
                   "municipal_district", "meter_installation_place",
                   "executor_organization", "executor", "report", "task_detail"]:
        val = locals().get(field, "")
        if val:
            clauses.append(f"{field} = :{field}")
            params[field] = val

    where_sql = " AND ".join(clauses)
    columns_sql = ", ".join(STORY_DISPLAY_COLUMNS)

    count_result = await db_session.execute(
        text(f"SELECT COUNT(*) FROM story_afl WHERE {where_sql}"), params)
    total = count_result.scalar()

    params["limit"] = per_page
    params["offset"] = (page - 1) * per_page
    result = await db_session.execute(
        text(f"SELECT {columns_sql} FROM story_afl WHERE {where_sql} LIMIT :limit OFFSET :offset"), params)
    rows = [dict(row._mapping) for row in result]

    filter_counts: dict = {}
    base_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}
    filter_fields = ["customer", "task_report", "task_type", "grid", "house_type",
                     "municipal_district", "meter_installation_place",
                     "executor_organization", "executor", "report", "task_detail"]
    base_where = " AND ".join(clauses)
    for field in filter_fields:
        count_result = await db_session.execute(
            text(f"SELECT {field}, COUNT(*) as cnt FROM story_afl WHERE {base_where} GROUP BY {field} ORDER BY {field}"), base_params)
        filter_counts[field] = [{"value": row[0] or "(пусто)", "count": row[1]} for row in count_result]

    return Response(content=json.dumps({
        "rows": rows, "total": total, "page": page, "per_page": per_page,
        "filter_counts": filter_counts
    }, ensure_ascii=False, default=str), media_type="application/json")


@post("/story-afl/reject", guards=[require_auth])
async def api_reject_story(
    request: Request, db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    user = await get_current_user(request, db_session)
    if user.effective_role not in ('администратор', 'специалист'):
        return Response(content=json.dumps({"success": False, "error": "Нет прав"}, ensure_ascii=False), media_type="application/json")
    task_numbers = data.get("task_numbers", [])
    if not task_numbers:
        return Response(content=json.dumps({"success": False, "error": "Не выбраны строки"}, ensure_ascii=False), media_type="application/json")
    names, bind_params = build_in_clause("st", task_numbers)
    result = await db_session.execute(
        text(f"UPDATE story_afl SET task_report = 'Отклонён', task_detail = 'Разногласия' WHERE task_number IN ({names})"), bind_params)
    await db_session.commit()
    return Response(content=json.dumps({"success": True, "updated": result.rowcount}, ensure_ascii=False), media_type="application/json")


story_router = Router("/api", route_handlers=[api_story_afl, api_reject_story])
