import asyncio
from sqlalchemy import text
from data.config import engine

async def migrate():
    async with engine.begin() as conn:
        # Column may already exist; ignore error
        try:
            await conn.execute(text("ALTER TABLE users ADD COLUMN role TEXT"))
        except Exception:
            pass
        await conn.execute(text("UPDATE users SET role = 'администратор' WHERE dept = 'Отдел организации' AND position = 'Директор'"))
        await conn.execute(text("UPDATE users SET role = 'специалист' WHERE dept = 'Отдел организации' AND role IS NULL"))
        await conn.execute(text("UPDATE users SET role = 'менеджер' WHERE position = 'Начальник отделения' AND role IS NULL"))
        await conn.execute(text("UPDATE users SET role = 'оператор' WHERE role IS NULL"))
        print("Migration OK")

asyncio.run(migrate())
