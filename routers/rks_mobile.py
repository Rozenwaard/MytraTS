"""Мобильный контур РКС: привязка устройств, синк заданий, приём отчётов и фото.

Авторизация мобильных запросов — по токену устройства (Bearer / X-Device-Token),
пароль полевым не выдаём. Админский эндпоинт выдачи кода — под session + ролью.
"""
import hashlib
import json
import os
import secrets
from datetime import datetime, timedelta

from litestar import Router
from litestar.connection import Request
from litestar.enums import RequestEncodingType
from litestar.exceptions import NotAuthorizedException
from litestar.handlers import get, post
from litestar.params import Body
from litestar.response import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from data.config import sand_session_factory
from deps import get_current_user, require_auth
from services.rks import (ALCOR_TITLE, DICT_KINDS, PHOTOS_DIR, STATUS_ASSIGNED,
                          STATUS_CREATED, STATUS_DONE, STATUS_IN_WORK, STATUS_MP,
                          STATUS_SENT, resolve_short)

ADMIN_ROLES = ("администратор", "специалист")

# Колонки отчёта (кроме client_op_id/device_id/task_number/created_at/submitted_at).
REPORT_FIELDS = [
    "status", "object_detected", "object_present", "object_in_operation", "object_purpose",
    "is_connected", "connected_to_mkd", "inspection_admitted", "network_object_type", "network_object_name",
    "meter_installation_place", "meter_inspection_results", "t1", "t2", "t3", "final_meter_status",
    "seals", "last_verification_date", "meter_ownership", "meter_model", "meter_type",
    "has_current_transformer", "has_voltage_transformer", "violations", "violation_type", "acts",
    "done_day", "co_executor", "task_report", "lat", "lng", "h3_res12", "satellites", "is_mock", "comment",
    "additional_works", "contract", "result", "seal_place", "seal_type", "seal_number",
    "seal_installed", "new_vpu_installed",
]


def _extract_token(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (request.headers.get("x-device-token") or "").strip()


async def _auth_device(request: Request, db_session: AsyncSession, sand_session) -> dict | None:
    token = _extract_token(request)
    if not token:
        return None
    dev = (await sand_session.execute(text(
        "SELECT * FROM rks_devices WHERE token = :t AND active = 1"), {"t": token})).mappings().first()
    if dev is None:
        return None
    user = (await db_session.execute(text(
        "SELECT id, full_name, staff_id, position, dept FROM users WHERE id = :uid"),
        {"uid": dev["user_id"]})).mappings().first()
    if user is None:
        return None
    return {"device": dev, "user": user}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@post("/rks/enroll-code", guards=[require_auth])
async def api_rks_enroll_code(request: Request, db_session: AsyncSession,
                              data: dict = Body(media_type=RequestEncodingType.JSON)) -> Response:
    user = await get_current_user(request, db_session)
    if not user:
        raise NotAuthorizedException()

    user_id = data.get("user_id")
    if not user_id:
        return Response(content=json.dumps({"error": "Не указан сотрудник"}, ensure_ascii=False),
                        media_type="application/json", status_code=400)

    target = (await db_session.execute(text(
        "SELECT id, full_name, dept FROM users WHERE id = :uid"), {"uid": user_id})).mappings().first()
    if target is None:
        return Response(content=json.dumps({"error": "Сотрудник не найден"}, ensure_ascii=False),
                        media_type="application/json", status_code=404)

    # Право выдачи: админ/специалист (любой отдел) или сотрудник своего отдела.
    if user.effective_role not in ADMIN_ROLES and target["dept"] != user.dept:
        raise NotAuthorizedException()

    code = secrets.token_hex(3).upper()
    expires_at = (datetime.now() + timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
    async with sand_session_factory() as sand_session:
        await sand_session.execute(text(
            "INSERT INTO rks_enrollments (code, user_id, created_at, expires_at, used) "
            "VALUES (:code, :user_id, :created_at, :expires_at, 0)"),
            {"code": code, "user_id": user_id, "created_at": _now(), "expires_at": expires_at})
        await sand_session.commit()

    return Response(content=json.dumps(
        {"code": code, "expires_at": expires_at, "full_name": target["full_name"]}, ensure_ascii=False),
        media_type="application/json")


@post("/m/1/enroll")
async def api_m_enroll(request: Request, db_session: AsyncSession,
                       data: dict = Body(media_type=RequestEncodingType.JSON)) -> Response:
    code = (data.get("code") or "").strip().upper()
    device_id = (data.get("device_id") or "").strip()
    platform = (data.get("platform") or "").strip()
    app_version = (data.get("app_version") or "").strip()
    if not code or not device_id:
        return Response(content=json.dumps({"error": "Код и device_id обязательны"}, ensure_ascii=False),
                        media_type="application/json", status_code=400)

    async with sand_session_factory() as sand_session:
        enr = (await sand_session.execute(text(
            "SELECT * FROM rks_enrollments WHERE code = :c"), {"c": code})).mappings().first()
        if enr is None or enr["used"] or (enr["expires_at"] and enr["expires_at"] < _now()):
            return Response(content=json.dumps({"error": "Код недействителен или истёк"}, ensure_ascii=False),
                            media_type="application/json", status_code=400)
        existing = (await sand_session.execute(text(
            "SELECT id FROM rks_devices WHERE device_id = :d"), {"d": device_id})).mappings().first()
        if existing is not None:
            return Response(content=json.dumps({"error": "Устройство уже привязано"}, ensure_ascii=False),
                            media_type="application/json", status_code=400)

        token = secrets.token_urlsafe(32)
        await sand_session.execute(text(
            "INSERT INTO rks_devices (user_id, device_id, token, platform, app_version, created_at, last_seen_at, active) "
            "VALUES (:user_id, :device_id, :token, :platform, :app_version, :created_at, :last_seen_at, 1)"),
            {"user_id": enr["user_id"], "device_id": device_id, "token": token,
             "platform": platform, "app_version": app_version,
             "created_at": _now(), "last_seen_at": _now()})
        await sand_session.execute(text(
            "UPDATE rks_enrollments SET used = 1, used_at = :ts WHERE id = :id"),
            {"ts": _now(), "id": enr["id"]})
        await sand_session.execute(text(
            "INSERT INTO rks_event_log (device_id, event_type, payload, created_at) "
            "VALUES (:device_id, 'enroll', :payload, :created_at)"),
            {"device_id": device_id, "payload": json.dumps({"user_id": enr["user_id"]}, ensure_ascii=False),
             "created_at": _now()})
        await sand_session.commit()

    user = (await db_session.execute(text(
        "SELECT full_name, staff_id FROM users WHERE id = :uid"), {"uid": enr["user_id"]})).mappings().first()
    return Response(content=json.dumps(
        {"token": token, "user": {"full_name": user["full_name"], "staff_id": user["staff_id"]}}, ensure_ascii=False),
        media_type="application/json")

@get("/m/1/sync")
async def api_m_sync(request: Request, db_session: AsyncSession) -> Response:
    async with sand_session_factory() as sand_session:
        auth = await _auth_device(request, db_session, sand_session)
        if auth is None:
            return Response(content=json.dumps({"error": "Не авторизовано"}, ensure_ascii=False),
                            media_type="application/json", status_code=401)
        full_name = auth["user"]["full_name"]

        rows = (await sand_session.execute(text(
            "SELECT t.*, p.meter_serial, p.address, p.meter_model, p.phase, "
            "c.consumer_name, c.contract_number, c.energy_object_code, c.fl_yul, c.phone, "
            "(SELECT r.result FROM rks_mobile_reports r WHERE r.task_number = t.task_number "
            " ORDER BY r.id DESC LIMIT 1) AS last_result, "
            "(SELECT COUNT(*) FROM rks_mobile_reports r WHERE r.task_number = t.task_number "
            " AND r.result = 'недопуск') AS nedopusk_count "
            "FROM rks_task t "
            "JOIN rks_consumer_point p ON p.id = t.point_id "
            "JOIN rks_consumer c ON c.id = p.consumer_id "
            "WHERE t.task_number IN (SELECT task_number FROM rks_task_assignees WHERE assignee = :fn) "
            "AND t.status IN (:st1, :st2, :st3) ORDER BY t.id"),
            {"fn": full_name, "st1": STATUS_ASSIGNED, "st2": STATUS_MP, "st3": STATUS_IN_WORK})).mappings().all()

        assigned_tns = [r["task_number"] for r in rows if r["status"] == STATUS_ASSIGNED]
        if assigned_tns:
            names = ", ".join(f":tn{i}" for i in range(len(assigned_tns)))
            params = {f"tn{i}": tn for i, tn in enumerate(assigned_tns)}
            await sand_session.execute(text(
                f"UPDATE rks_task SET status = :st WHERE task_number IN ({names})"),
                {"st": STATUS_MP, **params})

        await sand_session.execute(text(
            "UPDATE rks_devices SET last_seen_at = :ts WHERE id = :id"),
            {"ts": _now(), "id": auth["device"]["id"]})
        await sand_session.commit()

        # Справочники мобильного отчёта (sand.db).
        dicts = {}
        for kind in DICT_KINDS:
            dicts[kind] = [dict(r) for r in (await sand_session.execute(text(
                "SELECT code, title FROM rks_dict WHERE kind = :k ORDER BY id"),
                {"k": kind})).mappings().all()]

    # Нормативы — work_catalog (mytra.db): база по виду работ + допработы + Алькор.
    # RKS-работы = работы РЛЭ (ПСК — на вырост, не учитываем).
    base_by_short = {r["short"]: (r["norm"] or 0) for r in (await db_session.execute(text(
        "SELECT short, norm FROM work_catalog WHERE kind = 'base' AND customer = 'РЛЭ'"))).mappings().all()}
    extra_by_key = {r["short"] or r["title"]: r for r in (await db_session.execute(text(
        "SELECT short, title, norm, kind FROM work_catalog WHERE kind IN ('additional', 'replacement')"))).mappings().all()}

    alcor = 5
    alcor_row = (await db_session.execute(text(
        "SELECT norm FROM work_catalog WHERE short = :t LIMIT 1"), {"t": ALCOR_TITLE})).mappings().first()
    if alcor_row and alcor_row["norm"] is not None:
        alcor = alcor_row["norm"]

    for item in dicts.get("additional_work", []):
        row = extra_by_key.get(item["code"])
        item["norm"] = (row["norm"] or 0) if row else 0
        item["kind"] = row["kind"] if row else None

    models = [{"model": r["meter_model"], "phase": r["phase"]} for r in (await db_session.execute(text(
        "SELECT meter_model, phase FROM meter_model_phase ORDER BY meter_model"))).mappings().all()]

    tasks = [{
        "task_number": r["task_number"], "work_type": r["work_type"],
        "task_type": r["task_type"], "phase": r["phase"],
        "due_date": r["due_date"], "status": r["status"],
        "subscriber_name": r["consumer_name"], "address": r["address"],
        "meter_serial": r["meter_serial"], "meter_model": r["meter_model"],
        "contract_number": r["contract_number"], "energy_object_code": r["energy_object_code"], "fl_yul": r["fl_yul"], "phone": r["phone"],
        "last_result": r["last_result"], "nedopusk_count": r["nedopusk_count"],
        "letter_number": r["letter_number"], "note": r["note"],
        "norm": base_by_short.get(resolve_short(r["work_type"], r["task_type"], r["phase"]), 0),
    } for r in rows]

    return Response(content=json.dumps(
        {"tasks": tasks, "dicts": dicts, "alcor": alcor,
         "models": models,
         "base_works": [{"short": k, "norm": v} for k, v in base_by_short.items()]},
        ensure_ascii=False),
        media_type="application/json")


@post("/m/1/reports")
async def api_m_reports(request: Request, db_session: AsyncSession,
                        data: dict = Body(media_type=RequestEncodingType.JSON)) -> Response:
    client_op_id = (data.get("client_op_id") or "").strip()
    task_number = (data.get("task_number") or "").strip()
    if not client_op_id or not task_number:
        return Response(content=json.dumps({"error": "client_op_id и task_number обязательны"}, ensure_ascii=False),
                        media_type="application/json", status_code=400)

    async with sand_session_factory() as sand_session:
        auth = await _auth_device(request, db_session, sand_session)
        if auth is None:
            return Response(content=json.dumps({"error": "Не авторизовано"}, ensure_ascii=False),
                            media_type="application/json", status_code=401)

        # Guard: не даём поздним/чужим отчётам закрывать или откатывать задание.
        task_row = (await sand_session.execute(text(
            "SELECT status FROM rks_task WHERE task_number = :tn"),
            {"tn": task_number})).mappings().first()
        if task_row is None:
            return Response(content=json.dumps({"error": "Задание не найдено", "closed": True}, ensure_ascii=False),
                            media_type="application/json", status_code=404)
        if task_row["status"] in (STATUS_DONE, STATUS_SENT):
            return Response(content=json.dumps({"error": "Задание уже выполнено или отправлено", "closed": True}, ensure_ascii=False),
                            media_type="application/json", status_code=409)
        # Работник должен быть в наборе исполнителей задания.
        is_assigned = (await sand_session.execute(text(
            "SELECT 1 FROM rks_task_assignees WHERE task_number = :tn AND assignee = :fn"),
            {"tn": task_number, "fn": auth["user"]["full_name"]})).scalar()
        if not is_assigned:
            return Response(content=json.dumps({"error": "Задание передано другому исполнителю", "closed": True}, ensure_ascii=False),
                            media_type="application/json", status_code=409)

        dup = (await sand_session.execute(text(
            "SELECT client_op_id FROM rks_mobile_reports WHERE client_op_id = :cid"),
            {"cid": client_op_id})).mappings().first()
        if dup is not None:
            return Response(content=json.dumps({"success": True, "duplicate": True}, ensure_ascii=False),
                            media_type="application/json")

        fields = {k: data.get(k) for k in REPORT_FIELDS}
        columns = ["client_op_id", "device_id", "task_number", "created_at", "submitted_at"] + REPORT_FIELDS
        placeholders = ", ".join(f":{c}" for c in columns)
        values = {"client_op_id": client_op_id, "device_id": auth["device"]["device_id"],
                  "task_number": task_number, "created_at": _now(), "submitted_at": _now()}
        values.update(fields)
        await sand_session.execute(text(
            f"INSERT INTO rks_mobile_reports ({', '.join(columns)}) VALUES ({placeholders})"), values)

        report_status = (data.get("status") or "").strip()
        new_task_status = STATUS_DONE if report_status == "выполнено" else STATUS_IN_WORK
        await sand_session.execute(text(
            "UPDATE rks_task SET status = :st WHERE task_number = :tn"),
            {"st": new_task_status, "tn": task_number})

        await sand_session.execute(text(
            "INSERT INTO rks_event_log (device_id, event_type, payload, created_at) "
            "VALUES (:device_id, 'report', :payload, :created_at)"),
            {"device_id": auth["device"]["device_id"],
             "payload": json.dumps({"client_op_id": client_op_id, "task_number": task_number}, ensure_ascii=False),
             "created_at": _now()})
        await sand_session.commit()

    return Response(content=json.dumps({"success": True}, ensure_ascii=False),
                    media_type="application/json")


@post("/m/1/photos")
async def api_m_photos(request: Request, db_session: AsyncSession) -> Response:
    form = await request.form()
    client_op_id = (str(form.get("client_op_id") or "")).strip()
    task_number = (str(form.get("task_number") or "")).strip()
    photo_type = (str(form.get("photo_type") or "")).strip() or "general"
    file = form.get("file")
    if not client_op_id or file is None:
        return Response(content=json.dumps({"error": "client_op_id и file обязательны"}, ensure_ascii=False),
                        media_type="application/json", status_code=400)

    content = await file.read()
    sha = hashlib.sha256(content).hexdigest()

    async with sand_session_factory() as sand_session:
        auth = await _auth_device(request, db_session, sand_session)
        if auth is None:
            return Response(content=json.dumps({"error": "Не авторизовано"}, ensure_ascii=False),
                            media_type="application/json", status_code=401)

        rel_dir = os.path.join(task_number, client_op_id) if task_number else client_op_id
        abs_dir = os.path.join(PHOTOS_DIR, rel_dir)
        os.makedirs(abs_dir, exist_ok=True)
        ctype = (file.content_type or "").lower()
        ext = "webp" if "webp" in ctype else "jpg"
        filename = f"{sha}.{ext}"
        path = os.path.join(rel_dir, filename)
        with open(os.path.join(abs_dir, filename), "wb") as f:
            f.write(content)

        await sand_session.execute(text(
            "INSERT INTO rks_mobile_photos (report_id, task_number, photo_type, path, sha256, created_at) "
            "VALUES (:report_id, :task_number, :photo_type, :path, :sha256, :created_at)"),
            {"report_id": client_op_id, "task_number": task_number, "photo_type": photo_type,
             "path": path, "sha256": sha, "created_at": _now()})
        await sand_session.commit()

    return Response(content=json.dumps({"success": True, "sha256": sha}, ensure_ascii=False),
                    media_type="application/json")


@post("/m/1/return")
async def api_m_return(request: Request, db_session: AsyncSession,
                       data: dict = Body(media_type=RequestEncodingType.JSON)) -> Response:
    task_number = (data.get("task_number") or "").strip()
    reason = (data.get("reason") or "").strip()
    if not task_number or not reason:
        return Response(content=json.dumps({"error": "task_number и reason обязательны"}, ensure_ascii=False),
                        media_type="application/json", status_code=400)

    async with sand_session_factory() as sand_session:
        auth = await _auth_device(request, db_session, sand_session)
        if auth is None:
            return Response(content=json.dumps({"error": "Не авторизовано"}, ensure_ascii=False),
                            media_type="application/json", status_code=401)
        full_name = auth["user"]["full_name"]
        owned = (await sand_session.execute(text(
            "SELECT task_number FROM rks_task WHERE task_number = :tn AND assignee = :fn"),
            {"tn": task_number, "fn": full_name})).mappings().first()
        if owned is None:
            return Response(content=json.dumps({"error": "Задание не найдено или уже не за вами"}, ensure_ascii=False),
                            media_type="application/json", status_code=404)
        await sand_session.execute(text(
            "UPDATE rks_task SET status = :st, assignee = NULL WHERE task_number = :tn"),
            {"st": STATUS_CREATED, "tn": task_number})
        await sand_session.execute(text(
            "INSERT INTO rks_event_log (device_id, event_type, payload, created_at) "
            "VALUES (:device_id, 'return', :payload, :created_at)"),
            {"device_id": auth["device"]["device_id"],
             "payload": json.dumps({"task_number": task_number, "reason": reason}, ensure_ascii=False),
             "created_at": _now()})
        await sand_session.commit()

    return Response(content=json.dumps({"success": True}, ensure_ascii=False),
                    media_type="application/json")


@get("/mytrago/workers", guards=[require_auth])
async def api_mytrago_workers(request: Request, db_session: AsyncSession) -> Response:
    user = await get_current_user(request, db_session)
    if not user:
        raise NotAuthorizedException()
    org_dept = "Отдел организации"
    if user.effective_role in ADMIN_ROLES:
        rows = (await db_session.execute(text(
            "SELECT id, full_name, staff_id, position, dept, locale FROM users "
            "WHERE dept != :org ORDER BY dept, full_name"),
            {"org": org_dept})).mappings().all()
    else:
        rows = (await db_session.execute(text(
            "SELECT id, full_name, staff_id, position, dept, locale FROM users "
            "WHERE dept = :dept AND dept != :org ORDER BY full_name"),
            {"dept": user.dept, "org": org_dept})).mappings().all()
    return Response(content=json.dumps({"workers": [dict(r) for r in rows]}, ensure_ascii=False),
                    media_type="application/json")


mobile_router = Router("/api", route_handlers=[
    api_rks_enroll_code, api_m_enroll, api_m_sync, api_m_reports, api_m_photos,
    api_m_return, api_mytrago_workers,
])