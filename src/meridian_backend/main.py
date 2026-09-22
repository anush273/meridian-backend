from contextlib import asynccontextmanager

from fastapi import FastAPI

from meridian_backend.api.exception_handlers import register_exception_handlers
from meridian_backend.api.routes.health import router as health_router
from meridian_backend.api.routes.orders import router as orders_router
from meridian_backend.core.config import get_settings
from meridian_backend.core.logging import configure_logging
from meridian_backend.models.customer import Customer
from meridian_backend.models.order import Order
from meridian_backend.models.product import Product


@asynccontextmanager
async def lifespan(app: FastAPI):
    orders: list[Order] = []
    customers: list[Customer] = []
    products: list[Product] = []
    app.state.orders = orders
    app.state.customers = customers
    app.state.products = products

    yield

    app.state.orders.clear()
    app.state.customers.clear()
    app.state.products.clear()


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)
register_exception_handlers(app)
app.include_router(health_router)
app.include_router(orders_router)


def main() -> None:
    configure_logging()
