"""КРО: создание «созревших» клонов по графику проверок.

Запускается cron'ом на сервере (раз в сутки) или вручную:
    cd /opt/mytra && uv run python scripts/kro_maturity.py

Работает с sand.db (песочница УЛР); читает таблицу kro_control (generation/active/next_due).
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.config import sand_session_factory
from services.ulr import materialize_kro_clones


async def main() -> None:
    async with sand_session_factory() as session:
        created = await materialize_kro_clones(session)
    print(f"kro clones created: {created}")


if __name__ == "__main__":
    asyncio.run(main())
