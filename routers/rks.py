"""РКС — эксперимент: загрузка РКС.xlsx + РКС УЛР.xlsx, накопление потребителей/заданий (sand.db)."""
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
from services.rks import (STATUS_ASSIGNED, STATUS_CREATED, STATUS_DONE, STATUS_SENT,
                          WORK_TYPES, ingest_rks, parse_rks, parse_rks_ulr)

ADMIN_ROLES = ("администратор", "специалист")
# Работники (оператор/работник) этих отделений тоже видят раздел РКС.
RKS_WORKER_DEPTS = ("Всеволожское отделение", "Сертоловское отделение")


async def _require_admin(request: Request, db_session: AsyncSession) -> None:
    user = await get_current_user(request, db_session)
    if not user:
        raise NotAuthorizedException()
    if user.effective_role in ADMIN_ROLES:
        return
    # Работники (оператор/работник) Всеволожского и Сертоловского отделений.
    if user.effective_role in ("оператор", "работник") and user.dept in RKS_WORKER_DEPTS:
        return
    raise NotAuthorizedException()


@post("/rks/upload", guards=[require_auth])
async def api_rks_upload(request: Request, db_session: AsyncSession) -> Response:
    await _require_admin(request, db_session)

    form = await request.form()
    file = form.get("file")
    ulr_file = form.get("ulr_file")
    task_type = (str(form.get("task_type") or "")).strip() or None

    filename = getattr(file, "filename", "") or ""
    if not filename.lower().endswith(".xlsx"):
        return Response(content=json.dumps({"error": "Нужен файл заданий РКС (.xlsx)"}, ensure_ascii=False),
                        media_type="application/json", status_code=400)

    content = await file.read()
    rows = parse_rks(content)
    if not rows:
        return Response(content=json.dumps({"error": "В файле РКС нет строк"}, ensure_ascii=False),
                        media_type="application/json", status_code=400)

    ulr_rows = []
    if ulr_file is not None:
        ulr_rows = parse_rks_ulr(await ulr_file.read())

    now = datetime.now()
    async with sand_session_factory() as sand_session:
        stats = await ingest_rks(sand_session, rows, ulr_rows, filename, now, task_type)

        # Маппинг РКС УЛР перезаписываем при каждой загрузке (актуальный срез).
        if ulr_rows:
            await sand_session.execute(text("DELETE FROM rks_ulr_ref"))
            for r in ulr_rows:
                await sand_session.execute(text(
                    "INSERT INTO rks_ulr_ref (energy_object_code, work_date, address, loaded_at) "
                    "VALUES (:energy_object_code, :work_date, :address, :loaded_at)"),
                    {"energy_object_code": r["energy_object_code"], "work_date": r["work_date"],
                     "address": r["address"], "loaded_at": now.strftime("%Y-%m-%d %H:%M:%S")})

        await sand_session.commit()

    return Response(content=json.dumps({"success": True, "stats": stats, "total": len(rows)},
                                       ensure_ascii=False),
                    media_type="application/json")


@get("/rks/summary", guards=[require_auth])
async def api_rks_summary(request: Request, db_session: AsyncSession) -> Response:
    await _require_admin(request, db_session)
    async with sand_session_factory() as sand_session:
        result = (await sand_session.execute(text(
            "SELECT (SELECT COUNT(*) FROM rks_consumer), "
            "(SELECT COUNT(*) FROM rks_consumer_point), "
            "(SELECT COUNT(*) FROM rks_task), "
            "(SELECT COUNT(*) FROM rks_task WHERE work_date IS NOT NULL), "
            "(SELECT COUNT(*) FROM rks_ulr_ref)"))).first()
    return Response(content=json.dumps({
        "consumers": result[0], "points": result[1], "tasks": result[2],
        "matched": result[3], "ulr_ref": result[4]}, ensure_ascii=False),
        media_type="application/json")


@get("/rks/consumers", guards=[require_auth])
async def api_rks_consumers(request: Request, db_session: AsyncSession,
                            limit: int = 100, offset: int = 0) -> Response:
    await _require_admin(request, db_session)
    async with sand_session_factory() as sand_session:
        total = (await sand_session.execute(text("SELECT COUNT(*) FROM rks_consumer"))).scalar()
        result = await sand_session.execute(text(
            "SELECT c.*, (SELECT COUNT(*) FROM rks_consumer_point p WHERE p.consumer_id = c.id) AS points_count "
            "FROM rks_consumer c ORDER BY c.id LIMIT :limit OFFSET :offset"),
            {"limit": limit, "offset": offset})
        consumers = [dict(r._mapping) for r in result]
    return Response(content=json.dumps({"total": total, "items": consumers}, ensure_ascii=False),
                    media_type="application/json")


@get("/rks/tasks", guards=[require_auth])
async def api_rks_tasks(request: Request, db_session: AsyncSession,
                        limit: int = 100, offset: int = 0) -> Response:
    await _require_admin(request, db_session)
    async with sand_session_factory() as sand_session:
        total = (await sand_session.execute(text("SELECT COUNT(*) FROM rks_task"))).scalar()
        result = await sand_session.execute(text(
            "SELECT t.*, p.address, p.meter_serial, p.meter_model, p.phase, c.contract_number, c.consumer_name, c.department, c.fl_yul, c.phone "
            "FROM rks_task t "
            "LEFT JOIN rks_consumer_point p ON p.id = t.point_id "
            "LEFT JOIN rks_consumer c ON c.id = p.consumer_id "
            "ORDER BY t.id LIMIT :limit OFFSET :offset"),
            {"limit": limit, "offset": offset})
        tasks = [dict(r._mapping) for r in result]
    return Response(content=json.dumps({"total": total, "items": tasks}, ensure_ascii=False),
                    media_type="application/json")


def _compute_status(executor, done_day, work_type, co_executor, co_required, reestr_number) -> str:
    if reestr_number:
        return STATUS_SENT
    if executor and done_day and work_type and (not co_required or co_executor):
        return STATUS_DONE
    if executor:
        return STATUS_ASSIGNED
    return STATUS_CREATED


@get("/rks/execution", guards=[require_auth])
async def api_rks_execution(request: Request, db_session: AsyncSession) -> Response:
    await _require_admin(request, db_session)

    exec_rows = await db_session.execute(text(
        "SELECT full_name FROM users WHERE position IN "
        "('Инженер 1 категории','Инженер 2 категории','Контролёр') ORDER BY full_name"))
    executor_options = [r[0] for r in exec_rows]
    work_type_options = [{"id": None, "short": w, "needs_co": False} for w in WORK_TYPES]

    async with sand_session_factory() as sand_session:
        result = await sand_session.execute(text(
            "SELECT t.*, p.address, p.meter_serial, p.meter_model, "
            "c.contract_number, c.consumer_name, c.fl_yul, c.department "
            "FROM rks_task t "
            "JOIN rks_consumer_point p ON p.id = t.point_id "
            "JOIN rks_consumer c ON c.id = p.consumer_id ORDER BY t.id"))
        rows = []
        for r in result.mappings():
            rows.append({
                "task_number": r["task_number"], "task_source": "rks", "task_type": r["task_type"],
                "work_type_in_task": r["work_type"], "created_at": r["created_at"],
                "due_date": r["due_date"], "customer": None,
                "visit_reason": r["letter_number"], "subscriber_type": r["fl_yul"],
                "grid": None, "personal_account": r["contract_number"],
                "service_object_type": None, "subscriber_name": r["consumer_name"],
                "address": r["address"], "meter_model": r["meter_model"],
                "meter_installation_place": None, "meter_serial_number": r["meter_serial"],
                "violations": r["violations"], "meter_type": None,
                "has_current_transformer": None, "meter_status": None,
                "executor": r["assignee"], "executor_organization": r["executor_organization"],
                "co_executor": r["co_executor"], "task_report": r["work_type"],
                "done_day": r["work_date"], "reestr_number": r["reestr_number"],
                "status": r["status"], "contract_status": None, "norm": None,
                "work_type_options": work_type_options,
                "executor_options": executor_options,
                "co_executor_required": False,
            })

    return Response(content=json.dumps({"rows": rows}, ensure_ascii=False),
                    media_type="application/json")


@patch("/rks/execution", guards=[require_auth])
async def api_rks_update_execution(
    request: Request, db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    await _require_admin(request, db_session)

    task_number = (data.get("task_number") or "").strip()
    if not task_number:
        return Response(content=json.dumps({"error": "Не указан номер задания"}, ensure_ascii=False),
                        media_type="application/json", status_code=400)

    async with sand_session_factory() as sand_session:
        cur = (await sand_session.execute(text(
            "SELECT assignee, co_executor, work_type, work_date, violations, reestr_number "
            "FROM rks_task WHERE task_number = :tn"), {"tn": task_number})).mappings().first()
        if cur is None:
            return Response(content=json.dumps({"error": "Задание не найдено"}, ensure_ascii=False),
                            media_type="application/json", status_code=404)

        executor = data.get("executor") if data.get("executor") is not None else cur["assignee"]
        co_executor = data.get("co_executor") if data.get("co_executor") is not None else cur["co_executor"]
        work_type = data.get("task_report") if data.get("task_report") is not None else cur["work_type"]
        done_day = data.get("done_day") if data.get("done_day") is not None else cur["work_date"]
        violations = data.get("violations") if data.get("violations") is not None else cur["violations"]

        status = _compute_status(executor, done_day, work_type, co_executor, False, cur["reestr_number"])

        await sand_session.execute(text(
            "UPDATE rks_task SET assignee = :executor, co_executor = :co_executor, "
            "work_type = :work_type, work_date = :done_day, violations = :violations, status = :status "
            "WHERE task_number = :tn"),
            {"executor": executor, "co_executor": co_executor, "work_type": work_type,
             "done_day": done_day, "violations": violations, "status": status, "tn": task_number})
        await sand_session.commit()

    return Response(content=json.dumps({"success": True, "status": status}, ensure_ascii=False),
                    media_type="application/json")


@get("/rks/options", guards=[require_auth])
async def api_rks_options(request: Request, db_session: AsyncSession) -> Response:
    await _require_admin(request, db_session)
    work_types = [{"short": w, "title": w, "customer": None} for w in WORK_TYPES]
    return Response(content=json.dumps(
        {"customers": [], "subdivisions": {}, "work_types": work_types, "assignment_types": {}},
        ensure_ascii=False), media_type="application/json")


@post("/rks/reestr", guards=[require_auth])
async def api_rks_reestr(
    request: Request, db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    await _require_admin(request, db_session)

    task_numbers = [str(t).strip() for t in data.get("task_numbers", []) if t]
    if not task_numbers:
        return Response(content=json.dumps({"error": "Не выбраны строки"}, ensure_ascii=False),
                        media_type="application/json", status_code=400)

    year_suffix = datetime.now().strftime("%y")
    reestr_date = datetime.now().strftime("%Y-%m-%d")

    async with sand_session_factory() as sand_session:
        names = ", ".join(f":tn{i}" for i in range(len(task_numbers)))
        params = {f"tn{i}": tn for i, tn in enumerate(task_numbers)}
        result = await sand_session.execute(text(
            f"SELECT task_number, work_type, assignee, reestr_number, status FROM rks_task "
            f"WHERE task_number IN ({names})"), params)
        rows = [dict(r._mapping) for r in result]

    eligible = [r for r in rows if r.get("status") == STATUS_DONE and not r.get("reestr_number")]
    skipped = len(rows) - len(eligible)

    groups: dict = {}
    for r in eligible:
        key = (r.get("assignee") or "", r.get("work_type") or "")
        groups.setdefault(key, []).append(r)

    reestrs = []
    async with sand_session_factory() as sand_session:
        existing = (await sand_session.execute(text(
            "SELECT reestr_number FROM rks_task WHERE reestr_number LIKE :p AND reestr_number != 'Отклонён'"),
            {"p": f"%-{year_suffix}"})).fetchall()
        max_seq = max((int(n[0].split("-")[0]) for n in existing
                       if n[0] and "-" in n[0] and n[0].split("-")[0].isdigit()), default=0)
        for (assignee, work_type), group in groups.items():
            tns = [r["task_number"] for r in group]
            max_seq += 1
            rn = f"{max_seq}-{year_suffix}"
            display = f"{assignee or '-'} / {work_type or 'Без категории'}"
            tn_names = ", ".join(f":rn{i}" for i in range(len(tns)))
            tn_params = {f"rn{i}": tn for i, tn in enumerate(tns)}
            await sand_session.execute(text(
                f"UPDATE rks_task SET reestr_number = :rn, reestr_date = :rd, status = :st "
                f"WHERE task_number IN ({tn_names})"),
                {"rn": rn, "rd": reestr_date, "st": STATUS_SENT, **tn_params})
            reestrs.append({"name": display, "reestr_number": rn, "count": len(tns)})
        await sand_session.commit()

    return Response(content=json.dumps(
        {"success": True, "reestrs": reestrs, "skipped": skipped, "reestr_date": reestr_date},
        ensure_ascii=False), media_type="application/json")


@post("/rks/reestr/reset", guards=[require_auth])
async def api_rks_reestr_reset(
    request: Request, db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    await _require_admin(request, db_session)

    task_numbers = [str(t).strip() for t in data.get("task_numbers", []) if t]
    if not task_numbers:
        return Response(content=json.dumps({"error": "Не выбраны строки"}, ensure_ascii=False),
                        media_type="application/json", status_code=400)

    async with sand_session_factory() as sand_session:
        names = ", ".join(f":r{i}" for i in range(len(task_numbers)))
        params = {f"r{i}": tn for i, tn in enumerate(task_numbers)}
        result = await sand_session.execute(text(
            f"UPDATE rks_task SET reestr_number = NULL, reestr_date = NULL, status = :st "
            f"WHERE task_number IN ({names})"), {"st": STATUS_DONE, **params})
        await sand_session.commit()

    return Response(content=json.dumps({"success": True, "cleared": result.rowcount}, ensure_ascii=False),
                    media_type="application/json")


@patch("/rks/task-report", guards=[require_auth])
async def api_rks_task_report(
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

    async with sand_session_factory() as sand_session:
        await sand_session.execute(text(
            "UPDATE rks_task SET work_type = :tr, reestr_number = NULL, reestr_date = NULL, "
            "status = :st WHERE task_number = :tn"),
            {"tr": task_report or None, "st": STATUS_DONE, "tn": task_number})
        await sand_session.commit()

    return Response(content=json.dumps({"success": True}, ensure_ascii=False),
                    media_type="application/json")


@post("/rks/due-date", guards=[require_auth])
async def api_rks_change_due_date(
    request: Request, db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    await _require_admin(request, db_session)

    task_numbers = [str(t).strip() for t in data.get("task_numbers", []) if t]
    due_date = (data.get("due_date") or "").strip()
    if not task_numbers:
        return Response(content=json.dumps({"error": "Не выбраны строки"}, ensure_ascii=False),
                        media_type="application/json", status_code=400)
    if not due_date:
        return Response(content=json.dumps({"error": "Не указана дата"}, ensure_ascii=False),
                        media_type="application/json", status_code=400)

    async with sand_session_factory() as sand_session:
        names = ", ".join(f":d{i}" for i in range(len(task_numbers)))
        params = {f"d{i}": tn for i, tn in enumerate(task_numbers)}
        result = await sand_session.execute(text(
            f"UPDATE rks_task SET due_date = :dd WHERE task_number IN ({names})"),
            {"dd": due_date, **params})
        await sand_session.commit()

    return Response(content=json.dumps({"success": True, "updated": result.rowcount}, ensure_ascii=False),
                    media_type="application/json")


@get("/rks/object-points", guards=[require_auth])
async def api_rks_object_points(request: Request, db_session: AsyncSession, task_number: str = "") -> Response:
    await _require_admin(request, db_session)

    async with sand_session_factory() as sand_session:
        task = (await sand_session.execute(text(
            "SELECT point_id FROM rks_task WHERE task_number = :tn"), {"tn": task_number})).mappings().first()
        if task is None:
            return Response(content=json.dumps({"error": "Задание не найдено"}, ensure_ascii=False),
                            media_type="application/json", status_code=404)
        point = (await sand_session.execute(text(
            "SELECT consumer_id FROM rks_consumer_point WHERE id = :pid"), {"pid": task["point_id"]})).mappings().first()
        if point is None:
            return Response(content=json.dumps({"error": "Точка не найдена"}, ensure_ascii=False),
                            media_type="application/json", status_code=404)
        points = (await sand_session.execute(text(
            "SELECT p.id, p.meter_serial, p.address, "
            "(SELECT t.task_number FROM rks_task t WHERE t.point_id = p.id AND t.status IN (:st1, :st2) LIMIT 1) AS active_task "
            "FROM rks_consumer_point p WHERE p.consumer_id = :cid ORDER BY p.id"),
            {"cid": point["consumer_id"], "st1": STATUS_CREATED, "st2": STATUS_ASSIGNED})).mappings().all()

    items = [{"tu_id": str(p["id"]), "tu_number": p["meter_serial"] or p["address"] or f"точка {p['id']}",
              "active_task": p["active_task"]} for p in points]
    return Response(content=json.dumps({"points": items}, ensure_ascii=False),
                    media_type="application/json")


@post("/rks/add-point", guards=[require_auth])
async def api_rks_add_point(
    request: Request, db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    await _require_admin(request, db_session)

    task_number = (data.get("task_number") or "").strip()
    tu_id = (data.get("tu_id") or "").strip()
    if not task_number or not tu_id:
        return Response(content=json.dumps({"error": "Не указаны параметры"}, ensure_ascii=False),
                        media_type="application/json", status_code=400)

    async with sand_session_factory() as sand_session:
        tpl = (await sand_session.execute(text(
            "SELECT * FROM rks_task WHERE task_number = :tn"), {"tn": task_number})).mappings().first()
        if tpl is None:
            return Response(content=json.dumps({"error": "Задание не найдено"}, ensure_ascii=False),
                            media_type="application/json", status_code=404)

        year_suffix = datetime.now().strftime("%y")
        existing = (await sand_session.execute(text(
            "SELECT task_number FROM rks_task WHERE task_number LIKE :p"), {"p": f"%-{year_suffix}"})).fetchall()
        seq = max((int(n[0].split("-")[0]) for n in existing
                   if n[0] and "-" in n[0] and n[0].split("-")[0].isdigit()), default=0) + 1
        new_tn = f"{seq}-{year_suffix}"

        await sand_session.execute(text(
            "INSERT INTO rks_task (point_id, task_number, month, work_type, work_type_raw, note, "
            "letter_number, work_date, match_source, status, created_at, source_file, source_row) "
            "VALUES (:point_id, :task_number, :month, :work_type, :work_type_raw, :note, :letter_number, "
            ":work_date, :match_source, :status, :created_at, :source_file, :source_row)"),
            {"point_id": int(tu_id), "task_number": new_tn, "month": tpl["month"],
             "work_type": tpl["work_type"], "work_type_raw": tpl["work_type_raw"],
             "note": tpl["note"], "letter_number": tpl["letter_number"],
             "work_date": tpl["work_date"], "match_source": tpl["match_source"],
             "status": STATUS_CREATED, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
             "source_file": tpl["source_file"], "source_row": tpl["source_row"]})
        await sand_session.commit()

    return Response(content=json.dumps({"success": True, "task_number": new_tn}, ensure_ascii=False),
                    media_type="application/json")


@post("/rks/remove-control", guards=[require_auth])
async def api_rks_remove_control(
    request: Request, db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    await _require_admin(request, db_session)
    # В РКС нет цикла КРО — заглушка для паритета интерфейса с УЛР.
    return Response(content=json.dumps({"success": True, "deleted": 0}, ensure_ascii=False),
                    media_type="application/json")


rks_router = Router("/api", route_handlers=[
    api_rks_upload, api_rks_summary, api_rks_consumers, api_rks_tasks,
    api_rks_execution, api_rks_update_execution, api_rks_options,
    api_rks_reestr, api_rks_reestr_reset, api_rks_task_report,
    api_rks_change_due_date, api_rks_object_points, api_rks_add_point,
    api_rks_remove_control,
])
