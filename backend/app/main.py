"""FastAPI application entry point."""

from contextlib import asynccontextmanager
import logging
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config.settings import get_settings
from app.database.session import dispose_engine
from app.utils.logging import configure_logging
from app.websocket.router import router as websocket_router

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Manage application-wide resources."""

    logger.info("Starting %s", settings.app_name)
    yield
    await dispose_engine()
    logger.info("Stopped %s", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix=settings.api_v1_prefix)
app.include_router(websocket_router)
