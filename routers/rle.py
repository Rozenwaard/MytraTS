import json
from urllib.parse import quote

from litestar import Router
from litestar.connection import Request
from litestar.handlers import get
from litestar.response import Response
from sqlalchemy.ext.asyncio import AsyncSession

from deps import get_current_user, require_auth
from services.rle import build_week_sequence, compute_week_stats, generate_rle_xlsx_bytes


@get("/rle", guards=[require_auth])
async def api_rle(request: Request, db_session: AsyncSession) -> Response:
    """Таблица РЛЭ: сквозная колонка филиалов + недельные блоки (для вкладки)."""
    user = await get_current_user(request, db_session)
    if user.effective_role != "администратор":
        return Response(content=json.dumps({"error": "Нет прав"}, ensure_ascii=False), media_type="application/json", status_code=403)

    weeks = await build_week_sequence(db_session)
    stats = [await compute_week_stats(db_session, y, w) for y, w in weeks]

    grids = sorted({g for ws in stats for g in ws["cells"]})
    payload = {
        "weeks": [{"week": ws["week"], "range": ws["range"]} for ws in stats],
        "grids": grids,
        "rows": [
            {"grid": g, "values": [ws["cells"].get(g, {"count": 0, "per_executor": 0.0, "per_day": 0.0}) for ws in stats]}
            for g in grids
        ],
        "totals": [{"count": ws["total_works"], "executors": ws["executors_for_rle"]} for ws in stats],
    }
    return Response(content=json.dumps(payload, ensure_ascii=False), media_type="application/json")


@get("/rle/download", guards=[require_auth])
async def api_rle_download(request: Request, db_session: AsyncSession) -> Response:
    """Xlsx РЛЭ за весь период (с 27 недели до последней полной недели)."""
    user = await get_current_user(request, db_session)
    if user.effective_role != "администратор":
        return Response(content=json.dumps({"error": "Нет прав"}, ensure_ascii=False), media_type="application/json", status_code=403)

    weeks = await build_week_sequence(db_session)
    stats = [await compute_week_stats(db_session, y, w) for y, w in weeks]
    output = generate_rle_xlsx_bytes(stats)
    last_week = weeks[-1][1] if weeks else 0
    filename = f"РЛЭ неделя {last_week}.xlsx"
    return Response(
        content=output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


rle_router = Router("/api", route_handlers=[api_rle, api_rle_download])
