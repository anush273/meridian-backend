from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from meridian_backend.api.exception_handlers import register_exception_handlers
from meridian_backend.api.routes.health import router as health_router
from meridian_backend.api.routes.orders import router as orders_router
from meridian_backend.core.config import get_settings
from meridian_backend.core.logging import configure_logging
from meridian_backend.core.middleware import request_context_middleware
from meridian_backend.db.session import create_engine, create_session_factory


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    engine = create_engine(get_settings().database_url)
    app.state.session_factory = create_session_factory(engine)
    try:
        yield
    finally:
        await engine.dispose()


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)
register_exception_handlers(app)
app.middleware("http")(request_context_middleware)
app.include_router(health_router)
app.include_router(orders_router)


def main() -> None:
    configure_logging()
