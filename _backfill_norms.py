import asyncio

from sqlalchemy import text

from data.config import async_session_factory
from services.premium import apply_norms


async def main() -> None:
    async with async_session_factory() as session:
        await apply_norms(session)  # task_numbers=None → все строки main_afl
        await session.commit()

        total = (await session.execute(text("SELECT COUNT(*) FROM main_afl"))).scalar()
        norm_set = (await session.execute(text("SELECT COUNT(*) FROM main_afl WHERE norm IS NOT NULL"))).scalar()
        extra_set = (await session.execute(text("SELECT COUNT(*) FROM main_afl WHERE extra IS NOT NULL"))).scalar()
        print(f"main_afl: всего {total}, norm задан у {norm_set}, extra задан у {extra_set}")


if __name__ == "__main__":
    asyncio.run(main())
