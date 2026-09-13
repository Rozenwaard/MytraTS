"""Состояние загрузок для виджета «Состояние» (ключ-значение в status_state)."""

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_KEYS = ('last_txt_count', 'in_work_at', 'in_work_count', 'new_tasks_at', 'new_tasks_count')

# Допуск при сравнении объёма: строки могут «пропадать» в отчётах сторонней системы.
_TOLERANCE = 10


async def _get(db_session: AsyncSession, key: str) -> str | None:
    r = await db_session.execute(
        text("SELECT value FROM status_state WHERE key = :k"), {"k": key})
    return r.scalar()


async def _set(db_session: AsyncSession, key: str, value: str) -> None:
    await db_session.execute(
        text("INSERT INTO status_state (key, value) VALUES (:k, :v) "
             "ON CONFLICT(key) DO UPDATE SET value = excluded.value"),
        {"k": key, "v": value})


async def set_last_txt_count(db_session: AsyncSession, count: int) -> None:
    """Сохраняет счётчик строк скачанного .txt (для сравнения при следующей загрузке)."""
    await _set(db_session, 'last_txt_count', str(count))
    await db_session.commit()


async def get_status(db_session: AsyncSession) -> dict:
    """Текущее состояние для виджета «Состояние»."""
    return {k: await _get(db_session, k) for k in _KEYS}


async def record_upload(db_session: AsyncSession, total_rows: int, inserted: int) -> None:
    """Определяет исход загрузки и обновляет строки виджета «Состояние».

    - |total_rows − last_txt_count| ≤ 10 → «задания в работе»;
    - иначе, если inserted > 0 → «новые задания»;
    - иначе → игнорируем.
    """
    x_raw = await _get(db_session, 'last_txt_count')
    if x_raw is None:
        return
    try:
        x = int(x_raw)
    except ValueError:
        return

    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    if abs(total_rows - x) <= _TOLERANCE:
        await _set(db_session, 'in_work_at', now)
        await _set(db_session, 'in_work_count', str(total_rows))
    elif inserted > 0:
        await _set(db_session, 'new_tasks_at', now)
        await _set(db_session, 'new_tasks_count', str(inserted))
    # else: игнорируем
    await db_session.commit()
