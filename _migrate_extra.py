import asyncio

from sqlalchemy import text

from data.config import engine
from data.models import Base


async def migrate():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # main_afl: extra INTEGER
        try:
            await conn.execute(text("ALTER TABLE main_afl ADD COLUMN extra INTEGER"))
        except Exception:
            pass

        # main_afl: norm FLOAT -> INTEGER (пересоздаём колонку)
        try:
            await conn.execute(text("ALTER TABLE main_afl RENAME COLUMN norm TO norm_old"))
            await conn.execute(text("ALTER TABLE main_afl ADD COLUMN norm INTEGER"))
            await conn.execute(text("UPDATE main_afl SET norm = CAST(norm_old AS INTEGER) WHERE norm_old IS NOT NULL"))
            await conn.execute(text("ALTER TABLE main_afl DROP COLUMN norm_old"))
        except Exception:
            pass

        # utalo: norm_sum FLOAT -> INTEGER
        try:
            await conn.execute(text("ALTER TABLE utalo RENAME COLUMN norm_sum TO norm_sum_old"))
            await conn.execute(text("ALTER TABLE utalo ADD COLUMN norm_sum INTEGER"))
            await conn.execute(text("UPDATE utalo SET norm_sum = CAST(norm_sum_old AS INTEGER) WHERE norm_sum_old IS NOT NULL"))
            await conn.execute(text("ALTER TABLE utalo DROP COLUMN norm_sum_old"))
        except Exception:
            pass

    print("Миграция: main_afl.norm/extra INTEGER, utalo.norm_sum INTEGER")


asyncio.run(migrate())
