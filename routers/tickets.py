"""Тикеты «Вопросы»: пользователь задаёт вопрос по номерам заданий, администратор отвечает и закрывает."""

import json
from datetime import datetime

from litestar import Router
from litestar.connection import Request
from litestar.enums import RequestEncodingType
from litestar.handlers import get, post
from litestar.params import Body
from litestar.response import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from deps import get_current_user, require_auth


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


tickets_router = Router("/api", route_handlers=[api_create_ticket, api_list_tickets, api_answer_ticket])
