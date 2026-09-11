import asyncio
import calendar
import io
import json
import uuid
import zipfile
from datetime import datetime
from urllib.parse import quote

from litestar import Router
from litestar.connection import Request
from litestar.datastructures import UploadFile
from litestar.enums import RequestEncodingType
from litestar.handlers import get, post
from litestar.params import Body
from litestar.response import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from deps import get_current_user, require_auth
from sql import norm_name
from services.dashboard import generate_recheck_xlsx
from services.reestr import generate_dop_report_xlsx_bytes, generate_fin_report_xlsx_bytes
from services.report_check import BALANCE_ERRORS, check_row, join_errors, STOP_FACTOR_REGIONS, STOP_FACTOR_DISTRICTS


def _normal_work_types_clause():
    """IN-условие по «нормальным» видам работ (base-тарифы carte)."""
    return "task_report IN (SELECT title FROM carte WHERE kind = 'base')", {}


def _stop_zone_clause():
    """Зона стоп-фактора (как в дашборде): регион СПб + ЛО Гатчинский район."""
    regions = sorted(STOP_FACTOR_REGIONS)
    districts = sorted(STOP_FACTOR_DISTRICTS)
    r_names = [f"zr{i}" for i in range(len(regions))]
    d_names = [f"zd{i}" for i in range(len(districts))]
    params = {**dict(zip(r_names, regions)), **dict(zip(d_names, districts))}
    r_in = ", ".join(f":{n}" for n in r_names)
    d_in = ", ".join(f":{n}" for n in d_names)
    return f"(region IN ({r_in}) OR municipal_district IN ({d_in}))", params


def _locale_expr():
    return f"COALESCE((SELECT locale FROM users WHERE {norm_name('users.full_name')} = {norm_name('main_afl.executor')} LIMIT 1), '(без локали)')"


def _cost_expr():
    """SQL-выражение стоимости строки: цена из carte.price (0 — если цены нет)."""
    return "COALESCE((SELECT price FROM carte WHERE carte.title = main_afl.task_report LIMIT 1), 0)", {}


def _period_clause(period: str):
    """Область выборки Финотчёта.

    Пустой period («Выберите период») → строки, ещё НЕ включённые в отчёт
    (report пустой) — то есть текущая незакрытая работа.
    Заданный period → строки этого отчётного периода (report = «ГГГГ ММ»).

    Возвращает (clause, period_fmt, params).
    """
    period_fmt = period.strip().replace("-", " ") if period else ""
    if period_fmt:
        return "report = :period", period_fmt, {"period": period_fmt}
    return "(report IS NULL OR report = '')", "", {}


def _period_end(period: str) -> str:
    """Последний день выбранного периода 'ГГГГ-ММ' в виде 'ГГГГ-ММ-ДД'.

    Нужен для фильтра done_day <= конец периода (done_day хранится как
    'ГГГГ-ММ-ДД', поэтому сравнение строками корректно).
    """
    year, month = (int(x) for x in period.strip().split("-"))
    return f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"


async def _next_period(db_session: AsyncSession) -> str:
    """Следующий отчётный период после последнего в main_afl (формат 'ГГГГ ММ')."""
    result = await db_session.execute(
        text("SELECT MAX(report) FROM main_afl WHERE report GLOB '[0-9][0-9][0-9][0-9] [0-9][0-9]'"))
    latest = result.scalar()
    if latest:
        year, month = (int(x) for x in latest.split(" "))
        month += 1
        if month > 12:
            year += 1
            month = 1
        return f"{year:04d} {month:02d}"
    now = datetime.now()
    return f"{now.year:04d} {now.month:02d}"


async def _card(db_session, where_sql, params, locale_expr, cost_expr):
    """Счётчик + раскладка по locale + сумма стоимости для одной плашки."""
    total = (await db_session.execute(
        text(f"SELECT COUNT(*) FROM main_afl WHERE {where_sql}"), params)).scalar()
    rows = await db_session.execute(
        text(f"SELECT {locale_expr} AS loc, COUNT(*) AS cnt FROM main_afl WHERE {where_sql} GROUP BY {locale_expr} ORDER BY cnt DESC"),
        params)
    cost = (await db_session.execute(
        text(f"SELECT COALESCE(SUM({cost_expr}), 0) FROM main_afl WHERE {where_sql}"), params)).scalar()
    return {"total": total, "by_locale": [{"locale": r[0], "count": r[1]} for r in rows], "cost": round(cost or 0, 2)}


@get("/fin-report", guards=[require_auth])
async def api_fin_report(request: Request, db_session: AsyncSession, period: str = "") -> Response:
    """Финотчёт: плашки + раскладка по видам работ в выбранной области.

    Без period — всё, что ещё не в отчёте; с period — данные этого отчётного периода.
    """
    user = await get_current_user(request, db_session)
    if user.effective_role != "администратор":
        return Response(content=json.dumps({"error": "Нет прав"}, ensure_ascii=False), media_type="application/json", status_code=403)

    wt_clause, wt_params = _normal_work_types_clause()
    zone_clause, zone_params = _stop_zone_clause()
    locale_expr = _locale_expr()
    cost_expr, cost_params = _cost_expr()
    p_clause, _period_fmt, p_params = _period_clause(period)
    base = {**cost_params, **p_params}
    base_wt = {**base, **wt_params}

    cards = {
        "completed": await _card(db_session, f"{p_clause} AND status IN ('Завершено','Закрыто')", base, locale_expr, cost_expr),
        "without_reestr": await _card(db_session, f"{p_clause} AND status IN ('Завершено','Закрыто') AND {wt_clause} AND reestr_number IS NULL", base_wt, locale_expr, cost_expr),
        "with_errors": await _card(db_session, f"{p_clause} AND status IN ('Завершено','Закрыто') AND {wt_clause} AND reestr_number IS NULL AND (errors IS NOT NULL AND errors != '') AND {zone_clause}", {**base_wt, **zone_params}, locale_expr, cost_expr),
        "ready": await _card(db_session, f"{p_clause} AND status IN ('Завершено','Закрыто') AND reestr_number IS NOT NULL AND reestr_number != 'Отклонён'", base, locale_expr, cost_expr),
    }

    work_types = []
    total_cost = 0.0
    rows = await db_session.execute(
        text(f"SELECT task_report, COUNT(*), COALESCE((SELECT price FROM carte WHERE carte.title = main_afl.task_report LIMIT 1), 0) AS price FROM main_afl WHERE {p_clause} AND status IN ('Завершено','Закрыто') AND {wt_clause} GROUP BY task_report ORDER BY COUNT(*) DESC"),
        {**wt_params, **p_params})
    for (tr, cnt, price) in rows:
        work_types.append({"label": tr, "count": cnt})
        total_cost += (price or 0.0) * (cnt or 0)

    cust_rows = await db_session.execute(
        text(f"SELECT customer, COALESCE(SUM({cost_expr}), 0) FROM main_afl WHERE {p_clause} AND status IN ('Завершено','Закрыто') AND {wt_clause} GROUP BY customer"),
        {**wt_params, **cost_params, **p_params})
    cost_by_cust = {r[0]: (r[1] or 0) for r in cust_rows}
    cost_psk = round(cost_by_cust.get("ПСК", 0), 2)
    cost_rle = round(cost_by_cust.get("РЛЭ", 0), 2)

    return Response(content=json.dumps({
        "cards": cards,
        "work_types": work_types,
        "total_cost": round(total_cost, 2),
        "cost_psk": cost_psk,
        "cost_rle": cost_rle,
    }, ensure_ascii=False, default=str), media_type="application/json")


@post("/fin-report/add", guards=[require_auth])
async def api_fin_report_add(
    request: Request, db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    """«Добавить в отчёт»: report = «ГГГГ ММ».

    С выбранным периодом — строки с номером реестра (не «Отклонён»), пустым report
    и done_day не новее конца периода (пустой done_day не попадает).
    Без периода — все строки «Готово к отчёту» (с реестром, не «Отклонён», пустым
    report) уходят в следующий отчётный период после последнего в main_afl.
    """
    user = await get_current_user(request, db_session)
    if user.effective_role != "администратор":
        return Response(content=json.dumps({"error": "Нет прав"}, ensure_ascii=False), media_type="application/json", status_code=403)

    period = (data.get("period") or "").strip()
    if period:
        period_fmt = period.replace("-", " ")
        period_end = _period_end(period)
        result = await db_session.execute(
            text("UPDATE main_afl SET report = :period WHERE reestr_number IS NOT NULL AND reestr_number != 'Отклонён' AND (report IS NULL OR report = '') AND done_day IS NOT NULL AND done_day <= :period_end"),
            {"period": period_fmt, "period_end": period_end})
    else:
        period_fmt = await _next_period(db_session)
        result = await db_session.execute(
            text("UPDATE main_afl SET report = :period WHERE reestr_number IS NOT NULL AND reestr_number != 'Отклонён' AND (report IS NULL OR report = '')"),
            {"period": period_fmt})
    await db_session.commit()

    return Response(content=json.dumps({"success": True, "updated": result.rowcount, "period": period_fmt}, ensure_ascii=False), media_type="application/json")


@post("/fin-report/discrepancies", guards=[require_auth])
async def api_fin_report_discrepancies(
    request: Request, db_session: AsyncSession,
    data: UploadFile = Body(media_type=RequestEncodingType.MULTI_PART),
) -> Response:
    """«Разногласия»: txt с номерами заданий (по одному на строку).

    Для найденных по task_number строк сбрасывает их в неисполненные:
    task_report = NULL, task_detail = 'Разногласия', reestr_number = 'Отклонён',
    reestr_date = NULL, report = NULL, norm = NULL, extra = NULL.
    """
    user = await get_current_user(request, db_session)
    if user.effective_role != "администратор":
        return Response(content=json.dumps({"error": "Нет прав"}, ensure_ascii=False), media_type="application/json", status_code=403)

    if not data or not data.filename.lower().endswith(".txt"):
        return Response(content=json.dumps({"error": "Нужен файл .txt"}, ensure_ascii=False), media_type="application/json", status_code=400)

    raw = await data.read()
    text_content = None
    for enc in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            text_content = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text_content is None:
        return Response(content=json.dumps({"error": "Не удалось прочитать txt (кодировка)"}, ensure_ascii=False), media_type="application/json", status_code=400)

    numbers = [line.strip() for line in text_content.splitlines() if line.strip()]
    if not numbers:
        return Response(content=json.dumps({"error": "Файл пуст"}, ensure_ascii=False), media_type="application/json", status_code=400)

    # Уникальные номера в порядке появления (дубли в файле не считаем дважды).
    unique = list(dict.fromkeys(numbers))

    batch_id = uuid.uuid4().hex
    snapshot = {}
    updated = 0
    not_found = 0

    for tn in unique:
        before = await db_session.execute(
            text("SELECT task_report, task_detail, reestr_number, reestr_date, report, norm, extra FROM main_afl WHERE task_number = :tn"),
            {"tn": tn},
        )
        row = before.mappings().first()
        if row is None:
            not_found += 1
            continue

        # Снимок «до» — для возможности отката.
        snapshot[tn] = dict(row)

        await db_session.execute(
            text("UPDATE main_afl SET task_report = NULL, task_detail = 'Разногласия', reestr_number = 'Отклонён', reestr_date = NULL, report = NULL, norm = NULL, extra = NULL WHERE task_number = :tn"),
            {"tn": tn},
        )
        updated += 1

    if snapshot:
        await db_session.execute(
            text("INSERT INTO discrepancies_log (batch_id, payload, created_at) VALUES (:batch_id, :payload, :created_at)"),
            {"batch_id": batch_id, "payload": json.dumps(snapshot, ensure_ascii=False), "created_at": datetime.now().isoformat(timespec="seconds")},
        )

    await db_session.commit()

    return Response(content=json.dumps({"success": True, "updated": updated, "not_found": not_found, "batch_id": batch_id}, ensure_ascii=False), media_type="application/json")


@post("/fin-report/discrepancies/rollback", guards=[require_auth])
async def api_fin_report_discrepancies_rollback(
    request: Request, db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    """«Откат разногласий»: возвращает значения, сброшенные операцией «Разногласия».

    Восстанавливает task_report/task_detail/reestr_number/reestr_date/report/norm/extra
    для строк из последнего (или указанного batch_id) снимка. Одноразовый: снимок удаляется.
    """
    user = await get_current_user(request, db_session)
    if user.effective_role != "администратор":
        return Response(content=json.dumps({"error": "Нет прав"}, ensure_ascii=False), media_type="application/json", status_code=403)

    batch_id = (data or {}).get("batch_id")

    if batch_id:
        log = await db_session.execute(
            text("SELECT id, payload FROM discrepancies_log WHERE batch_id = :batch_id ORDER BY id DESC LIMIT 1"),
            {"batch_id": batch_id},
        )
    else:
        log = await db_session.execute(
            text("SELECT id, payload FROM discrepancies_log ORDER BY id DESC LIMIT 1"),
        )

    row = log.mappings().first()
    if row is None:
        return Response(content=json.dumps({"error": "Нет снимка для отката"}, ensure_ascii=False), media_type="application/json", status_code=404)

    snapshot = json.loads(row["payload"])
    restored = 0
    for tn, prev in snapshot.items():
        await db_session.execute(
            text(
                "UPDATE main_afl SET task_report = :task_report, task_detail = :task_detail, "
                "reestr_number = :reestr_number, reestr_date = :reestr_date, report = :report, "
                "norm = :norm, extra = :extra WHERE task_number = :tn"
            ),
            {
                "tn": tn,
                "task_report": prev.get("task_report"),
                "task_detail": prev.get("task_detail"),
                "reestr_number": prev.get("reestr_number"),
                "reestr_date": prev.get("reestr_date"),
                "report": prev.get("report"),
                "norm": prev.get("norm"),
                "extra": prev.get("extra"),
            },
        )
        restored += 1

    await db_session.execute(text("DELETE FROM discrepancies_log WHERE id = :id"), {"id": row["id"]})
    await db_session.commit()

    return Response(content=json.dumps({"success": True, "restored": restored}, ensure_ascii=False), media_type="application/json")


@post("/fin-report/discrepancies/discard", guards=[require_auth])
async def api_fin_report_discrepancies_discard(
    request: Request, db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    """«Сохранить» после «Разногласий»: выбрасывает снимок отката (изменения остаются).

    Удаляет строку discrepancies_log для batch_id — откат становится недоступен.
    """
    user = await get_current_user(request, db_session)
    if user.effective_role != "администратор":
        return Response(content=json.dumps({"error": "Нет прав"}, ensure_ascii=False), media_type="application/json", status_code=403)

    batch_id = (data or {}).get("batch_id")
    if not batch_id:
        return Response(content=json.dumps({"error": "Нет batch_id"}, ensure_ascii=False), media_type="application/json", status_code=400)

    await db_session.execute(text("DELETE FROM discrepancies_log WHERE batch_id = :batch_id"), {"batch_id": batch_id})
    await db_session.commit()

    return Response(content=json.dumps({"success": True}, ensure_ascii=False), media_type="application/json")


@post("/fin-report/recheck", guards=[require_auth])
async def api_fin_report_recheck(
    request: Request, db_session: AsyncSession,
    data: UploadFile = Body(media_type=RequestEncodingType.MULTI_PART),
) -> Response:
    """«Повторная проверка»: txt с номерами заданий (по одному на строку).

    Для найденных строк: report = NULL + пересчёт ошибок по общим правилам БЕЗ ограничений
    (verified/status/sent_to_billing/reestr_number). Возвращает xlsx с ошибками и колонкой
    «Комментарий» («Заблокировано исправление» для status='Закрыто' или sent_to_billing='Да').
    """
    user = await get_current_user(request, db_session)
    if user.effective_role != "администратор":
        return Response(content=json.dumps({"error": "Нет прав"}, ensure_ascii=False), media_type="application/json", status_code=403)

    if not data or not data.filename.lower().endswith(".txt"):
        return Response(content=json.dumps({"error": "Нужен файл .txt"}, ensure_ascii=False), media_type="application/json", status_code=400)

    raw = await data.read()
    text_content = None
    for enc in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            text_content = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text_content is None:
        return Response(content=json.dumps({"error": "Не удалось прочитать txt (кодировка)"}, ensure_ascii=False), media_type="application/json", status_code=400)

    numbers = [line.strip() for line in text_content.splitlines() if line.strip()]
    if not numbers:
        return Response(content=json.dumps({"error": "Файл пуст"}, ensure_ascii=False), media_type="application/json", status_code=400)

    updates = []
    report_rows = []
    balance_rows = []
    date_rows = []
    not_found = 0
    for tn in numbers:
        result = await db_session.execute(text("SELECT * FROM main_afl WHERE task_number = :tn"), {"tn": tn})
        row = result.fetchone()
        if row is None:
            not_found += 1
            continue
        row = dict(row._mapping)
        errors = check_row(row)
        updates.append({"e": join_errors(errors), "tn": tn})

        general = []
        for e in errors:
            if e in BALANCE_ERRORS:
                balance_rows.append((tn, e))
            elif e == "Дата работ":
                date_rows.append((tn, e))
            else:
                general.append(e)
        if general:
            comment = "Заблокировано исправление" if (row.get("status") == "Закрыто" or row.get("sent_to_billing") == "Да") else ""
            report_rows.append((tn, join_errors(general), comment))

    if updates:
        await db_session.execute(
            text("UPDATE main_afl SET report = NULL, reestr_number = NULL, reestr_date = NULL, errors = :e WHERE task_number = :tn"),
            updates,
        )
    await db_session.commit()

    output = generate_recheck_xlsx(report_rows, balance_rows, date_rows)
    filename = f"Повторная_проверка_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.xlsx"
    return Response(
        content=output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "X-Updated": str(len(updates)),
            "X-Not-Found": str(not_found),
        },
    )


download_progress: dict[str, dict] = {}
download_results: dict[str, bytes] = {}


@post("/fin-report/download", guards=[require_auth])
async def api_fin_report_download_start(request: Request, db_session: AsyncSession, data: dict = Body(media_type=RequestEncodingType.JSON)) -> Response:
    """Старт генерации отчёта: возвращает download_id, файлы собираются в фоне."""
    user = await get_current_user(request, db_session)
    if user.effective_role != "администратор":
        return Response(content=json.dumps({"error": "Нет прав"}, ensure_ascii=False), media_type="application/json", status_code=403)

    period = (data or {}).get("period", "")
    period_fmt = period.strip().replace("-", " ") if period else ""
    if not period_fmt:
        return Response(content=json.dumps({"error": "Выберите период"}, ensure_ascii=False), media_type="application/json", status_code=400)

    download_id = str(uuid.uuid4())
    download_progress[download_id] = {"status": "starting", "done": 0, "total": 6, "progress": 0}
    asyncio.create_task(_run_download(download_id, period_fmt))
    return Response(content=json.dumps({"download_id": download_id}, ensure_ascii=False), media_type="application/json")


@get("/fin-report/download/progress/{download_id:str}", guards=[require_auth])
async def api_fin_report_download_progress(download_id: str) -> Response:
    if download_id not in download_progress:
        return Response(content=json.dumps({"status": "not_found"}, ensure_ascii=False), media_type="application/json", status_code=404)
    return Response(content=json.dumps(download_progress[download_id], ensure_ascii=False), media_type="application/json")


@get("/fin-report/download/result/{download_id:str}", guards=[require_auth])
async def api_fin_report_download_result(download_id: str) -> Response:
    data = download_results.pop(download_id, None)
    if data is None:
        return Response(content=json.dumps({"error": "Ещё не готово"}, ensure_ascii=False), media_type="application/json", status_code=404)
    meta = download_progress.pop(download_id, {})
    filename = meta.get("filename", "Отчёт.zip")
    return Response(content=data, media_type="application/zip",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"})


async def _run_download(download_id: str, period_fmt: str):
    from data.config import async_session_factory
    try:
        async with async_session_factory() as db_session:
            period_tag = period_fmt.replace(" ", "-")
            detail_files = [
                ("Плановый", "СПб", "спбплан"),
                ("Плановый", "ЛО", "лоплан"),
                ("Внеплановый", "СПб", "спбвнеплан"),
                ("Внеплановый", "ЛО", "ловнеплан"),
            ]
            total = 6
            done = 0
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for task_type, region, name in detail_files:
                    data = await generate_fin_report_xlsx_bytes(db_session, period_fmt, task_type, region)
                    zf.writestr(f"Отчёт_{period_tag}_{name}.xlsx", data)
                    done += 1
                    download_progress[download_id] = {"status": "generating", "done": done, "total": total, "progress": int(done / total * 100)}

                for region, name in (("СПб", "спб"), ("ЛО", "ло")):
                    data = await generate_dop_report_xlsx_bytes(db_session, period_fmt, region)
                    zf.writestr(f"Допотчёт_{period_tag}_{name}.xlsx", data)
                    done += 1
                    download_progress[download_id] = {"status": "generating", "done": done, "total": total, "progress": int(done / total * 100)}

            buf.seek(0)
            filename = f"Отчёт_{period_tag}.zip"
            download_results[download_id] = buf.read()
            download_progress[download_id] = {"status": "complete", "done": total, "total": total, "progress": 100, "filename": filename}
    except Exception as e:
        import traceback
        traceback.print_exc()
        download_progress[download_id] = {"status": "error", "done": 0, "total": 6, "progress": 0, "message": str(e)}


fin_report_router = Router("/api", route_handlers=[
    api_fin_report, api_fin_report_add, api_fin_report_discrepancies, api_fin_report_discrepancies_rollback, api_fin_report_discrepancies_discard, api_fin_report_recheck,
    api_fin_report_download_start, api_fin_report_download_progress, api_fin_report_download_result,
])
