import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from litestar.plugins.sqlalchemy import SQLAlchemyAsyncConfig, SQLAlchemyPlugin

load_dotenv()

engine = create_async_engine("sqlite+aiosqlite:///mytra.db", echo=False)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)

db_config = SQLAlchemyAsyncConfig(
    engine_instance=engine,
    session_maker=async_session_factory,
)
sqlalchemy_plugin = SQLAlchemyPlugin(db_config)

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
