"""Общие зависимости и guard'ы для роутеров."""

from typing import Any

from litestar.connection import ASGIConnection, Request
from litestar.exceptions import NotAuthorizedException
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from data.config import async_session_factory
from data.models import User


async def get_current_user(request: Request, db_session: AsyncSession) -> User | None:
    user_id = request.session.get("user_id")
    if user_id:
        result = await db_session.execute(sa_select(User).where(User.id == user_id))
        return result.scalar_one_or_none()
    return None


async def require_auth(connection: ASGIConnection, _: Any) -> None:
    user_id = connection.session.get("user_id")
    if not user_id:
        raise NotAuthorizedException()

    # A4: отзыв сессий при сбросе пароля / смене роли / удалении пользователя.
    # Сверяем session_version из cookie с актуальным значением в БД.
    expected = connection.session.get("session_version") or 0
    async with async_session_factory() as db_session:
        current = (await db_session.execute(
            sa_select(User.session_version).where(User.id == user_id)
        )).scalar_one_or_none()

    if current is None or current != expected:
        connection.session.clear()
        raise NotAuthorizedException()


async def require_role(request: Request, db_session: AsyncSession, *roles: str) -> User | None:
    """Текущий пользователь, если его effective_role входит в roles; иначе None.

    Используется внутри хэндлера (после guard'а require_auth), чтобы вернуть 403.
    """
    user = await get_current_user(request, db_session)
    if not user or user.effective_role not in roles:
        return None
    return user


def role_scope_clauses(user) -> tuple[list[str], dict]:
    """Зона видимости по роли: оператор/работник → locale, менеджер → dept.

    Возвращает (SQL-условия без префикса AND, bind-параметры). Для админа/специалиста —
    пустой список (видит всё). Единая точка вместо восьми копий блока (B1).
    """
    clauses: list[str] = []
    params: dict = {}
    if user.effective_role in ("оператор", "работник"):
        clauses.append("executor IN (SELECT executor_name FROM users WHERE locale = :locale)")
        params["locale"] = user.locale
    elif user.effective_role == "менеджер":
        clauses.append("executor_organization = :dept")
        params["dept"] = user.dept
    return clauses, params
