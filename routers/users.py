"""Админ-панель: управление пользователями (только администратор).

Добавление/удаление, сброс пароля, очередь на добавление
из таблицы tabel (Премия). Чтение — через ORM User (как deps.get_current_user),
запись — сырым SQL через text()/bindparams (конвенция проекта).
"""

import json

from litestar import Router
from litestar.connection import Request
from litestar.enums import RequestEncodingType
from litestar.handlers import delete, get, patch, post
from litestar.params import Body
from litestar.response import Response
from sqlalchemy import select as sa_select
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from data.models import ROLES, User
from deps import get_current_user, require_auth


def _json(data, status_code: int = 200) -> Response:
    return Response(
        content=json.dumps(data, ensure_ascii=False),
        media_type="application/json",
        status_code=status_code,
    )


async def _admin_or_403(request: Request, db_session: AsyncSession) -> User | None:
    """Текущий пользователь, если он администратор; иначе None (вернуть 403)."""
    user = await get_current_user(request, db_session)
    if not user or user.effective_role != "администратор":
        return None
    return user


async def _has_other_admin(db_session: AsyncSession, exclude_id: int) -> bool:
    result = await db_session.execute(sa_select(User))
    for u in result.scalars():
        if u.id != exclude_id and u.effective_role == "администратор":
            return True
    return False


def _clean(v):
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _serialize(u: User) -> dict:
    return {
        "id": u.id,
        "full_name": u.full_name or "",
        "dept": u.dept or "",
        "locale": u.locale,
        "position": u.position or "",
        "staff_id": u.staff_id or "",
        "role": u.role,
        "effective_role": u.effective_role,
        "executor_name": u.executor_name,
        "has_password": u.password_hash is not None,
    }


@get("/admin/users", guards=[require_auth])
async def api_admin_users(request: Request, db_session: AsyncSession, q: str = "") -> Response:
    user = await _admin_or_403(request, db_session)
    if not user:
        return _json({"error": "Нет прав"}, 403)

    result = await db_session.execute(sa_select(User).order_by(User.full_name))
    users = [_serialize(u) for u in result.scalars()]

    q = (q or "").strip().lower()
    if q:
        users = [
            u for u in users
            if q in (u["full_name"] or "").lower()
            or q in (u["staff_id"] or "").lower()
            or q in (u["position"] or "").lower()
            or q in (u["dept"] or "").lower()
        ]
    return _json({"users": users})


@get("/admin/missing", guards=[require_auth])
async def api_admin_missing(request: Request, db_session: AsyncSession) -> Response:
    """Очередь на добавление: работники из tabel (инженер/контролёр — как в Премии), которых нет в users."""
    user = await _admin_or_403(request, db_session)
    if not user:
        return _json({"error": "Нет прав"}, 403)

    rows = (await db_session.execute(text(
        "SELECT DISTINCT t.staff_id, t.name, t.position FROM tabel t "
        "WHERE t.staff_id IS NOT NULL AND t.staff_id != '' "
        "AND t.staff_id NOT IN (SELECT staff_id FROM users WHERE staff_id IS NOT NULL) "
        "ORDER BY t.position, t.staff_id"
    ))).fetchall()

    # Синхронизировано с Премией (routers/premium.py _should_warn_missing): инженер/контролёр.
    missing = [{
        "staff_id": r[0],
        "name": r[1] or "",
        "position": r[2] or "",
    } for r in rows
        if any(k in (r[2] or "").lower() for k in ("инженер", "контрол"))]
    return _json({"missing": missing})


@get("/admin/quarantine", guards=[require_auth])
async def api_admin_quarantine(request: Request, db_session: AsyncSession) -> Response:
    """Карантин: исполнители main_afl без точного совпадения с users.executor_name."""
    user = await _admin_or_403(request, db_session)
    if not user:
        return _json({"error": "Нет прав"}, 403)

    rows = (await db_session.execute(text(
        "SELECT executor, executor_organization, status FROM ("
        "  SELECT m.executor AS executor, MAX(m.executor_organization) AS executor_organization, "
        "         COALESCE(q.status, 'рассмотрение') AS status "
        "  FROM main_afl m "
        "  LEFT JOIN quarantine_status q ON q.executor = m.executor "
        "  WHERE m.executor IS NOT NULL AND m.executor != '' "
        "    AND m.executor NOT IN (SELECT executor_name FROM users WHERE executor_name IS NOT NULL AND executor_name != '') "
        "  GROUP BY m.executor "
        "  UNION "
        "  SELECT q.executor AS executor, q.executor_organization AS executor_organization, q.status AS status "
        "  FROM quarantine_status q "
        "  WHERE q.executor NOT IN (SELECT executor_name FROM users WHERE executor_name IS NOT NULL AND executor_name != '') "
        ") ORDER BY status, executor"
    ))).fetchall()

    # Один и тот же исполнитель может прийти из обеих веток UNION (main_afl и
    # quarantine_status) с разным executor_organization — UNION схлопывает только
    # полностью одинаковые строки, поэтому на выходе могут оказаться дубли по
    # executor. На фронте таблица ключуется по executor ({#each ... (item.executor)}),
    # и дубли роняют рендер с each_key_duplicate. Схлопываем в одну строку на executor:
    # приоритет непустого отделения и статуса «блок».
    items: list[dict] = []
    seen: dict[str, dict] = {}
    for r in rows:
        executor = r[0]
        org = r[1] or ""
        status = r[2]
        cur = seen.get(executor)
        if cur is None:
            cur = {"executor": executor, "executor_organization": org, "status": status}
            seen[executor] = cur
            items.append(cur)
        else:
            if not cur["executor_organization"] and org:
                cur["executor_organization"] = org
            if status == "блок" and cur["status"] != "блок":
                cur["status"] = "блок"
    return _json({"items": items})


@post("/admin/quarantine/toggle", guards=[require_auth])
async def api_admin_quarantine_toggle(
    request: Request, db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    """Переключить статус (рассмотрение/блок) исполнителя карантина."""
    admin = await _admin_or_403(request, db_session)
    if not admin:
        return _json({"error": "Нет прав"}, 403)

    executor = _clean(data.get("executor"))
    if not executor:
        return _json({"error": "Некорректный исполнитель"}, 400)

    current = (await db_session.execute(
        text("SELECT status FROM quarantine_status WHERE executor = :e"),
        {"e": executor})).scalar()
    if current == "блок":
        # Снятие блока → рассмотрение (строку оставляем, меняем статус).
        await db_session.execute(
            text("UPDATE quarantine_status SET status = 'рассмотрение' WHERE executor = :e"),
            {"e": executor})
        new_status = "рассмотрение"
    else:
        # Блок → пометить (сохранив отделение) и вычистить строки из main_afl (бэкфил).
        org = (await db_session.execute(
            text("SELECT MAX(executor_organization) FROM main_afl WHERE executor = :e"),
            {"e": executor})).scalar() or ""
        await db_session.execute(
            text("INSERT INTO quarantine_status (executor, status, executor_organization) "
                 "VALUES (:e, 'блок', :org) "
                 "ON CONFLICT(executor) DO UPDATE SET status = 'блок', "
                 "executor_organization = excluded.executor_organization"),
            {"e": executor, "org": org})
        await db_session.execute(text("DELETE FROM main_afl WHERE executor = :e"), {"e": executor})
        new_status = "блок"
    await db_session.commit()
    return _json({"ok": True, "status": new_status})


@post("/admin/users", guards=[require_auth])
async def api_admin_user_create(
    request: Request, db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    admin = await _admin_or_403(request, db_session)
    if not admin:
        return _json({"error": "Нет прав"}, 403)

    full_name = _clean(data.get("full_name"))
    staff_id = _clean(data.get("staff_id"))
    if not full_name or not staff_id:
        return _json({"error": "ФИО и табельный номер обязательны"}, 400)

    exists = (await db_session.execute(
        text("SELECT id FROM users WHERE staff_id = :s"), {"s": staff_id})).scalar()
    if exists:
        return _json({"error": "Табельный номер уже существует"}, 400)

    role = _clean(data.get("role"))
    if role is not None and role not in ROLES:
        return _json({"error": "Некорректная роль"}, 400)

    executor_name = _clean(data.get("executor_name"))
    await db_session.execute(text(
        "INSERT INTO users (full_name, dept, locale, position, staff_id, password_hash, role, executor_name) "
        "VALUES (:full_name, :dept, :locale, :position, :staff_id, NULL, :role, :executor_name)"
    ), {
        "full_name": full_name,
        "dept": _clean(data.get("dept")) or "",
        "locale": _clean(data.get("locale")),
        "position": _clean(data.get("position")) or "",
        "staff_id": staff_id,
        "role": role,
        "executor_name": executor_name,
    })
    if executor_name:
        await db_session.execute(
            text("DELETE FROM quarantine_status WHERE executor = :e"),
            {"e": executor_name})
    await db_session.commit()
    return _json({"ok": True})


@patch("/admin/users/{user_id:int}/executor-name", guards=[require_auth])
async def api_admin_user_executor_name(
    request: Request, db_session: AsyncSession, user_id: int,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    """Правка поля «Алькор» (точное ФИО из main_afl.executor) у пользователя."""
    admin = await _admin_or_403(request, db_session)
    if not admin:
        return _json({"error": "Нет прав"}, 403)

    target = (await db_session.execute(sa_select(User).where(User.id == user_id))).scalar_one_or_none()
    if not target:
        return _json({"error": "Пользователь не найден"}, 404)

    executor_name = _clean(data.get("executor_name"))
    await db_session.execute(
        text("UPDATE users SET executor_name = :e WHERE id = :id"),
        {"e": executor_name, "id": user_id})
    if executor_name:
        # Сопоставление: убираем исполнителя из карантина совсем.
        await db_session.execute(
            text("DELETE FROM quarantine_status WHERE executor = :e"),
            {"e": executor_name})
    await db_session.commit()
    return _json({"ok": True})


@delete("/admin/users/{user_id:int}", guards=[require_auth], status_code=200)
async def api_admin_user_delete(request: Request, db_session: AsyncSession, user_id: int) -> Response:
    admin = await _admin_or_403(request, db_session)
    if not admin:
        return _json({"error": "Нет прав"}, 403)
    if admin.id == user_id:
        return _json({"error": "Нельзя удалить самого себя"}, 400)

    target = (await db_session.execute(sa_select(User).where(User.id == user_id))).scalar_one_or_none()
    if not target:
        return _json({"error": "Пользователь не найден"}, 404)

    if target.effective_role == "администратор" and not await _has_other_admin(db_session, exclude_id=user_id):
        return _json({"error": "Нельзя удалить последнего администратора"}, 400)

    await db_session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
    await db_session.commit()
    return _json({"ok": True})


@post("/admin/users/{user_id:int}/reset-password", guards=[require_auth])
async def api_admin_user_reset_password(request: Request, db_session: AsyncSession, user_id: int) -> Response:
    admin = await _admin_or_403(request, db_session)
    if not admin:
        return _json({"error": "Нет прав"}, 403)

    target = (await db_session.execute(sa_select(User).where(User.id == user_id))).scalar_one_or_none()
    if not target:
        return _json({"error": "Пользователь не найден"}, 404)

    # Сброс → NULL: при следующем входе пароль = табельный номер + принудительная смена.
    await db_session.execute(text("UPDATE users SET password_hash = NULL WHERE id = :id"), {"id": user_id})
    await db_session.commit()
    return _json({"ok": True})


users_router = Router("/api", route_handlers=[
    api_admin_users, api_admin_missing, api_admin_user_create,
    api_admin_user_executor_name, api_admin_user_delete, api_admin_user_reset_password,
    api_admin_quarantine, api_admin_quarantine_toggle,
])
