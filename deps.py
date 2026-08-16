"""Общие зависимости и guard'ы для роутеров."""

from typing import Any

from litestar.connection import ASGIConnection, Request
from litestar.exceptions import NotAuthorizedException
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from data.models import User


async def get_current_user(request: Request, db_session: AsyncSession) -> User | None:
    user_id = request.session.get("user_id")
    if user_id:
        result = await db_session.execute(sa_select(User).where(User.id == user_id))
        return result.scalar_one_or_none()
    return None


def require_auth(connection: ASGIConnection, _: Any) -> None:
    if not connection.session.get("user_id"):
        raise NotAuthorizedException()
