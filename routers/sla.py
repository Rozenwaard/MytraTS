"""Вкладка «СЛА» в Отчётах — расчёт полноты (результативности) по ПСК."""

import json
from datetime import datetime
from urllib.parse import quote

from litestar import Router
from litestar.connection import Request
from litestar.handlers import get
from litestar.response import Response
from sqlalchemy.ext.asyncio import AsyncSession

from deps import get_current_user, require_auth
from services.sla import compute_resultativity, generate_sla_xlsx


async def _month(request: Request, db_session: AsyncSession, month: str) -> tuple[str | None, str]:
    user = await get_current_user(request, db_session)
    if user.effective_role not in ("администратор", "специалист"):
        return None, ""
    if not month:
        month = datetime.now().strftime("%Y-%m")
    return user, month


@get("/reports/sla", guards=[require_auth])
async def api_reports_sla(
    request: Request, db_session: AsyncSession, month: str = "",
) -> Response:
    user, month = await _month(request, db_session, month)
    if user is None:
        return Response(content=json.dumps({"error": "Нет прав"}, ensure_ascii=False),
                        media_type="application/json", status_code=403)
    data = await compute_resultativity(db_session, month)
    return Response(content=json.dumps(data, ensure_ascii=False), media_type="application/json")


@get("/reports/sla/download", guards=[require_auth])
async def api_reports_sla_download(
    request: Request, db_session: AsyncSession, month: str = "",
) -> Response:
    user, month = await _month(request, db_session, month)
    if user is None:
        return Response(content=json.dumps({"error": "Нет прав"}, ensure_ascii=False),
                        media_type="application/json", status_code=403)
    data = await compute_resultativity(db_session, month)
    output = generate_sla_xlsx(data)
    filename = f"СЛА_{month}.xlsx"
    return Response(
        content=output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


sla_router = Router("/api", route_handlers=[api_reports_sla, api_reports_sla_download])
