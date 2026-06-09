"""Factory `create_app()` — titik masuk pembuatan ASGI app FastAPI."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import Settings, get_settings
from .errors import install_exception_handlers
from .logging import configure_logging
from .middleware import install_middleware
from .observability import install_observability
from .openapi import install_openapi, openapi_kwargs


def create_app(settings: Settings | None = None) -> FastAPI:
    """Buat dan kembalikan ASGI app FastAPI yang sudah dikonfigurasi."""
    cfg = settings or get_settings()
    configure_logging(cfg.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        install_observability(app, cfg)
        yield

    app = FastAPI(**openapi_kwargs(cfg), lifespan=lifespan)

    install_middleware(app, cfg)
    install_exception_handlers(app)
    install_openapi(app, cfg)

    from .api.router import api_router

    app.include_router(api_router)

    return app


app = create_app()
