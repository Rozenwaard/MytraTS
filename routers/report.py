import json
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
from services.reestr import generate_report_xlsx_bytes


@post("/report", guards=[require_auth])
async def api_report(
    request: Request, db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    user = await get_current_user(request, db_session)
    if user.effective_role not in ('администратор', 'специалист'):
        return Response(content=json.dumps({"success": False, "error": "Нет прав"}, ensure_ascii=False), media_type="application/json")
    month = data.get("month")
    year = data.get("year")
    if not month or not year:
        return Response(content=json.dumps({"success": False, "error": "Выберите месяц и год"}, ensure_ascii=False), media_type="application/json")
    months = ["", "январь", "февраль", "март", "апрель", "май", "июнь",
              "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
    period = f"{months[month]} {year}"

    result1 = await db_session.execute(
        text("UPDATE main_afl SET report = :period WHERE reestr_date IS NOT NULL AND report IS NULL"),
        {"period": period})
    count = result1.rowcount

    result2 = await db_session.execute(
        text("UPDATE main_afl SET report = 'Отклонён' WHERE reestr_number = 'Отклонён' AND report IS NULL"))
    rejected = result2.rowcount

    await db_session.execute(text("INSERT INTO story_afl SELECT * FROM main_afl WHERE report IS NOT NULL"))
    await db_session.execute(text("DELETE FROM main_afl WHERE report IS NOT NULL"))
    await db_session.commit()

    return Response(content=json.dumps({
        "success": True, "period": period, "count": count, "rejected": rejected,
        "download_url": f"/api/download-report/{quote(period)}"
    }, ensure_ascii=False), media_type="application/json")


@get("/download-report/{period:str}", guards=[require_auth])
async def api_download_report(period: str, db_session: AsyncSession) -> Response:
    output = await generate_report_xlsx_bytes(db_session, period)
    filename = f"Отчёт_{period}.xlsx"
    return Response(content=output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"})


report_router = Router("/api", route_handlers=[api_report, api_download_report])
