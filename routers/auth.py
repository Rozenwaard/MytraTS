import hashlib
import json

from litestar import Router
from litestar.connection import Request
from litestar.enums import RequestEncodingType
from litestar.handlers import get, post
from litestar.params import Body
from litestar.response import Response
from sqlalchemy import select as sa_select, text
from sqlalchemy.ext.asyncio import AsyncSession

from data.models import User
from deps import get_current_user, require_auth


@post("/login")
async def api_login(
    request: Request, db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    staff_id = data.get("staff_id", "")
    password = data.get("password", "")
    if not staff_id:
        return Response(content=json.dumps({"ok": False, "error": "Введите табельный номер"}, ensure_ascii=False), media_type="application/json", status_code=400)

    result = await db_session.execute(sa_select(User).where(User.staff_id == staff_id))
    user = result.scalar_one_or_none()
    if not user:
        return Response(content=json.dumps({"ok": False, "error": "Неверный логин или пароль"}, ensure_ascii=False), media_type="application/json", status_code=401)

    if user.password_hash is None:
        if password != user.staff_id:
            return Response(content=json.dumps({"ok": False, "error": "Неверный логин или пароль"}, ensure_ascii=False), media_type="application/json", status_code=401)
        request.session["user_id"] = user.id
        return Response(content=json.dumps({"ok": True, "change_password": True, "full_name": user.full_name, "role": user.effective_role}, ensure_ascii=False), media_type="application/json")

    if user.password_hash != hashlib.sha256(password.encode()).hexdigest():
        return Response(content=json.dumps({"ok": False, "error": "Неверный логин или пароль"}, ensure_ascii=False), media_type="application/json", status_code=401)

    request.session["user_id"] = user.id
    return Response(content=json.dumps({"ok": True, "change_password": False, "full_name": user.full_name, "role": user.effective_role}, ensure_ascii=False), media_type="application/json")


@get("/me", guards=[require_auth])
async def api_me(request: Request, db_session: AsyncSession) -> Response:
    user = await get_current_user(request, db_session)
    if not user:
        return Response(content=json.dumps({"user": None}, ensure_ascii=False), media_type="application/json", status_code=401)
    return Response(content=json.dumps({"user": {"id": user.id, "full_name": user.full_name, "dept": user.dept, "locale": user.locale, "position": user.position, "staff_id": user.staff_id, "role": user.effective_role}}, ensure_ascii=False), media_type="application/json")


@post("/logout")
async def api_logout(request: Request) -> Response:
    request.session.clear()
    return Response(content=json.dumps({"ok": True}), media_type="application/json")


@post("/change-password", guards=[require_auth])
async def api_change_password(
    request: Request, db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    new_password = data.get("new_password", "")
    confirm_password = data.get("confirm_password", "")
    if len(new_password) < 4:
        return Response(content=json.dumps({"ok": False, "error": "Пароль должен быть не менее 4 символов"}, ensure_ascii=False), media_type="application/json", status_code=400)
    if new_password != confirm_password:
        return Response(content=json.dumps({"ok": False, "error": "Пароли не совпадают"}, ensure_ascii=False), media_type="application/json", status_code=400)
    user_id = request.session.get("user_id")
    await db_session.execute(text("UPDATE users SET password_hash = :hash WHERE id = :id"), {"hash": hashlib.sha256(new_password.encode()).hexdigest(), "id": user_id})
    await db_session.commit()
    return Response(content=json.dumps({"ok": True}), media_type="application/json")


@get("/user/settings", guards=[require_auth])
async def api_get_settings(request: Request, db_session: AsyncSession) -> Response:
    user = await get_current_user(request, db_session)
    if not user:
        return Response(content=json.dumps({"settings": None}), media_type="application/json")
    return Response(content=json.dumps({"settings": json.loads(user.settings) if user.settings else None}, ensure_ascii=False), media_type="application/json")


@post("/user/settings", guards=[require_auth])
async def api_save_settings(
    request: Request,
    db_session: AsyncSession,
    data: dict = Body(media_type=RequestEncodingType.JSON),
) -> Response:
    user = await get_current_user(request, db_session)
    if not user:
        return Response(content=json.dumps({"ok": False}), media_type="application/json", status_code=401)
    settings_json = json.dumps(data.get("settings", {}), ensure_ascii=False)
    await db_session.execute(
        text("UPDATE users SET settings = :s WHERE id = :id"),
        {"s": settings_json, "id": user.id})
    await db_session.commit()
    return Response(content=json.dumps({"ok": True}), media_type="application/json")


@get("/users/search")
async def api_search_users(db_session: AsyncSession, q: str = "") -> Response:
    if len(q) < 2:
        return Response(content=json.dumps([]), media_type="application/json")
    result = await db_session.execute(text("SELECT full_name, position, staff_id FROM users"))
    all_users = [{"full_name": row[0], "position": row[1], "staff_id": row[2]} for row in result]
    q_lower = q.lower()
    filtered = [u for u in all_users if q_lower in u["full_name"].lower()][:5]
    return Response(content=json.dumps(filtered, ensure_ascii=False), media_type="application/json")


auth_router = Router("/api", route_handlers=[
    api_login, api_me, api_logout, api_change_password,
    api_get_settings, api_save_settings, api_search_users,
])
