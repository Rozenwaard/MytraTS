"""УЛР — загрузка реестра: справочники для формы и приём файла с матчингом в main_afl."""
import json
from datetime import datetime

from litestar import Router
from litestar.connection import Request
from litestar.exceptions import NotAuthorizedException
from litestar.handlers import get, post
from litestar.response import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from data.config import sand_session_factory
from deps import get_current_user, require_auth
from services.ulr import INSERT_SQL, build_main_afl_row, feedback_xlsx_b64, find_points, read_register

CUSTOMERS = ["ПСК", "РЛЭ"]
GRIDS = ["-", "ГтЭС", "КнЭС", "НлЭС", "СЭС", "ТхЭС", "ЮЭС", "ВЭС", "ЛОЭСК", "Оборонэнерго"]
# Виды работ, которые не показываем в выпадающем списке «Поручение» формы УЛР.
EXCLUDED_WORK_TYPES = ("недопуск", "бездог")
ADMIN_ROLES = ("администратор", "специалист")


async def _require_role(request: Request, db_session: AsyncSession) -> None:
    user = await get_current_user(request, db_session)
    if not user or user.effective_role not in ADMIN_ROLES:
        raise NotAuthorizedException()


@get("/ulr/options", guards=[require_auth])
async def api_ulr_options(request: Request, db_session: AsyncSession) -> Response:
    await _require_role(request, db_session)
    async with sand_session_factory() as session:
        result = await session.execute(text(
            "SELECT short, title, customer FROM work_catalog WHERE kind = 'base' ORDER BY id"))
        work_types = sorted(
            (
                {"short": r[0], "title": r[1], "customer": r[2]}
                for r in result
                if not any(term in (r[0] or "").lower() for term in EXCLUDED_WORK_TYPES)
            ),
            key=lambda w: (w["short"] or "").lower(),
        )
    return Response(content=json.dumps(
        {"customers": CUSTOMERS, "grids": GRIDS, "work_types": work_types},
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
    grid = _f("grid")
    due_date = _f("due_date")
    file = form.get("file")

    missing = []
    for label, val in [("заказчик", customer), ("основание", visit_reason),
                       ("поручение", work_type_in_task), ("плановая дата выполнения", due_date)]:
        if not val:
            missing.append(label)
    if customer == "РЛЭ" and not grid:
        missing.append("филиал сетей (для РЛЭ)")
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
                "work_type_in_task": work_type_in_task, "grid": grid, "due_date": due_date}
    now = datetime.now()

    # Начальники отделений (dept -> ФИО) из mytra.db
    head_rows = await db_session.execute(text(
        "SELECT dept, full_name FROM users WHERE position LIKE '%Начальник%'"))
    head_map = {r[0]: r[1] for r in head_rows}

    inserted = 0
    feedback = []
    async with sand_session_factory() as session:
        for i, row in enumerate(rows, start=2):
            points, err = await find_points(session, row)
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
                rec = build_main_afl_row(p, form_ctx, now, head_map)
                exists = await session.execute(
                    text("SELECT 1 FROM main_afl WHERE task_number = :tn"), {"tn": rec["task_number"]})
                if exists.first() is not None:
                    feedback.append({"row": i, "object_code": row["object_code"],
                                     "meter_serial_number": row["meter_serial_number"],
                                     "tu_number": row["tu_number"],
                                     "reason": f"уже загружено сегодня ({rec['task_number']})"})
                    continue
                await session.execute(text(INSERT_SQL), rec)
                inserted += 1
        await session.commit()

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

    where = "1=1"
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

    async with sand_session_factory() as session:
        result = await session.execute(text(
            f"SELECT task_number, customer, work_type_in_task, personal_account, address, executor, "
            f"task_report, done_day, reestr_number, errors, norm, co_executor, acts "
            f"FROM main_afl WHERE {where} ORDER BY task_number"), params)
        rows = [dict(r._mapping) for r in result]
    return Response(content=json.dumps({"rows": rows}, ensure_ascii=False), media_type="application/json")


ulr_router = Router("/api", route_handlers=[api_ulr_options, api_ulr_upload, api_ulr_execution])
