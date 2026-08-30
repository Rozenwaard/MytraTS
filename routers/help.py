import json
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
from services.help import HELP_KEYS, parse_instruction_docx, parse_xlsx_to_blocks, render_help_html


async def _load_page(db_session: AsyncSession, key: str) -> dict | None:
    result = await db_session.execute(
        text("SELECT title, content, updated_at FROM help_pages WHERE key = :k"), {"k": key})
    row = result.fetchone()
    if row is None:
        return None
    blocks = json.loads(row[1]).get("blocks", [])
    return {"key": key, "title": row[0], "updated_at": row[2], "blocks": blocks}


@get("/help/{key:str}", guards=[require_auth])
async def api_help_get(key: str, db_session: AsyncSession) -> Response:
    if key not in HELP_KEYS:
        return Response(content=json.dumps({"error": "Неизвестная страница"}, ensure_ascii=False),
                        media_type="application/json", status_code=404)
    page = await _load_page(db_session, key)
    if page is None:
        page = {"key": key, "title": HELP_KEYS[key], "updated_at": None, "blocks": []}
    return Response(content=json.dumps(page, ensure_ascii=False), media_type="application/json")


@post("/help/{key:str}", guards=[require_auth])
async def api_help_upload(request: Request, db_session: AsyncSession, key: str,
                          data: UploadFile = Body(media_type=RequestEncodingType.MULTI_PART)) -> Response:
    user = await get_current_user(request, db_session)
    if user.effective_role != "администратор":
        return Response(content=json.dumps({"error": "Нет прав"}, ensure_ascii=False),
                        media_type="application/json", status_code=403)
    if key not in HELP_KEYS:
        return Response(content=json.dumps({"error": "Неизвестная страница"}, ensure_ascii=False),
                        media_type="application/json", status_code=404)

    filename = (data.filename or "").lower()
    raw = await data.read()

    if key == "instruction":
        if not filename.endswith(".docx"):
            return Response(content=json.dumps({"error": "Нужен файл .docx"}, ensure_ascii=False),
                            media_type="application/json", status_code=400)
        blocks = parse_instruction_docx(raw)
    elif key == "tariffs":
        if not filename.endswith(".xlsx"):
            return Response(content=json.dumps({"error": "Нужен файл .xlsx"}, ensure_ascii=False),
                            media_type="application/json", status_code=400)
        blocks = parse_xlsx_to_blocks(raw)
    else:
        return Response(content=json.dumps({"error": "Для этой страницы загрузка недоступна"}, ensure_ascii=False),
                        media_type="application/json", status_code=400)

    if not blocks:
        return Response(content=json.dumps({"error": "Файл пуст или не прочитан"}, ensure_ascii=False),
                        media_type="application/json", status_code=400)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await db_session.execute(
        text("INSERT OR REPLACE INTO help_pages (key, title, content, updated_at) VALUES (:k, :t, :c, :u)"),
        {"k": key, "t": HELP_KEYS[key], "c": json.dumps({"blocks": blocks}, ensure_ascii=False), "u": now})
    await db_session.commit()

    return Response(content=json.dumps({"success": True, "key": key, "updated_at": now}, ensure_ascii=False),
                    media_type="application/json")


@get("/help/{key:str}/download", guards=[require_auth])
async def api_help_download(key: str, db_session: AsyncSession) -> Response:
    if key not in HELP_KEYS:
        return Response(content=json.dumps({"error": "Неизвестная страница"}, ensure_ascii=False),
                        media_type="application/json", status_code=404)
    page = await _load_page(db_session, key)
    if page is None:
        return Response(content=json.dumps({"error": "Страница пуста"}, ensure_ascii=False),
                        media_type="application/json", status_code=404)

    html = render_help_html(page["title"], page["blocks"])
    filename = f"{page['title']}.html"
    return Response(content=html, media_type="text/html",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"})


help_router = Router("/api", route_handlers=[api_help_get, api_help_upload, api_help_download])
