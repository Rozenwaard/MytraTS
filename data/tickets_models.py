"""Модели базы вложений тикетов (tickets.db).

Отдельная база, чтобы blob-файлы (скрины/сканы/xlsx) не раздували операционную mytra.db.
"""

from typing import Optional

from sqlalchemy import Integer, LargeBinary, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class TicketsBase(DeclarativeBase):
    pass


class TicketAttachment(TicketsBase):
    __tablename__ = 'ticket_attachments'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(Integer)
    filename: Mapped[str] = mapped_column(Text)
    content_type: Mapped[Optional[str]] = mapped_column(Text)
    size: Mapped[int] = mapped_column(Integer)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    uploaded_by: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text)
