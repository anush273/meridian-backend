from fastapi import FastAPI

from meridian_backend.api.exception_handlers import register_exception_handlers
from meridian_backend.api.routes.health import router as health_router
from meridian_backend.api.routes.orders import router as orders_router
from meridian_backend.core.logging import configure_logging

app = FastAPI(title="Meridian Commerce API", version="0.1.0")
register_exception_handlers(app)
app.state.orders = []
app.state.customers = []
app.state.products = []
app.include_router(health_router)
app.include_router(orders_router)


def main() -> None:
    configure_logging()
