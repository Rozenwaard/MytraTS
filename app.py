"""Точка входа приложения MytraTS.

Собирает Litestar-приложение из тематических роутеров (см. routers/).
"""

import json

from dotenv import load_dotenv
from litestar import Litestar
from litestar.config.cors import CORSConfig
from litestar.exceptions import NotFoundException
from litestar.middleware.session.client_side import CookieBackendConfig
from litestar.response import Response

from data.config import sqlalchemy_plugin, SECRET_KEY
from routers.auth import auth_router
from routers.dashboard import dashboard_router
from routers.lookups import lookups_router
from routers.main_afl import main_afl_router
from routers.reestr import reestr_router
from routers.report import report_router
from routers.story import story_router
from routers.upload import upload_router

load_dotenv()
session_config = CookieBackendConfig(secret=SECRET_KEY.encode())

cors_config = CORSConfig(allow_origins=["http://localhost:5173"], allow_credentials=True)

app = Litestar(
    route_handlers=[
        auth_router,
        upload_router,
        main_afl_router,
        reestr_router,
        report_router,
        story_router,
        dashboard_router,
        lookups_router,
    ],
    plugins=[sqlalchemy_plugin],
    middleware=[session_config.middleware],
    cors_config=cors_config,
    exception_handlers={NotFoundException: lambda r, e: Response(content=json.dumps({"error": "Not found"}), media_type="application/json", status_code=404)},
    request_max_body_size=35 * 1024 * 1024,
)
