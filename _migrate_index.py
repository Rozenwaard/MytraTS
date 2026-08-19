import asyncio
from sqlalchemy import text
from data.config import engine


async def migrate():
    async with engine.begin() as conn:
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_main_afl_task_number ON main_afl (task_number)"
        ))
        print("Index ix_main_afl_task_number created (or already exists)")


asyncio.run(migrate())
