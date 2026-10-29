"""УЛР — загрузка реестра: справочники для формы и приём файла с матчингом в main_afl."""
import json
from datetime import datetime

from litestar import Router
from litestar.connection import Request
from litestar.exceptions import NotAuthorizedException
from litestar.enums import RequestEncodingType
from litestar.handlers import get, patch, post
from litestar.params import Body
from litestar.response import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from data.config import sand_session_factory
from deps import get_current_user, require_auth
from services.ulr import (CO_EXECUTOR_WORK_IDS, EXECUTOR_POSITIONS, INSERT_SQL, NO_EXECUTION,
                          STATUS_DONE, STATUS_SENT, build_main_afl_row, compute_status,
                          feedback_xlsx_b64, find_points, read_register, resolve_work_ids)

CUSTOMERS = ["ПСК", "РЛЭ"]
# Подразделения заказчика: ПСК — из Книга123.xlsx (лист 3), РЛЭ — филиалы.
SUBDIVISIONS = {
    "ПСК": ["ДРЛО", "ЛО", "ОВОКУ", "ОДРДП", "ОДРП ЖКХ ЛО", "ОДРП ЖКХ СПБ", "ОКРБП", "ОКРЮЛ", "ООКПЭ", "ОТАПЭ", "ОЭР", "ПТО", "УРБП", "УРДЗ", "УРДЗ ЖКХ и РСО", "УРКП", "УРНП", "ЦОДК"],
    "РЛЭ": ["ВЭС", "ГтЭС", "КнЭС", "НлЭС", "СЭС", "ТхЭС", "ЮЭС"],
}
# Виды работ, которые не показываем в выпадающем списке «Поручение» формы УЛР.
EXCLUDED_WORK_TYPES = ("недопуск", "бездог")
# Виды поручений (категории) по заказчику — из Книга123.xlsx (лист 2).
ASSIGNMENT_TYPES = {
    "РЛЭ": ["Архив", "Допуск", "ИП", "КРО", "КСП", "Опрос", "Привязка"],
    "ПСК": ["Архив", "Допуск", "Доставка", "ИП", "КРО", "КСП", "Осмотр"],
}
ADMIN_ROLES = ("администратор", "специалист")


async def _require_role(request: Request, db_session: AsyncSession) -> None:
    user = await get_current_user(request, db_session)
    if not user or user.effective_role not in ADMIN_ROLES:
        raise NotAuthorizedException()


@get("/ulr/options", guards=[require_auth])
async def api_ulr_options(request: Request, db_session: AsyncSession) -> Response:
    await _require_role(request, db_session)
    result = await db_session.execute(text(
        "SELECT short, title, customer FROM work_catalog WHERE kind = 'base'"))
    work_types = sorted(
        ({"short": r[0], "title": r[1], "customer": r[2]} for r in result),
        key=lambda w: (w["short"] or "").lower(),
    )
    return Response(content=json.dumps(
        {"customers": CUSTOMERS, "subdivisions": SUBDIVISIONS, "work_types": work_types,
         "assignment_types": ASSIGNMENT_TYPES},
        ensure_ascii=False), media_type="application/json")


@post("/ulr/upload", guards=[require_auth])
async def api_ulr_upload(request: Request, db_session: AsyncSession) -> Response:
    await _require_role(request, db_session)

    form = await request.form()

    def _f(key: str) -> str:
        v = form.get(key)
        return v.strip() if isinstance(v, str) else ""

    customer = _f("customer")
    visit_reason = _f("visit_reason")
    work_type_in_task = _f("work_type_in_task")
    subdivision = _f("subdivision")
    due_date = _f("due_date")
    task_type = _f("task_type")
    file = form.get("file")

    missing = []
    for label, val in [("заказчик", customer), ("основание", visit_reason),
                       ("поручение", work_type_in_task), ("плановая дата выполнения", due_date),
                       ("тип поручения", task_type), ("подразделение заказчика", subdivision)]:
        if not val:
            missing.append(label)
    if missing:
        return Response(content=json.dumps(
            {"error": "Не заполнены поля: " + ", ".join(missing)}, ensure_ascii=False),
            media_type="application/json", status_code=400)

    filename = getattr(file, "filename", "") or ""
    if not filename.lower().endswith(".xlsx"):
        return Response(content=json.dumps({"error": "Нужен файл .xlsx"}, ensure_ascii=False),
                        media_type="application/json", status_code=400)

    content = await file.read()
    rows = read_register(content)
    if not rows:
        return Response(content=json.dumps({"error": "В файле нет строк"}, ensure_ascii=False),
                        media_type="application/json", status_code=400)

    form_ctx = {"customer": customer, "visit_reason": visit_reason,
                "work_type_in_task": work_type_in_task, "subdivision": subdivision, "due_date": due_date,
                "task_type": task_type}
    now = datetime.now()

    # Начальники отделений (dept -> ФИО) из mytra.db
    head_rows = await db_session.execute(text(
        "SELECT dept, full_name FROM users WHERE position LIKE '%Начальник%'"))
    head_map = {r[0]: r[1] for r in head_rows}

    inserted = 0
    feedback = []
    sand_session = sand_session_factory()
    year_suffix = now.strftime("%y")
    existing = (await sand_session.execute(text(
        "SELECT task_number FROM main_afl WHERE task_number LIKE :p"),
        {"p": f"%-{year_suffix}"})).fetchall()
    seq = max((int(n[0].split("-")[0]) for n in existing
               if n[0] and "-" in n[0] and n[0].split("-")[0].isdigit()), default=0) + 1
    for i, row in enumerate(rows, start=2):
        points, err = await find_points(sand_session, row)
        if err:
            feedback.append({"row": i, "object_code": row["object_code"],
                             "meter_serial_number": row["meter_serial_number"],
                             "tu_number": row["tu_number"], "reason": err})
            continue
        for p in points:
            if not (p.get("municipal_district") or "").strip():
                feedback.append({"row": i, "object_code": row["object_code"],
                                 "meter_serial_number": row["meter_serial_number"],
                                 "tu_number": row["tu_number"],
                                 "reason": "нет района у объекта"})
                continue
            if not (p.get("depts") or "").strip():
                feedback.append({"row": i, "object_code": row["object_code"],
                                 "meter_serial_number": row["meter_serial_number"],
                                 "tu_number": row["tu_number"],
                                 "reason": "нет отделения"})
                continue
            exists = await sand_session.execute(
                text("SELECT 1 FROM main_afl WHERE metering_point = :mp AND created_at = :created"),
                {"mp": p["tu_id"], "created": now.strftime("%Y-%m-%d")})
            if exists.first() is not None:
                feedback.append({"row": i, "object_code": row["object_code"],
                                 "meter_serial_number": row["meter_serial_number"],
                                 "tu_number": row["tu_number"],
                                 "reason": "уже загружено сегодня"})
                continue
            rec = build_main_afl_row(p, form_ctx, now, head_map)
            rec["task_number"] = f"{seq}-{year_suffix}"
            await sand_session.execute(text(INSERT_SQL), rec)
            inserted += 1
            seq += 1
    await sand_session.commit()
    await sand_session.close()

    resp = {"inserted": inserted, "feedback": feedback, "total": len(rows)}
    if feedback:
        resp["feedback_file_base64"] = feedback_xlsx_b64(filename, feedback)
        resp["feedback_filename"] = f"фидбек_УЛР_{now.strftime('%Y%m%d_%H%M%S')}.xlsx"
    return Response(content=json.dumps(resp, ensure_ascii=False), media_type="application/json")


@get("/ulr/execution", guards=[require_auth])
async def api_ulr_execution(request: Request, db_session: AsyncSession) -> Response:
    user = await get_current_user(request, db_session)
    if not user:
        raise NotAuthorizedException()

    where = "task_source = 'mytra'"
    params: dict = {}
    if user.effective_role in ("оператор", "работник"):
        names = [r[0] for r in (await db_session.execute(text(
            "SELECT executor_name FROM users WHERE locale = :locale AND executor_name IS NOT NULL"),
            {"locale": user.locale}))]
        if names:
            ph = ", ".join(f":e{i}" for i in range(len(names)))
            where += f" AND executor IN ({ph})"
            for i, n in enumerate(names):
                params[f"e{i}"] = n
        else:
            where += " AND 1=0"
    elif user.effective_role == "менеджер":
        where += " AND executor_organization = :dept"
        params["dept"] = user.dept

    # Справочники для дропдаунов (из mytra.db).
    wc_rows = await db_session.execute(text(
        "SELECT id, short FROM work_catalog WHERE kind = 'base'"))
    wc_short = {r[0]: r[1] for r in wc_rows}
    short_to_id = {r[1]: r[0] for r in wc_rows if r[1]}

    pos_ph = ", ".join(f":p{i}" for i in range(len(EXECUTOR_POSITIONS)))
    pos_params = {f"p{i}": p for i, p in enumerate(EXECUTOR_POSITIONS)}
    user_rows = await db_session.execute(text(
        f"SELECT dept, executor_name FROM users "
        f"WHERE executor_name IS NOT NULL AND executor_name != '' AND position IN ({pos_ph}) "
        f"ORDER BY executor_name"), pos_params)
    users_by_dept: dict = {}
    for dept, name in user_rows:
        users_by_dept.setdefault(dept or "", []).append(name)

    sand_session = sand_session_factory()
    result = await sand_session.execute(text(
        f"SELECT task_number, task_source, task_type, work_type_in_task, created_at, "
        f"due_date, customer, visit_reason, subscriber_type, grid, "
        f"personal_account, service_object_type, subscriber_name, address, "
        f"meter_model, meter_installation_place, violations, meter_type, "
        f"executor, executor_organization, co_executor, task_report, done_day, "
        f"reestr_number, status, contract_status, "
        f"COALESCE(norm, 0) + COALESCE(extra, 0) AS norm "
        f"FROM main_afl WHERE {where} ORDER BY CAST(task_number AS INTEGER)"), params)
    rows = [dict(r._mapping) for r in result]

    for row in rows:
        work_ids = resolve_work_ids(
            row.get("customer"), row.get("work_type_in_task"), row.get("task_type"),
            row.get("meter_type"), row.get("contract_status"))
        row["work_type_options"] = [
            {"id": wid, "short": wc_short.get(wid), "needs_co": wid in CO_EXECUTOR_WORK_IDS}
            for wid in work_ids if wid in wc_short
        ]
        row["work_type_options"].append({"id": None, "short": NO_EXECUTION, "needs_co": False})
        # Если текущий вид работ не входит в рассчитанный список (например, после «Заменить вид работ»),
        # добавляем его, чтобы дропдаун не сбрасывался на пустое.
        if row.get("task_report") and not any(o["short"] == row["task_report"] for o in row["work_type_options"]):
            row["work_type_options"].append({"id": None, "short": row["task_report"], "needs_co": False})
        row["executor_options"] = users_by_dept.get(row.get("executor_organization") or "", [])
        cur_id = short_to_id.get(row.get("task_report"))
        row["co_executor_required"] = row.get("meter_type") == "3ф" and cur_id in CO_EXECUTOR_WORK_IDS

    await sand_session.close()
    return Response(content=json.dumps({"rows": rows}, ensure_ascii=False), media_type="application/json")


@patch("/ulr/execution", guards=[require_auth])
async def api_ulr_update_execution(
    request: Request, db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    user = await get_current_user(request, db_session)
    if not user or user.effective_role not in ADMIN_ROLES:
        raise NotAuthorizedException()

    def _v(key):
        v = data.get(key)
        return (str(v).strip() if v is not None else "") or None

    task_number = _v("task_number")
    executor = _v("executor")
    co_executor = _v("co_executor")
    task_report = _v("task_report")
    done_day = _v("done_day")
    violations = _v("violations")

    if not task_number:
        return Response(content=json.dumps({"error": "Не указан номер задания"}, ensure_ascii=False),
                        media_type="application/json", status_code=400)

    # «Без исполнения» → дата = сегодня.
    if task_report == NO_EXECUTION:
        done_day = datetime.now().strftime("%Y-%m-%d")

    wc_rows = await db_session.execute(text(
        "SELECT id, short FROM work_catalog WHERE kind = 'base'"))
    short_to_id = {r[1]: r[0] for r in wc_rows if r[1]}

    norm_val = (await db_session.execute(text(
        "SELECT norm FROM work_catalog WHERE kind = 'base' AND short = :tr LIMIT 1"),
        {"tr": task_report})).scalar_one_or_none()
    sand_session = sand_session_factory()
    cur = (await sand_session.execute(text(
        "SELECT reestr_number, meter_type, verified, status_changed_at FROM main_afl WHERE task_number = :tn"),
        {"tn": task_number})).fetchone()
    if cur is None:
        return Response(content=json.dumps({"error": "Строка не найдена"}, ensure_ascii=False),
                        media_type="application/json", status_code=404)
    reestr_number, meter_type, cur_verified, cur_status_changed_at = cur[0], cur[1], cur[2], cur[3]
    if reestr_number:
        return Response(content=json.dumps(
            {"error": "Реестр уже присвоен — редактирование закрыто"}, ensure_ascii=False),
            media_type="application/json", status_code=400)

    co_required = meter_type == "3ф" and short_to_id.get(task_report) in CO_EXECUTOR_WORK_IDS
    status = compute_status(executor, done_day, task_report, co_executor, co_required, reestr_number)

    # Автор и время перехода в «Выполнено» — храним последние значения.
    if status == STATUS_DONE:
        verified = user.full_name
        status_changed_at = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    else:
        verified = cur_verified
        status_changed_at = cur_status_changed_at

    await sand_session.execute(text(
        "UPDATE main_afl SET executor = :executor, co_executor = :co_executor, "
        "task_report = :task_report, done_day = :done_day, violations = :violations, "
        "status = :status, verified = :verified, status_changed_at = :status_changed_at, "
        "norm = :norm, extra = 0 "
        "WHERE task_number = :tn"),
        {"executor": executor, "co_executor": co_executor, "task_report": task_report,
         "done_day": done_day, "violations": violations, "status": status,
         "verified": verified, "status_changed_at": status_changed_at, "norm": norm_val, "tn": task_number})
    await sand_session.commit()
    await sand_session.close()

    return Response(content=json.dumps({"success": True, "status": status}, ensure_ascii=False),
                    media_type="application/json")


@post("/ulr/reestr", guards=[require_auth])
async def api_ulr_reestr(
    request: Request, db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    user = await get_current_user(request, db_session)
    if not user or user.effective_role not in ADMIN_ROLES:
        raise NotAuthorizedException()

    task_numbers = [str(t).strip() for t in data.get("task_numbers", []) if t]
    if not task_numbers:
        return Response(content=json.dumps({"error": "Не выбраны строки"}, ensure_ascii=False),
                        media_type="application/json", status_code=400)

    # Локале исполнителя — из mytra.db.
    loc_rows = await db_session.execute(text(
        "SELECT executor_name, locale FROM users WHERE executor_name IS NOT NULL AND executor_name != ''"))
    locale_map = {r[0]: r[1] for r in loc_rows}

    year_suffix = datetime.now().strftime("%y")
    reestr_date = datetime.now().strftime("%Y-%m-%d")
    reestrs = []
    skipped = 0

    sand_session = sand_session_factory()
    names = ", ".join(f":tn{i}" for i in range(len(task_numbers)))
    params = {f"tn{i}": tn for i, tn in enumerate(task_numbers)}
    result = await sand_session.execute(text(
        f"SELECT task_number, customer, task_organization, task_report, executor_organization, "
        f"executor, reestr_number, status FROM main_afl WHERE task_number IN ({names})"), params)
    rows = [dict(r._mapping) for r in result]

    eligible = [r for r in rows if r.get("status") == STATUS_DONE and not r.get("reestr_number")]
    skipped = len(rows) - len(eligible)

    groups: dict = {}
    for r in eligible:
        locale = locale_map.get(r.get("executor") or "", "") or ""
        key = (r.get("task_organization"), locale, r.get("task_report"))
        groups.setdefault(key, []).append(r)

    for (task_org, locale, task_report), group in groups.items():
        tns = [r["task_number"] for r in group]
        display = f"{task_org or '-'} / {locale or '-'} / {task_report or 'Без категории'}"

        if task_report == NO_EXECUTION:
            rn = "Отклонён"
        else:
            pattern = f"%-{year_suffix}"
            existing = (await sand_session.execute(text(
                "SELECT reestr_number FROM main_afl WHERE reestr_number LIKE :p AND reestr_number != 'Отклонён'"),
                {"p": pattern})).fetchall()
            max_seq = max((int(n[0].split("-")[0]) for n in existing
                           if n[0] and "-" in n[0] and n[0].split("-")[0].isdigit()), default=0)
            rn = f"{max_seq + 1}-{year_suffix}"

        tn_names = ", ".join(f":rn{i}" for i in range(len(tns)))
        tn_params = {f"rn{i}": tn for i, tn in enumerate(tns)}
        await sand_session.execute(text(
            f"UPDATE main_afl SET reestr_number = :rn, reestr_date = :rd, status = :st "
            f"WHERE task_number IN ({tn_names})"),
            {"rn": rn, "rd": reestr_date, "st": STATUS_SENT, **tn_params})
        reestrs.append({"name": display, "reestr_number": rn, "count": len(tns)})

    await sand_session.commit()
    await sand_session.close()

    return Response(content=json.dumps(
        {"success": True, "reestrs": reestrs, "skipped": skipped, "reestr_date": reestr_date},
        ensure_ascii=False), media_type="application/json")


@post("/ulr/reestr/reset", guards=[require_auth])
async def api_ulr_reestr_reset(
    request: Request, db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    user = await get_current_user(request, db_session)
    if not user:
        raise NotAuthorizedException()

    task_numbers = [str(t).strip() for t in data.get("task_numbers", []) if t]
    if not task_numbers:
        return Response(content=json.dumps({"error": "Не выбраны строки"}, ensure_ascii=False),
                        media_type="application/json", status_code=400)

    sand_session = sand_session_factory()
    names = ", ".join(f":r{i}" for i in range(len(task_numbers)))
    params = {f"r{i}": tn for i, tn in enumerate(task_numbers)}
    result = await sand_session.execute(text(
        f"UPDATE main_afl SET reestr_number = NULL, reestr_date = NULL, status = :st "
        f"WHERE task_number IN ({names})"),
        {"st": STATUS_DONE, **params})
    await sand_session.commit()
    await sand_session.close()

    return Response(content=json.dumps({"success": True, "cleared": result.rowcount}, ensure_ascii=False),
                    media_type="application/json")


@patch("/ulr/task-report", guards=[require_auth])
async def api_ulr_task_report(
    request: Request, db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    user = await get_current_user(request, db_session)
    if not user or user.effective_role != "администратор":
        return Response(content=json.dumps({"error": "Нет прав"}, ensure_ascii=False),
                        media_type="application/json", status_code=403)

    task_number = (data.get("task_number") or "").strip()
    task_report = (data.get("task_report") or "").strip()
    if not task_number:
        return Response(content=json.dumps({"error": "Не указан номер задания"}, ensure_ascii=False),
                        media_type="application/json", status_code=400)

    norm_val = (await db_session.execute(text(
        "SELECT norm FROM work_catalog WHERE kind = 'base' AND short = :tr LIMIT 1"),
        {"tr": task_report})).scalar_one_or_none()
    sand_session = sand_session_factory()
    await sand_session.execute(text(
        "UPDATE main_afl SET task_report = :tr, reestr_number = NULL, reestr_date = NULL, "
        "status = :st, norm = :norm, extra = 0 "
        "WHERE task_number = :tn"),
        {"tr": task_report or None, "st": STATUS_DONE, "norm": norm_val, "tn": task_number})
    await sand_session.commit()
    await sand_session.close()

    return Response(content=json.dumps({"success": True}, ensure_ascii=False),
                    media_type="application/json")


ulr_router = Router("/api", route_handlers=[api_ulr_options, api_ulr_upload, api_ulr_execution, api_ulr_update_execution, api_ulr_reestr, api_ulr_reestr_reset, api_ulr_task_report])
