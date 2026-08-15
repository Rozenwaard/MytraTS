import asyncio
import hashlib
import json
import traceback
import uuid
from collections import Counter
from datetime import date
from typing import Any
from urllib.parse import quote

from dotenv import load_dotenv
from litestar import Litestar, patch
from litestar.config.cors import CORSConfig
from litestar.connection import ASGIConnection, Request
from litestar.datastructures import UploadFile
from litestar.enums import RequestEncodingType
from litestar.exceptions import NotFoundException, NotAuthorizedException
from litestar.handlers import get, post
from litestar.middleware.session.client_side import CookieBackendConfig
from litestar.params import Body
from litestar.response import Response
from sqlalchemy import text, select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from data.config import sqlalchemy_plugin, SECRET_KEY
from data.models import User
from services.merger import merge_to_main
from services.processor import process_raw_afl
from services.reestr import DEPT_PREFIXES, LOCALE_SUFFIXES, generate_reestr_xlsx_bytes, generate_report_xlsx_bytes
from services.uploader import load_xlsx_to_raw
from services.report_check import is_stop_blocked, recompute_errors, split_errors
from services.dashboard import build_scope, generate_errors_xlsx, generate_balance_xlsx, pick_pu_type

load_dotenv()
upload_progress: dict[str, dict] = {}
session_config = CookieBackendConfig(secret=SECRET_KEY.encode())


async def get_current_user(request: Request, db_session: AsyncSession) -> User | None:
    user_id = request.session.get("user_id")
    if user_id:
        result = await db_session.execute(sa_select(User).where(User.id == user_id))
        return result.scalar_one_or_none()
    return None


def require_auth(connection: ASGIConnection, _: Any) -> None:
    if not connection.session.get("user_id"):
        raise NotAuthorizedException()

# ─── Auth ──────────────────────────────────────────────────────

@post("/api/login")
async def api_login(
    request: Request, db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    staff_id = data.get("staff_id", "")
    password = data.get("password", "")
    if not staff_id:
        return Response(content=json.dumps({"ok": False, "error": "Введите табельный номер"}, ensure_ascii=False), media_type="application/json", status_code=400)

    result = await db_session.execute(sa_select(User).where(User.staff_id == staff_id))
    user = result.scalar_one_or_none()
    if not user:
        return Response(content=json.dumps({"ok": False, "error": "Неверный логин или пароль"}, ensure_ascii=False), media_type="application/json", status_code=401)

    if user.password_hash is None:
        if password != user.staff_id:
            return Response(content=json.dumps({"ok": False, "error": "Неверный логин или пароль"}, ensure_ascii=False), media_type="application/json", status_code=401)
        request.session["user_id"] = user.id
        return Response(content=json.dumps({"ok": True, "change_password": True, "full_name": user.full_name, "role": user.effective_role}, ensure_ascii=False), media_type="application/json")

    if user.password_hash != hashlib.sha256(password.encode()).hexdigest():
        return Response(content=json.dumps({"ok": False, "error": "Неверный логин или пароль"}, ensure_ascii=False), media_type="application/json", status_code=401)

    request.session["user_id"] = user.id
    return Response(content=json.dumps({"ok": True, "change_password": False, "full_name": user.full_name, "role": user.effective_role}, ensure_ascii=False), media_type="application/json")


@get("/api/me", guards=[require_auth])
async def api_me(request: Request, db_session: AsyncSession) -> Response:
    user = await get_current_user(request, db_session)
    if not user:
        return Response(content=json.dumps({"user": None}, ensure_ascii=False), media_type="application/json", status_code=401)
    return Response(content=json.dumps({"user": {"id": user.id, "full_name": user.full_name, "dept": user.dept, "locale": user.locale, "position": user.position, "staff_id": user.staff_id, "role": user.effective_role}}, ensure_ascii=False), media_type="application/json")


@post("/api/logout")
async def api_logout(request: Request) -> Response:
    request.session.clear()
    return Response(content=json.dumps({"ok": True}), media_type="application/json")


@post("/api/change-password", guards=[require_auth])
async def api_change_password(
    request: Request, db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    new_password = data.get("new_password", "")
    confirm_password = data.get("confirm_password", "")
    if len(new_password) < 4:
        return Response(content=json.dumps({"ok": False, "error": "Пароль должен быть не менее 4 символов"}, ensure_ascii=False), media_type="application/json", status_code=400)
    if new_password != confirm_password:
        return Response(content=json.dumps({"ok": False, "error": "Пароли не совпадают"}, ensure_ascii=False), media_type="application/json", status_code=400)
    user_id = request.session.get("user_id")
    await db_session.execute(text("UPDATE users SET password_hash = :hash WHERE id = :id"), {"hash": hashlib.sha256(new_password.encode()).hexdigest(), "id": user_id})
    await db_session.commit()
    return Response(content=json.dumps({"ok": True}), media_type="application/json")


# ─── User Settings ─────────────────────────────────────────────

@get("/api/user/settings", guards=[require_auth])
async def api_get_settings(request: Request, db_session: AsyncSession) -> Response:
    user = await get_current_user(request, db_session)
    if not user:
        return Response(content=json.dumps({"settings": None}), media_type="application/json")
    return Response(content=json.dumps({"settings": json.loads(user.settings) if user.settings else None}, ensure_ascii=False), media_type="application/json")


@post("/api/user/settings", guards=[require_auth])
async def api_save_settings(
    request: Request,
    db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    user = await get_current_user(request, db_session)
    if not user:
        return Response(content=json.dumps({"ok": False}), media_type="application/json", status_code=401)
    settings_json = json.dumps(data.get("settings", {}), ensure_ascii=False)
    await db_session.execute(
        text("UPDATE users SET settings = :s WHERE id = :id"),
        {"s": settings_json, "id": user.id})
    await db_session.commit()
    return Response(content=json.dumps({"ok": True}), media_type="application/json")

# ─── Users & Upload ────────────────────────────────────────────

@get("/api/users/search")
async def api_search_users(db_session: AsyncSession, q: str = "") -> Response:
    if len(q) < 2:
        return Response(content=json.dumps([]), media_type="application/json")
    result = await db_session.execute(text("SELECT full_name, position, staff_id FROM users"))
    all_users = [{"full_name": row[0], "position": row[1], "staff_id": row[2]} for row in result]
    q_lower = q.lower()
    filtered = [u for u in all_users if q_lower in u["full_name"].lower()][:5]
    return Response(content=json.dumps(filtered, ensure_ascii=False), media_type="application/json")


@post("/api/upload", guards=[require_auth])
async def api_upload(data: UploadFile = Body(media_type=RequestEncodingType.MULTI_PART)) -> Response:
    if not data or not data.filename.endswith('.xlsx'):
        return Response(content=json.dumps({"error": "Нужен файл .xlsx"}, ensure_ascii=False), media_type="application/json", status_code=400)
    try:
        content = await data.read()
        upload_id = str(uuid.uuid4())
        upload_progress[upload_id] = {"status": "starting", "progress": 0, "total": 0}
        asyncio.create_task(_run_pipeline(upload_id, content))
        return Response(content=json.dumps({"upload_id": upload_id}, ensure_ascii=False), media_type="application/json")
    except Exception as e:
        traceback.print_exc()
        return Response(content=json.dumps({"error": str(e)}, ensure_ascii=False), media_type="application/json", status_code=500)


@get("/api/upload/progress/{upload_id:str}")
async def api_upload_progress(upload_id: str) -> Response:
    if upload_id not in upload_progress:
        return Response(content=json.dumps({"status": "not_found"}, ensure_ascii=False), media_type="application/json", status_code=404)
    return Response(content=json.dumps(upload_progress[upload_id], ensure_ascii=False), media_type="application/json")


async def _run_pipeline(upload_id: str, content: bytes):
    from data.config import async_session_factory
    async with async_session_factory() as db_session:
        try:
            upload_progress[upload_id] = {"status": "loading", "progress": 5, "total": 0}
            success, error, total_rows = await load_xlsx_to_raw(db_session, content)
            if not success:
                upload_progress[upload_id] = {"status": "error", "progress": 0, "total": 0, "message": error}
                return
            upload_progress[upload_id] = {"status": "loaded", "progress": 20, "total": total_rows, "loaded": total_rows}
            upload_progress[upload_id] = {"status": "processing", "progress": 25, "total": total_rows}
            success = await process_raw_afl(db_session, upload_progress, upload_id, total_rows)
            if not success:
                return
            upload_progress[upload_id] = {"status": "merging", "progress": 90, "total": total_rows}
            inserted, updated, affected = await merge_to_main(db_session, upload_progress, upload_id, total_rows)
            await recompute_errors(db_session, affected)
            upload_progress[upload_id] = {"status": "complete", "progress": 100, "total": total_rows, "inserted": inserted, "updated": updated, "message": f"Загружено: {total_rows} строк | Новых: {inserted} | Обновлено: {updated}"}
        except Exception as e:
            await db_session.rollback()
            upload_progress[upload_id] = {"status": "error", "progress": 0, "total": 0, "message": str(e)}
            traceback.print_exc()

# ─── Main AFL ──────────────────────────────────────────────────

MAIN_AFL_DISPLAY_COLUMNS = [
    "task_number", "task_source", "task_type", "work_type_in_task",
    "address", "municipal_district", "house_type", "personal_account",
    "service_object_type", "subscriber_name", "meter_installation_place",
    "meter_status", "meter_ownership", "violations", "comment",
    "executor", "visit_reason", "customer", "task_output", "task_report",
    "grid", "done_day", "reestr_number", "reestr_date", "errors"
]


@get("/api/main-afl", guards=[require_auth])
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

# ─── Reestr Helper ────────────────────────────────────────────

def _build_in_clause(prefix: str, values: list[str]) -> tuple[str, dict]:
    placeholders = {f"{prefix}{i}": v for i, v in enumerate(values)}
    names = ", ".join(f":{prefix}{i}" for i in range(len(values)))
    return names, placeholders


@post("/api/reestr", guards=[require_auth])
async def api_reestr(
    request: Request, db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    task_numbers = data.get("task_numbers", [])
    if not task_numbers:
        return Response(content=json.dumps({"success": False, "error": "Не выбраны строки"}, ensure_ascii=False), media_type="application/json")

    user = await get_current_user(request, db_session)
    names, bind_params = _build_in_clause("tn", task_numbers)

    result = await db_session.execute(
        text(f"SELECT task_number, task_report, executor_organization, customer, grid, reestr_number, errors, region, municipal_district, "
             f"(SELECT locale FROM users WHERE users.full_name = main_afl.executor LIMIT 1) as locale "
             f"FROM main_afl WHERE task_number IN ({names})"), bind_params)
    all_rows = [dict(row._mapping) for row in result]

    blocked_set = {r["task_number"] for r in all_rows if is_stop_blocked(r)}
    rows = [r for r in all_rows if r["task_number"] not in blocked_set]
    blocked = sorted(blocked_set)

    groups: dict = {}
    existing_map: dict = {}
    for r in rows:
        key = (r["executor_organization"], r["customer"], r["grid"], r["task_report"], r["locale"])
        if key not in groups:
            groups[key] = {"task_numbers": [], "dept": r["executor_organization"],
                           "customer": r["customer"], "grid": r["grid"],
                           "task_report": r["task_report"], "locale": r["locale"]}
        groups[key]["task_numbers"].append(r["task_number"])
        existing_map[r["task_number"]] = r["reestr_number"]

    today = date.today()
    reestr_date = today.isoformat()
    invalid_reports = {"Дубли", "Ручная проверка"}
    reestrs = []

    for (dept, customer, grid_val, task_report, locale_val), group in groups.items():
        new_tasks = [tn for tn in group["task_numbers"] if existing_map.get(tn) is None]
        already = [tn for tn in group["task_numbers"] if existing_map.get(tn) is not None]
        display_name = f"{customer} / {grid_val} / {task_report}" if task_report else f"{customer} / {grid_val} / Без категории"

        if task_report is None or task_report == "" or task_report in invalid_reports:
            if new_tasks:
                tn_names, tn_params = _build_in_clause("rj", new_tasks)
                await db_session.execute(
                    text(f"UPDATE main_afl SET reestr_number = 'Отклонён' WHERE task_number IN ({tn_names})"), tn_params)
            reestrs.append({"task_report": display_name, "reestr_number": "Отклонён",
                           "count": 0, "skipped": len(already), "rejected": len(new_tasks)})
            continue

        if not new_tasks:
            if already:
                reestrs.append({"task_report": display_name, "reestr_number": existing_map[already[0]],
                               "count": 0, "skipped": len(already), "rejected": 0})
            continue

        prefix = DEPT_PREFIXES.get(dept, "XX")
        suffix = LOCALE_SUFFIXES.get(locale_val, "")
        pattern = f"%-{prefix}{suffix}%" if suffix else f"%-{prefix}%"

        count_result = await db_session.execute(
            text("SELECT reestr_number FROM main_afl WHERE reestr_number LIKE :pattern AND reestr_number != 'Отклонён'"),
            {"pattern": pattern})
        existing_numbers = [row[0] for row in count_result]
        max_num = max([int(n.split('-')[0]) for n in existing_numbers
                       if n and '-' in n and n.split('-')[0].isdigit()], default=0)
        count = max_num + 1
        reestr_number = f"{count}-{prefix}{suffix}" if suffix else f"{count}-{prefix}"

        tn_names, tn_params = _build_in_clause("rn", new_tasks)
        await db_session.execute(
            text(f"UPDATE main_afl SET reestr_number = :rn, reestr_date = :rd WHERE task_number IN ({tn_names})"),
            {"rn": reestr_number, "rd": reestr_date, **tn_params})
        reestrs.append({"task_report": display_name, "reestr_number": reestr_number,
                       "count": len(new_tasks), "skipped": len(already), "rejected": 0})

    await db_session.commit()
    return Response(content=json.dumps({"success": True, "reestrs": reestrs, "reestr_date": reestr_date, "blocked": blocked}, ensure_ascii=False), media_type="application/json")


@get("/api/download-reestr/{reestr_number:str}", guards=[require_auth])
async def api_download_reestr(request: Request, db_session: AsyncSession, reestr_number: str) -> Response:
    user = await get_current_user(request, db_session)
    result = await db_session.execute(
        text("SELECT task_report, executor_organization, reestr_date FROM main_afl WHERE reestr_number = :rn LIMIT 1"),
        {"rn": reestr_number})
    row = result.fetchone()
    if not row:
        return Response(content="Реестр не найден", status_code=404)
    task_report, dept, reestr_date = row[0], row[1], row[2]
    tasks_result = await db_session.execute(
        text("SELECT task_number FROM main_afl WHERE reestr_number = :rn ORDER BY task_number"), {"rn": reestr_number})
    task_numbers = [r[0] for r in tasks_result]
    output = await generate_reestr_xlsx_bytes(db_session, task_numbers, reestr_number, reestr_date, task_report, dept, user)
    filename = f"Реестр_{reestr_number}.xlsx"
    return Response(content=output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"})


@post("/api/reestr/reset", guards=[require_auth])
async def api_reset_reestr(
    db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    task_numbers = data.get("task_numbers", [])
    if not task_numbers:
        return Response(content=json.dumps({"success": False, "error": "Не выбраны строки"}), media_type="application/json")
    names, bind_params = _build_in_clause("rs", task_numbers)
    result = await db_session.execute(
        text(f"UPDATE main_afl SET reestr_number = NULL, reestr_date = NULL WHERE task_number IN ({names})"), bind_params)
    await db_session.commit()
    return Response(content=json.dumps({"success": True, "cleared": result.rowcount}), media_type="application/json")


@patch("/api/main-afl/task-report", guards=[require_auth])
async def api_update_task_report(
    request: Request, db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    user = await get_current_user(request, db_session)
    if user.effective_role not in ('администратор', 'специалист'):
        return Response(content=json.dumps({"success": False, "error": "Нет прав"}), media_type="application/json")
    task_numbers = data.get("task_numbers", [])
    task_report = data.get("task_report", "")
    if not task_numbers:
        return Response(content=json.dumps({"success": False, "error": "Не выбраны строки"}), media_type="application/json")
    names, bind_params = _build_in_clause("tr", task_numbers)
    bind_params["tr_val"] = task_report if task_report else None
    result = await db_session.execute(
        text(f"UPDATE main_afl SET task_report = :tr_val, task_detail = 'Ручная правка' WHERE task_number IN ({names})"), bind_params)
    await db_session.commit()
    return Response(content=json.dumps({"success": True, "updated": result.rowcount}), media_type="application/json")

# ─── Report ────────────────────────────────────────────────────

@post("/api/report", guards=[require_auth])
async def api_report(
    request: Request, db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    user = await get_current_user(request, db_session)
    if user.effective_role not in ('администратор', 'специалист'):
        return Response(content=json.dumps({"success": False, "error": "Нет прав"}), media_type="application/json")
    month = data.get("month")
    year = data.get("year")
    if not month or not year:
        return Response(content=json.dumps({"success": False, "error": "Выберите месяц и год"}), media_type="application/json")
    months = ["", "январь", "февраль", "март", "апрель", "май", "июнь",
              "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
    period = f"{months[month]} {year}"

    result1 = await db_session.execute(
        text("UPDATE main_afl SET report = :period WHERE reestr_date IS NOT NULL AND report IS NULL"),
        {"period": period})
    count = result1.rowcount

    result2 = await db_session.execute(
        text("UPDATE main_afl SET report = 'Отклонён' WHERE reestr_number = 'Отклонён' AND report IS NULL"))
    rejected = result2.rowcount

    await db_session.execute(text("INSERT INTO story_afl SELECT * FROM main_afl WHERE report IS NOT NULL"))
    await db_session.execute(text("DELETE FROM main_afl WHERE report IS NOT NULL"))
    await db_session.commit()

    return Response(content=json.dumps({
        "success": True, "period": period, "count": count, "rejected": rejected,
        "download_url": f"/api/download-report/{quote(period)}"
    }, ensure_ascii=False), media_type="application/json")


@get("/api/download-report/{period:str}", guards=[require_auth])
async def api_download_report(period: str, db_session: AsyncSession) -> Response:
    output = await generate_report_xlsx_bytes(db_session, period)
    filename = f"Отчёт_{period}.xlsx"
    return Response(content=output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"})

# ─── Story / Archive ───────────────────────────────────────────

STORY_DISPLAY_COLUMNS = [
    "task_number", "task_type", "work_type_in_task", "created_at",
    "address", "municipal_district", "house_type", "personal_account",
    "subscriber_name", "meter_installation_place", "meter_status",
    "violations", "comment", "executor", "executor_organization",
    "visit_reason", "customer", "task_output", "task_report", "task_detail",
    "grid", "done_day", "reestr_number", "reestr_date", "report"
]


@get("/api/story-afl", guards=[require_auth])
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


@post("/api/story-afl/reject", guards=[require_auth])
async def api_reject_story(
    request: Request, db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    user = await get_current_user(request, db_session)
    if user.effective_role not in ('администратор', 'специалист'):
        return Response(content=json.dumps({"success": False, "error": "Нет прав"}), media_type="application/json")
    task_numbers = data.get("task_numbers", [])
    if not task_numbers:
        return Response(content=json.dumps({"success": False, "error": "Не выбраны строки"}), media_type="application/json")
    names, bind_params = _build_in_clause("st", task_numbers)
    result = await db_session.execute(
        text(f"UPDATE story_afl SET task_report = 'Отклонён', task_detail = 'Разногласия' WHERE task_number IN ({names})"), bind_params)
    await db_session.commit()
    return Response(content=json.dumps({"success": True, "updated": result.rowcount}), media_type="application/json")


# ─── Stats ─────────────────────────────────────────────────────

@get("/api/main-afl/stats", guards=[require_auth])
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


# ─── Lookups ───────────────────────────────────────────────────

@get("/api/reestr-list", guards=[require_auth])
async def api_reestr_list(request: Request, db_session: AsyncSession) -> Response:
    user = await get_current_user(request, db_session)
    query = "SELECT DISTINCT reestr_number FROM main_afl WHERE reestr_number IS NOT NULL AND reestr_number != 'Отклонён'"
    params = {}
    if user.effective_role in ("оператор", "работник"):
        query += " AND executor IN (SELECT full_name FROM users WHERE locale = :locale)"
        params["locale"] = user.locale
    elif user.effective_role == "менеджер":
        query += " AND executor_organization = :dept"
        params["dept"] = user.dept
    query += " ORDER BY CAST(substr(reestr_number, 1, instr(reestr_number, '-') - 1) AS INTEGER)"
    result = await db_session.execute(text(query), params)
    reestrs_raw = await db_session.execute(
        text("SELECT DISTINCT reestr_number, task_report, customer FROM main_afl WHERE reestr_number IS NOT NULL AND reestr_number != 'Отклонён'"),
        params)
    reestr_meta = {}
    for row in reestrs_raw:
        if row[0] not in reestr_meta:
            reestr_meta[row[0]] = {"task_report": row[1], "customer": row[2]}
    reestrs = [row[0] for row in result]
    return Response(content=json.dumps({"reestrs": reestrs, "meta": reestr_meta}, ensure_ascii=False), media_type="application/json")


@get("/api/executor-organizations", guards=[require_auth])
async def api_executor_organizations(db_session: AsyncSession) -> Response:
    result = await db_session.execute(text(
        "SELECT DISTINCT executor_organization FROM main_afl WHERE executor_organization IS NOT NULL ORDER BY executor_organization"))
    orgs = [row[0] for row in result]
    return Response(content=json.dumps(orgs, ensure_ascii=False), media_type="application/json")


@get("/api/executors", guards=[require_auth])
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


@get("/api/task-reports", guards=[require_auth])
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


@get("/api/dashboard/summary", guards=[require_auth])
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


@get("/api/dashboard/errors-report", guards=[require_auth])
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


@get("/api/dashboard/balance-report", guards=[require_auth])
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


# ─── App Init ─────────────────────────────────────────────────

cors_config = CORSConfig(allow_origins=["http://localhost:5173"], allow_credentials=True)


app = Litestar(
    route_handlers=[
        api_login, api_me, api_logout, api_change_password, api_get_settings, api_save_settings,
        api_search_users,
        api_upload, api_upload_progress,
        api_main_afl, api_main_afl_stats,
        api_reestr, api_download_reestr, api_reset_reestr,
        api_update_task_report,
        api_report, api_download_report,
        api_dashboard_summary, api_dashboard_errors_report, api_dashboard_balance_report,
        api_story_afl, api_reject_story,
        api_executor_organizations, api_reestr_list,
        api_executors, api_task_reports,
    ],
    plugins=[sqlalchemy_plugin],
    middleware=[session_config.middleware],
    cors_config=cors_config,
    exception_handlers={NotFoundException: lambda r, e: Response(content=json.dumps({"error": "Not found"}), media_type="application/json", status_code=404)},
    request_max_body_size=35 * 1024 * 1024,
)
