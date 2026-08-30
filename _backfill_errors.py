import asyncio

from sqlalchemy import text

from data.config import async_session_factory
from services.report_check import recompute_errors


async def main() -> None:
    async with async_session_factory() as session:
        n = await recompute_errors(session)  # task_numbers=None → все строки main_afl

        total = (await session.execute(text("SELECT COUNT(*) FROM main_afl"))).scalar()
        with_errors = (await session.execute(text("SELECT COUNT(*) FROM main_afl WHERE errors IS NOT NULL AND errors != ''"))).scalar()
        print(f"main_afl: пересчитано {n}, всего {total}, с ошибками {with_errors}")


if __name__ == "__main__":
    asyncio.run(main())
