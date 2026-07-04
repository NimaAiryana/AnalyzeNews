"""FastAPI application entry point for the Crypto News Analysis Engine."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import routes_analyze, routes_data, routes_symbols
from app.config import get_settings
from app.db.mongodb import close_mongo_connection, connect_to_mongo
from app.seed import seed_default_symbols
from app.utils.logging import configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()
    await connect_to_mongo()
    if settings.seed_default_symbols:
        await seed_default_symbols()
    logger.info("%s v%s started (AI provider: %s)", settings.app_name, __version__, settings.ai_provider)
    yield
    await close_mongo_connection()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="Headless crypto news crawler + AI fundamental analysis engine.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(routes_symbols.router)
    app.include_router(routes_analyze.router)
    app.include_router(routes_data.router)

    @app.get("/health", tags=["health"])
    async def health():
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
