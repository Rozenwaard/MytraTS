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
