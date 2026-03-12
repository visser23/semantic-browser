"""FastAPI app factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from semantic_browser import __version__
from semantic_browser.service.routes import router, shutdown_registry
from semantic_browser.service.settings import load_service_settings


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    try:
        yield
    finally:
        await shutdown_registry()


def create_app() -> FastAPI:
    settings = load_service_settings()
    app = FastAPI(title="semantic-browser", version=__version__, lifespan=_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allow_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-API-Token"],
    )
    app.include_router(router)
    return app
