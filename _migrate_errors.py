import asyncio
from sqlalchemy import text
from data.config import engine, async_session_factory
from services.report_check import recompute_errors


async def migrate():
    async with engine.begin() as conn:
        try:
            await conn.execute(text("ALTER TABLE main_afl ADD COLUMN errors TEXT"))
            print("Column 'errors' added")
        except Exception:
            print("Column 'errors' already exists (skipped)")

    async with async_session_factory() as db_session:
        n = await recompute_errors(db_session)
        print(f"Backfill OK: {n} rows")


asyncio.run(migrate())
