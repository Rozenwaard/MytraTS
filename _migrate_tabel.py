import asyncio

from sqlalchemy import text

from data.config import engine
from data.models import Base


async def migrate():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Для таблицы, созданной ранее без колонок position/name.
        for col in ("position", "name"):
            try:
                await conn.execute(text(f"ALTER TABLE tabel ADD COLUMN {col} TEXT"))
            except Exception:
                pass
    print("Таблица 'tabel' готова (в т.ч. колонки position, name)")


asyncio.run(migrate())
