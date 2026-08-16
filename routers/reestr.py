import json
from datetime import date
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
from sql import build_in_clause
from services.reestr import DEPT_PREFIXES, LOCALE_SUFFIXES, generate_reestr_xlsx_bytes
from services.report_check import is_stop_blocked


@post("/reestr", guards=[require_auth])
async def api_reestr(
    request: Request, db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    task_numbers = data.get("task_numbers", [])
    if not task_numbers:
        return Response(content=json.dumps({"success": False, "error": "Не выбраны строки"}, ensure_ascii=False), media_type="application/json")

    user = await get_current_user(request, db_session)
    names, bind_params = build_in_clause("tn", task_numbers)

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
                tn_names, tn_params = build_in_clause("rj", new_tasks)
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

        tn_names, tn_params = build_in_clause("rn", new_tasks)
        await db_session.execute(
            text(f"UPDATE main_afl SET reestr_number = :rn, reestr_date = :rd WHERE task_number IN ({tn_names})"),
            {"rn": reestr_number, "rd": reestr_date, **tn_params})
        reestrs.append({"task_report": display_name, "reestr_number": reestr_number,
                       "count": len(new_tasks), "skipped": len(already), "rejected": 0})

    await db_session.commit()
    return Response(content=json.dumps({"success": True, "reestrs": reestrs, "reestr_date": reestr_date, "blocked": blocked}, ensure_ascii=False), media_type="application/json")


@get("/download-reestr/{reestr_number:str}", guards=[require_auth])
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


@post("/reestr/reset", guards=[require_auth])
async def api_reset_reestr(
    db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    task_numbers = data.get("task_numbers", [])
    if not task_numbers:
        return Response(content=json.dumps({"success": False, "error": "Не выбраны строки"}, ensure_ascii=False), media_type="application/json")
    names, bind_params = build_in_clause("rs", task_numbers)
    result = await db_session.execute(
        text(f"UPDATE main_afl SET reestr_number = NULL, reestr_date = NULL WHERE task_number IN ({names})"), bind_params)
    await db_session.commit()
    return Response(content=json.dumps({"success": True, "cleared": result.rowcount}, ensure_ascii=False), media_type="application/json")


@get("/reestr-list", guards=[require_auth])
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


reestr_router = Router("/api", route_handlers=[
    api_reestr, api_download_reestr, api_reset_reestr, api_reestr_list,
])

