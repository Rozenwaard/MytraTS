import asyncio
import json
import traceback
import uuid
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

from deps import require_auth
from services.merger import merge_to_main
from services.processor import process_raw_afl
from services.report_check import recompute_errors
from services.status import get_status, record_upload, set_last_txt_count
from services.uploader import load_xlsx_to_raw

upload_progress: dict[str, dict] = {}


@post("/upload", guards=[require_auth])
async def api_upload(data: UploadFile = Body(media_type=RequestEncodingType.MULTI_PART)) -> Response:
    if not data or not data.filename.endswith('.xlsx'):
        return Response(content=json.dumps({"error": "Нужен файл .xlsx"}, ensure_ascii=False), media_type="application/json", status_code=400)
    try:
        content = await data.read()
        upload_id = str(uuid.uuid4())
        upload_progress[upload_id] = {"status": "starting", "progress": 0, "total": 0}
        asyncio.create_task(_run_pipeline(upload_id, content))
        return Response(content=json.dumps({"upload_id": upload_id}, ensure_ascii=False), media_type="application/json")
    except Exception as e:
        traceback.print_exc()
        return Response(content=json.dumps({"error": str(e)}, ensure_ascii=False), media_type="application/json", status_code=500)


@get("/upload/progress/{upload_id:str}")
async def api_upload_progress(upload_id: str) -> Response:
    if upload_id not in upload_progress:
        return Response(content=json.dumps({"status": "not_found"}, ensure_ascii=False), media_type="application/json", status_code=404)
    return Response(content=json.dumps(upload_progress[upload_id], ensure_ascii=False), media_type="application/json")


@get("/upload/task-numbers-in-work", guards=[require_auth])
async def api_task_numbers_in_work(request: Request, db_session: AsyncSession) -> Response:
    """Номера заданий «в работе»: без отчёта (report) и без реестра (reestr_number)."""
    result = await db_session.execute(
        text("SELECT task_number FROM main_afl "
             "WHERE (report IS NULL OR report = '') AND (reestr_number IS NULL OR reestr_number = '') "
             "ORDER BY task_number"))
    rows = [r[0] for r in result if r[0]]
    await set_last_txt_count(db_session, len(rows))
    content = ("\n".join(rows) + ("\n" if rows else "")).encode("utf-8")
    filename = f"Номера_заданий_в_работе_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"
    return Response(content=content, media_type="text/plain",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"})


@get("/status", guards=[require_auth])
async def api_status(request: Request, db_session: AsyncSession) -> Response:
    """Состояние загрузок для виджета «Состояние»."""
    data = await get_status(db_session)
    return Response(content=json.dumps(data, ensure_ascii=False), media_type="application/json")


async def _run_pipeline(upload_id: str, content: bytes):
    from data.config import async_session_factory
    async with async_session_factory() as db_session:
        try:
            upload_progress[upload_id] = {"status": "loading", "progress": 5, "total": 0}
            success, error, total_rows = await load_xlsx_to_raw(db_session, content)
            if not success:
                upload_progress[upload_id] = {"status": "error", "progress": 0, "total": 0, "message": error}
                return
            upload_progress[upload_id] = {"status": "loaded", "progress": 20, "total": total_rows, "loaded": total_rows}
            upload_progress[upload_id] = {"status": "processing", "progress": 25, "total": total_rows}
            success = await process_raw_afl(db_session, upload_progress, upload_id, total_rows)
            if not success:
                return
            upload_progress[upload_id] = {"status": "merging", "progress": 90, "total": total_rows}
            inserted, updated, affected = await merge_to_main(db_session, upload_progress, upload_id, total_rows)
            upload_progress[upload_id] = {"status": "merging", "progress": 99, "total": total_rows, "inserted": inserted, "updated": updated}
            await recompute_errors(db_session, affected)
            await record_upload(db_session, total_rows, inserted)
            upload_progress[upload_id] = {"status": "complete", "progress": 100, "total": total_rows, "inserted": inserted, "updated": updated, "message": f"Загружено: {total_rows} строк | Новых: {inserted} | Обновлено: {updated}"}
        except Exception as e:
            await db_session.rollback()
            upload_progress[upload_id] = {"status": "error", "progress": 0, "total": 0, "message": str(e)}
            traceback.print_exc()


upload_router = Router("/api", route_handlers=[api_upload, api_upload_progress, api_task_numbers_in_work, api_status])
