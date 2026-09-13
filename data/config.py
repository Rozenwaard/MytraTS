import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from litestar.plugins.sqlalchemy import SQLAlchemyAsyncConfig, SQLAlchemyPlugin

load_dotenv()

engine = create_async_engine("sqlite+aiosqlite:///mytra.db", echo=False)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)

# Отдельная база «сторидб» (архив story_afl + справочник потребителей),
# чтобы не нагружать операционную mytra.db.
story_engine = create_async_engine("sqlite+aiosqlite:///story.db", echo=False)
story_session_factory = async_sessionmaker(story_engine, expire_on_commit=False)

# Абсолютный путь к story.db — для ATTACH при кросс-БД переносе main_afl → story_afl.
STORY_DB_PATH = str(Path(__file__).resolve().parent.parent / "story.db")

db_config = SQLAlchemyAsyncConfig(
    engine_instance=engine,
    session_maker=async_session_factory,
)
sqlalchemy_plugin = SQLAlchemyPlugin(db_config)

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
