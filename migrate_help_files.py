import asyncio

from data.config import engine
from data.models import Base


async def migrate():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Таблица 'help_files' готова")


asyncio.run(migrate())
