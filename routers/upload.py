import asyncio
import json
import traceback
import uuid

from litestar import Router
from litestar.datastructures import UploadFile
from litestar.enums import RequestEncodingType
from litestar.handlers import get, post
from litestar.params import Body
from litestar.response import Response

from deps import require_auth
from services.merger import merge_to_main
from services.processor import process_raw_afl
from services.report_check import recompute_errors
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
            await recompute_errors(db_session, affected)
            upload_progress[upload_id] = {"status": "complete", "progress": 100, "total": total_rows, "inserted": inserted, "updated": updated, "message": f"Загружено: {total_rows} строк | Новых: {inserted} | Обновлено: {updated}"}
        except Exception as e:
            await db_session.rollback()
            upload_progress[upload_id] = {"status": "error", "progress": 0, "total": 0, "message": str(e)}
            traceback.print_exc()


upload_router = Router("/api", route_handlers=[api_upload, api_upload_progress])
