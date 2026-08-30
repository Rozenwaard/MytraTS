import asyncio
import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

from data.config import engine
from data.models import Base
from services.help import OPERATOR_BLOCKS, parse_instruction_docx, parse_xlsx_to_blocks


async def migrate():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    root = Path(__file__).parent
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    async with engine.begin() as conn:
        docx = root / "Инструкция.docx"
        if docx.exists():
            blocks = parse_instruction_docx(docx.read_bytes())
            await conn.execute(
                text("INSERT OR REPLACE INTO help_pages (key, title, content, updated_at) VALUES (:k, :t, :c, :u)"),
                {"k": "instruction", "t": "Инструкция",
                 "c": json.dumps({"blocks": blocks}, ensure_ascii=False), "u": now},
            )

        xlsx = root / "Тарифы.xlsx"
        if xlsx.exists():
            blocks = parse_xlsx_to_blocks(xlsx.read_bytes())
            await conn.execute(
                text("INSERT OR REPLACE INTO help_pages (key, title, content, updated_at) VALUES (:k, :t, :c, :u)"),
                {"k": "tariffs", "t": "Тарифы",
                 "c": json.dumps({"blocks": blocks}, ensure_ascii=False), "u": now},
            )

        await conn.execute(
            text("INSERT OR REPLACE INTO help_pages (key, title, content, updated_at) VALUES (:k, :t, :c, :u)"),
            {"k": "operators", "t": "Операторы",
             "c": json.dumps({"blocks": OPERATOR_BLOCKS}, ensure_ascii=False), "u": now},
        )

    print("help_pages: таблица создана и заполнена (инструкция, тарифы, операторы)")


asyncio.run(migrate())
