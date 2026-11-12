import asyncio
import json
import re
from datetime import date
from urllib.parse import quote

from litestar import Router
from litestar.connection import Request
from litestar.datastructures import UploadFile
from litestar.enums import RequestEncodingType
from litestar.handlers import get, post
from litestar.params import Body
from litestar.response import Response
from sqlalchemy.ext.asyncio import AsyncSession

from data.config import story_session_factory
from deps import get_current_user, require_auth
from services.periods import compute_report_periods
from services.rle import (
    IP_FILE_TITLES,
    IP_MAIN_TYPES,
    KSP_FILE_TITLES,
    KSP_MAIN_TYPES,
    MONTH_NAMES,
    biweekly_periods,
    build_execution_report_xlsx,
    build_file_minutes,
    compute_merged_period_stats,
    compute_period_stats,
    fetch_readings_register_rows,
    generate_merged_rle_xlsx_bytes,
    generate_readings_violations_xlsx,
    generate_rle_xlsx_bytes,
    parse_rle_file,
    weekly_periods,
)


def _empty_cell() -> dict:
    return {"count": 0, "per_executor": 0.0, "per_day": 0.0, "workers": 0.0}


@get("/rle", guards=[require_auth])
async def api_rle(request: Request, db_session: AsyncSession) -> Response:
    """Таблица РЛЭ: четыре недельных периода окна 28 дней (для вкладки)."""
    user = await get_current_user(request, db_session)
    if user.effective_role != "администратор":
        return Response(content=json.dumps({"error": "Нет прав"}, ensure_ascii=False), media_type="application/json", status_code=403)

    periods = weekly_periods()
    stats = [await compute_period_stats(db_session, d1, d2) for d1, d2 in periods]

    grids = sorted({g for ws in stats for g in ws["cells"]})
    payload = {
        "weeks": [{"week": ws["week"], "range": ws["range"]} for ws in stats],
        "grids": grids,
        "rows": [
            {"grid": g, "values": [ws["cells"].get(g, _empty_cell()) for ws in stats]}
            for g in grids
        ],
        "totals": [
            {
                "count": ws["total_works"],
                "per_executor": ws["total_per_executor"],
                "per_day": ws["total_per_day"],
                "executors": ws["workers_for_rle"],
            }
            for ws in stats
        ],
    }
    return Response(content=json.dumps(payload, ensure_ascii=False), media_type="application/json")


@get("/rle/download", guards=[require_auth])
async def api_rle_download(request: Request, db_session: AsyncSession) -> Response:
    """Xlsx РЛЭ: два двухнедельных периода окна 28 дней."""
    user = await get_current_user(request, db_session)
    if user.effective_role != "администратор":
        return Response(content=json.dumps({"error": "Нет прав"}, ensure_ascii=False), media_type="application/json", status_code=403)

    periods = biweekly_periods()
    stats = [await compute_period_stats(db_session, d1, d2) for d1, d2 in periods]
    output = await asyncio.to_thread(generate_rle_xlsx_bytes, stats)

    start, end = periods[0][0], periods[-1][1]
    filename = f"РЛЭ {start.strftime('%d.%m')}-{end.strftime('%d.%m')}.xlsx"
    return Response(
        content=output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@post("/rle/upload", guards=[require_auth])
async def api_rle_upload(
    request: Request, db_session: AsyncSession,
    data: UploadFile = Body(media_type=RequestEncodingType.MULTI_PART),
) -> Response:
    """«Загрузить 1С»: файл с работами РЛЭ → сводный отчёт (КСП + ИП).

    Дополнительные работы/работники из файла добавляются к базе main_afl и
    считаются по текущему алгоритму РЛЭ. Возвращает xlsx с двумя таблицами:
    «КСП» (Проверка, осмотр из main_afl + Бытовая заявка и Снятие показаний из
    файла) и «ИП» (Инструментальная проверка из main_afl + из файла).
    """
    user = await get_current_user(request, db_session)
    if user.effective_role != "администратор":
        return Response(content=json.dumps({"error": "Нет прав"}, ensure_ascii=False), media_type="application/json", status_code=403)

    if not data or not data.filename.lower().endswith((".xlsx", ".xls")):
        return Response(content=json.dumps({"error": "Нужен файл .xlsx"}, ensure_ascii=False), media_type="application/json", status_code=400)

    content = await data.read()
    file_rows = await asyncio.to_thread(parse_rle_file, content)
    if not file_rows:
        return Response(content=json.dumps({"error": "В файле нет строк заказчика «ЛЭ»"}, ensure_ascii=False), media_type="application/json", status_code=400)

    # Минуты работ файла — carte.absolute + множитель 2 для «Инструментальной проверки».
    file_minutes = await build_file_minutes(db_session)

    periods = biweekly_periods()
    ksp_stats = [await compute_merged_period_stats(db_session, d1, d2, file_rows, KSP_MAIN_TYPES, KSP_FILE_TITLES, file_minutes) for d1, d2 in periods]
    ip_stats = [await compute_merged_period_stats(db_session, d1, d2, file_rows, IP_MAIN_TYPES, IP_FILE_TITLES, file_minutes) for d1, d2 in periods]

    output = await asyncio.to_thread(generate_merged_rle_xlsx_bytes, ksp_stats, ip_stats)
    start, end = periods[0][0], periods[-1][1]
    filename = f"РЛЭ {start.strftime('%d.%m')}-{end.strftime('%d.%m')}.xlsx"
    return Response(
        content=output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@get("/rle/readings", guards=[require_auth])
async def api_rle_readings(request: Request, db_session: AsyncSession) -> Response:
    """«Реестр показаний»: показания и нарушения РЛЭ за текущий месяц → xlsx."""
    user = await get_current_user(request, db_session)
    if user.effective_role != "администратор":
        return Response(content=json.dumps({"error": "Нет прав"}, ensure_ascii=False), media_type="application/json", status_code=403)

    today = date.today()
    year_month = today.strftime("%Y-%m")
    rows = await fetch_readings_register_rows(db_session, year_month)
    output = await asyncio.to_thread(generate_readings_violations_xlsx, rows)

    filename = f"Реестр показаний и нарушений {MONTH_NAMES[today.month]}.xlsx"
    return Response(
        content=output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


_YM_RE = re.compile(r"^\d{4}-\d{2}$")


@get("/rle/periods", guards=[require_auth])
async def api_rle_periods(request: Request, db_session: AsyncSession) -> Response:
    """Карусель месяцев для «Отчёта о выполнении» (те же периоды, что в Финотчёте)."""
    user = await get_current_user(request, db_session)
    if user.effective_role != "администратор":
        return Response(content=json.dumps({"error": "Нет прав"}, ensure_ascii=False), media_type="application/json", status_code=403)

    data = await compute_report_periods(db_session)
    return Response(content=json.dumps(data, ensure_ascii=False), media_type="application/json")


@post("/rle/report/download", guards=[require_auth])
async def api_rle_report_download(
    request: Request, db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    """«Отчёт о выполнении»: для выбранных месяцев — пара листов «Свод» + «Реестр».

    Строки — main_afl/story_afl с customer = 'РЛЭ', принадлежность месяцу — по done_day.
    """
    user = await get_current_user(request, db_session)
    if user.effective_role != "администратор":
        return Response(content=json.dumps({"error": "Нет прав"}, ensure_ascii=False), media_type="application/json", status_code=403)

    raw = (data or {}).get("periods")
    if not isinstance(raw, list):
        return Response(content=json.dumps({"error": "Выберите период"}, ensure_ascii=False), media_type="application/json", status_code=400)

    periods = sorted(
        {str(p) for p in raw if isinstance(p, str) and _YM_RE.match(str(p))},
        reverse=True,
    )
    if not periods:
        return Response(content=json.dumps({"error": "Выберите период"}, ensure_ascii=False), media_type="application/json", status_code=400)

    async with story_session_factory() as story_session:
        output = await build_execution_report_xlsx(db_session, story_session, periods)

    filename = "Отчёт о выполнении РЛЭ.xlsx"
    return Response(
        content=output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


rle_router = Router(
    "/api",
    route_handlers=[
        api_rle,
        api_rle_periods,
        api_rle_download,
        api_rle_report_download,
        api_rle_readings,
        api_rle_upload,
    ],
)
