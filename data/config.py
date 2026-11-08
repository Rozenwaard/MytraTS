import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from litestar.plugins.sqlalchemy import SQLAlchemyAsyncConfig, SQLAlchemyPlugin

load_dotenv()

engine = create_async_engine("sqlite+aiosqlite:///mytra.db", echo=False, connect_args={"timeout": 30})
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)

# Отдельная база «сторидб» (архив story_afl + справочник потребителей),
# чтобы не нагружать операционную mytra.db.
story_engine = create_async_engine("sqlite+aiosqlite:///story.db", echo=False, connect_args={"timeout": 30})
story_session_factory = async_sessionmaker(story_engine, expire_on_commit=False)

# Абсолютный путь к story.db — для ATTACH при кросс-БД переносе main_afl → story_afl.
STORY_DB_PATH = str(Path(__file__).resolve().parent.parent / "story.db")

# Флаг «нужен VACUUM» после архивации (ставит routers/fin_report.py, снимает _vacuum.py по cron).
VACUUM_FLAG_PATH = str(Path(__file__).resolve().parent.parent / ".vacuum_needed")

# Отдельная база для вложений тикетов (ticket_attachments) — blob-файлы не раздувают mytra.db.
tickets_engine = create_async_engine("sqlite+aiosqlite:///tickets.db", echo=False, connect_args={"timeout": 30})
tickets_session_factory = async_sessionmaker(tickets_engine, expire_on_commit=False)

TICKETS_DB_PATH = str(Path(__file__).resolve().parent.parent / "tickets.db")

# Песочница для разработки УЛР (libra + копия main_afl + work_catalog).
sand_engine = create_async_engine("sqlite+aiosqlite:///sand.db", echo=False, connect_args={"timeout": 30})
sand_session_factory = async_sessionmaker(sand_engine, expire_on_commit=False)


def _sqlite_pragmas(dbapi_connection, _record):
    """WAL + явный busy_timeout на каждом соединении (B7.1).

    journal_mode=WAL хранится в файле, но ставим на каждом соединении.
    busy_timeout=30000 совпадает с connect_args timeout=30 (не снижаем его).
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


for _engine in (engine, story_engine, tickets_engine, sand_engine):
    event.listens_for(_engine.sync_engine, "connect")(_sqlite_pragmas)


db_config = SQLAlchemyAsyncConfig(
    engine_instance=engine,
    session_maker=async_session_factory,
)
sqlalchemy_plugin = SQLAlchemyPlugin(db_config)

def _load_secret_key() -> str:
    """Litestar CookieBackendConfig требует ключ ровно 16/24/32 байта."""
    key = os.getenv("SECRET_KEY")
    if not key:
        raise RuntimeError(
            "SECRET_KEY не задан. Сгенерируйте: openssl rand -base64 24 "
            "и пропишите в .env"
        )
    if len(key.encode()) not in (16, 24, 32):
        raise RuntimeError(
            f"SECRET_KEY должен быть 16/24/32 байта (сейчас {len(key.encode())} байт). "
            "Сгенерируйте: openssl rand -base64 24"
        )
    return key


SECRET_KEY = _load_secret_key()
