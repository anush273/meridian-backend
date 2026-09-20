import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from meridian_backend.core.exceptions import (
    CustomerNotFoundError,
    OrderNotFoundError,
    ProductNotFoundError,
)

logger = logging.getLogger(__name__)


async def not_found_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc)},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "Unhandled exception for %s %s",
        request.method,
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


def register_exception_handlers(app: FastAPI) -> None:
    for exception_class in (CustomerNotFoundError, OrderNotFoundError, ProductNotFoundError):
        app.add_exception_handler(exception_class, not_found_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
