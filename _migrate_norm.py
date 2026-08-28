import asyncio

from sqlalchemy import text

from data.config import engine
from data.models import Base

# (kind, planned, detail) для кодов/причин (carte.id 27..41)
CARTE_CODE_ROWS = {
    27: ("additional", None, "Несоответствие тарифных зон"),
    28: ("additional", None, "Несоответствие номеров ПУ и ДЭС"),
    29: ("replacement", 10, "Объект отключен"),
    30: ("replacement", 10, "Отсутствует связь с ВПУ"),
    31: ("replacement", 10, "Установлен новый ВПУ"),
    32: ("replacement", 10, "Коммерческий объект"),
    33: ("replacement", 10, "Объект эксплуатируется"),
    34: ("replacement", 0, "Отсутствует тип ПУ в справочнике Алькора"),
    35: ("replacement", 0, "На земельном участке выявлен жилой дом"),
    36: ("replacement", 0, "Земельный участок не присоединён к сети"),
    37: ("replacement", 0, "Причина невыполнения: Нет доступа до ПУ"),
    38: ("replacement", 10, "Объект не эксплуатируется"),
    39: ("replacement", 10, "Объект отсутствует"),
    40: ("replacement", 0, "Причина невыполнения: Помещение не найдено"),
    41: ("additional", None, "Несоответствие разрядности"),
}


async def migrate():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for col, ctype in (("kind", "TEXT"), ("planned", "FLOAT"), ("detail", "TEXT")):
            try:
                await conn.execute(text(f"ALTER TABLE carte ADD COLUMN {col} {ctype}"))
            except Exception:
                pass

        # Базовые тарифы (id 1..26)
        await conn.execute(text("UPDATE carte SET kind = 'base' WHERE id BETWEEN 1 AND 26"))

        # Коды и причины (id 27..41)
        for cid, (kind, planned, detail) in CARTE_CODE_ROWS.items():
            await conn.execute(
                text("UPDATE carte SET kind = :k, planned = :p, detail = :d WHERE id = :i"),
                {"k": kind, "p": planned, "d": detail, "i": cid},
            )

        # Универсальный дополнительный тариф «Выполнение задания в Алькоре» (+5)
        await conn.execute(text("""
            INSERT OR IGNORE INTO carte (id, title, absolute, price, kind, planned, detail)
            VALUES (42, 'Выполнение задания в Алькоре', 5, NULL, 'additional', NULL, NULL)
        """))
        await conn.execute(text(
            "UPDATE carte SET absolute = 5, kind = 'additional', planned = NULL, detail = NULL WHERE id = 42"
        ))

    print("Миграция нормативов: carte дополнен kind/planned/detail + «Выполнение задания в Алькоре»")


asyncio.run(migrate())
