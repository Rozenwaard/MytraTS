import json
from urllib.parse import quote

from litestar import Router
from litestar.connection import Request
from litestar.datastructures import UploadFile
from litestar.enums import RequestEncodingType
from litestar.handlers import get, post
from litestar.params import Body
from litestar.response import Response
from sqlalchemy.ext.asyncio import AsyncSession

from deps import get_current_user, require_auth
from services.rle import (
    IP_FILE_TITLES,
    IP_MAIN_TYPES,
    KSP_FILE_TITLES,
    KSP_MAIN_TYPES,
    biweekly_periods,
    build_file_minutes,
    compute_merged_period_stats,
    compute_period_stats,
    generate_merged_rle_xlsx_bytes,
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
    output = generate_rle_xlsx_bytes(stats)

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
    file_rows = parse_rle_file(content)
    if not file_rows:
        return Response(content=json.dumps({"error": "В файле нет строк заказчика «ЛЭ»"}, ensure_ascii=False), media_type="application/json", status_code=400)

    # Минуты работ файла — carte.absolute + множитель 2 для «Инструментальной проверки».
    file_minutes = await build_file_minutes(db_session)

    periods = biweekly_periods()
    ksp_stats = [await compute_merged_period_stats(db_session, d1, d2, file_rows, KSP_MAIN_TYPES, KSP_FILE_TITLES, file_minutes) for d1, d2 in periods]
    ip_stats = [await compute_merged_period_stats(db_session, d1, d2, file_rows, IP_MAIN_TYPES, IP_FILE_TITLES, file_minutes) for d1, d2 in periods]

    output = generate_merged_rle_xlsx_bytes(ksp_stats, ip_stats)
    start, end = periods[0][0], periods[-1][1]
    filename = f"РЛЭ {start.strftime('%d.%m')}-{end.strftime('%d.%m')}.xlsx"
    return Response(
        content=output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


rle_router = Router("/api", route_handlers=[api_rle, api_rle_download, api_rle_upload])
