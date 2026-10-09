"""Тикеты «Вопросы»: пользователь задаёт вопрос по номерам заданий, администратор отвечает и закрывает."""

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

from data.config import tickets_session_factory
from deps import get_current_user, require_auth
from sql import build_in_clause


def _json(data, status_code: int = 200) -> Response:
    return Response(
        content=json.dumps(data, ensure_ascii=False),
        media_type="application/json",
        status_code=status_code,
    )


def _normalize_task_numbers(raw) -> list[str]:
    """Строка с номерами (запятые/пробелы/переносы) → список без пустых."""
    if raw is None:
        return []
    s = str(raw)
    for ch in ("\xa0", "\u2007", "\u202f", ","):
        s = s.replace(ch, " ")
    return [p for p in s.split() if p.strip()]


# Вложения: разрешённые типы (по расширению) и лимиты.
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".pdf", ".xlsx"}
MAX_ATTACHMENTS_PER_TICKET = 5
MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024  # 10 МБ


def _attachment_content_type(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
        "gif": "image/gif",
        "pdf": "application/pdf",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }.get(ext, "application/octet-stream")


@post("/tickets", guards=[require_auth])
async def api_create_ticket(
    request: Request, db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    user = await get_current_user(request, db_session)
    if not user:
        return _json({"error": "Не авторизован"}, 401)

    task_numbers = _normalize_task_numbers(data.get("task_numbers"))
    question = (data.get("question") or "").strip()
    if not task_numbers:
        return _json({"error": "Укажите номер задания"}, 400)
    if not question:
        return _json({"error": "Введите текст вопроса"}, 400)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await db_session.execute(text(
        "INSERT INTO tickets (task_numbers, question, answer, status, author_id, author_name, author_staff_id, created_at) "
        "VALUES (:tn, :q, NULL, 'open', :aid, :aname, :astaff, :created)"
    ), {
        "tn": json.dumps(task_numbers, ensure_ascii=False),
        "q": question,
        "aid": user.id,
        "aname": user.full_name,
        "astaff": user.staff_id,
        "created": now,
    })
    ticket_id = (await db_session.execute(text("SELECT last_insert_rowid()"))).scalar()
    await db_session.commit()
    return _json({"ok": True, "id": ticket_id}, 201)


@get("/tickets", guards=[require_auth])
async def api_list_tickets(request: Request, db_session: AsyncSession) -> Response:
    user = await get_current_user(request, db_session)
    if not user:
        return _json({"error": "Не авторизован"}, 401)

    columns = ("id, task_numbers, question, answer, status, author_name, "
               "author_staff_id, created_at, answered_at, answered_by")
    if user.effective_role == "администратор":
        result = await db_session.execute(text(f"SELECT {columns} FROM tickets ORDER BY id DESC"))
    else:
        result = await db_session.execute(
            text(f"SELECT {columns} FROM tickets WHERE author_id = :aid ORDER BY id DESC"),
            {"aid": user.id})

    tickets = []
    for row in result:
        tickets.append({
            "id": row[0],
            "task_numbers": json.loads(row[1]) if row[1] else [],
            "question": row[2],
            "answer": row[3],
            "status": row[4],
            "author_name": row[5],
            "author_staff_id": row[6],
            "created_at": row[7],
            "answered_at": row[8],
            "answered_by": row[9],
        })

    # Вложения (метаданные) из tickets.db.
    for t in tickets:
        t["attachments"] = []
    if tickets:
        tids = [t["id"] for t in tickets]
        in_sql, in_params = build_in_clause("ta", tids)
        by_ticket = {t["id"]: t for t in tickets}
        async with tickets_session_factory() as ts:
            rows = await ts.execute(text(
                f"SELECT id, ticket_id, filename, content_type, size FROM ticket_attachments "
                f"WHERE ticket_id IN ({in_sql}) ORDER BY id"), in_params)
            for row in rows:
                if row[1] in by_ticket:
                    by_ticket[row[1]]["attachments"].append({
                        "id": row[0],
                        "filename": row[2],
                        "content_type": row[3],
                        "size": row[4],
                    })

    return _json({"tickets": tickets})


@post("/tickets/{ticket_id:int}/answer", guards=[require_auth])
async def api_answer_ticket(
    request: Request, db_session: AsyncSession, ticket_id: int,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    user = await get_current_user(request, db_session)
    if not user or user.effective_role != "администратор":
        return _json({"error": "Нет прав"}, 403)

    answer = (data.get("answer") or "").strip()
    if not answer:
        return _json({"error": "Введите ответ"}, 400)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    result = await db_session.execute(text(
        "UPDATE tickets SET answer = :a, status = 'closed', answered_at = :at, answered_by = :by "
        "WHERE id = :id AND status = 'open'"
    ), {"a": answer, "at": now, "by": user.full_name, "id": ticket_id})
    await db_session.commit()
    if result.rowcount == 0:
        return _json({"error": "Тикет не найден или уже закрыт"}, 404)
    return _json({"ok": True})


@post("/tickets/{ticket_id:int}/attachments", guards=[require_auth])
async def api_upload_attachments(
    request: Request, db_session: AsyncSession, ticket_id: int,
    data: dict = Body(media_type=RequestEncodingType.MULTI_PART),
) -> Response:
    user = await get_current_user(request, db_session)
    if not user:
        return _json({"error": "Не авторизован"}, 401)

    author_id = (await db_session.execute(
        text("SELECT author_id FROM tickets WHERE id = :id"), {"id": ticket_id})).scalar()
    if author_id is None:
        return _json({"error": "Тикет не найден"}, 404)
    if author_id != user.id:
        return _json({"error": "Прикреплять файлы может только автор тикета"}, 403)

    raw_files = data.get("files")
    if raw_files is None:
        return _json({"error": "Файлы не переданы"}, 400)
    files = raw_files if isinstance(raw_files, list) else [raw_files]

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    saved = 0
    async with tickets_session_factory() as ts:
        already = (await ts.execute(
            text("SELECT COUNT(*) FROM ticket_attachments WHERE ticket_id = :tid"),
            {"tid": ticket_id})).scalar() or 0
        if already + len(files) > MAX_ATTACHMENTS_PER_TICKET:
            return _json({"error": f"Не более {MAX_ATTACHMENTS_PER_TICKET} файлов на тикет"}, 400)

        for f in files:
            filename = (f.filename or "").strip() or "file"
            ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
            if ext not in ALLOWED_EXTENSIONS:
                return _json({"error": f"Недопустимый тип файла: {filename}"}, 400)
            content = await f.read()
            if not content:
                continue
            if len(content) > MAX_ATTACHMENT_SIZE:
                return _json({"error": f"Файл {filename} больше 10 МБ"}, 400)
            await ts.execute(text(
                "INSERT INTO ticket_attachments "
                "(ticket_id, filename, content_type, size, data, uploaded_by, created_at) "
                "VALUES (:tid, :fn, :ct, :sz, :data, :by, :at)"
            ), {
                "tid": ticket_id,
                "fn": filename,
                "ct": f.content_type or _attachment_content_type(filename),
                "sz": len(content),
                "data": content,
                "by": user.full_name,
                "at": now,
            })
            saved += 1
        await ts.commit()

    return _json({"ok": True, "saved": saved}, 201)


@get("/tickets/{ticket_id:int}/attachments/{attachment_id:int}", guards=[require_auth])
async def api_download_attachment(
    request: Request, db_session: AsyncSession, ticket_id: int, attachment_id: int,
) -> Response:
    user = await get_current_user(request, db_session)
    if not user:
        return _json({"error": "Не авторизован"}, 401)

    author_id = (await db_session.execute(
        text("SELECT author_id FROM tickets WHERE id = :id"), {"id": ticket_id})).scalar()
    if author_id is None:
        return _json({"error": "Тикет не найден"}, 404)
    if user.effective_role != "администратор" and author_id != user.id:
        return _json({"error": "Нет прав"}, 403)

    async with tickets_session_factory() as ts:
        row = (await ts.execute(text(
            "SELECT filename, content_type, data FROM ticket_attachments "
            "WHERE id = :aid AND ticket_id = :tid"
        ), {"aid": attachment_id, "tid": ticket_id})).fetchone()

    if row is None:
        return _json({"error": "Файл не найден"}, 404)

    filename, content_type, blob = row
    disposition = f"attachment; filename*=UTF-8''{quote(filename)}"
    return Response(
        content=blob,
        media_type=content_type or "application/octet-stream",
        headers={"Content-Disposition": disposition},
    )


tickets_router = Router("/api", route_handlers=[
    api_create_ticket, api_list_tickets, api_answer_ticket,
    api_upload_attachments, api_download_attachment,
])
