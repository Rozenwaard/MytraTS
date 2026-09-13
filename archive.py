"""Архивация main_afl → story_afl → consumers.

Запуск по cron 22-го числа в 22:00:
    0 22 22 * * cd /path/to/MytraTS && uv run python archive.py >> /var/log/mytra-archive.log 2>&1
"""

import asyncio
import sys
from datetime import date

from data.config import async_session_factory, story_session_factory
from services.archive import (
    last_report_period, preview, archive_main_to_story, fill_consumers,
)


async def main() -> None:
    dry_run = "--dry-run" in sys.argv
    today = date.today()
    report_str, month_str = last_report_period(today)
    tag = " (DRY-RUN)" if dry_run else ""
    print(f"[archive] дата={today.isoformat()} последний_отчёт={report_str}{tag}")

    if dry_run:
        async with async_session_factory() as main_session:
            total, mps = await preview(main_session, report_str, month_str)
        print(f"[archive] строк к переносу: {total}, разных точек учёта: {mps}")
        return

    async with async_session_factory() as main_session:
        moved, metering_points = await archive_main_to_story(main_session, report_str, month_str)

    async with story_session_factory() as story_session:
        filled = await fill_consumers(story_session, metering_points)

    print(f"[archive] перенесено строк: {moved}, обновлено точек учёта в consumers: {filled}")


if __name__ == "__main__":
    asyncio.run(main())
