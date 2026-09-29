import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from meridian_backend.core.exceptions import (
    CustomerNotFoundError,
    InactiveUserError,
    InvalidCredentialsError,
    OrderNotFoundError,
    ProductNotFoundError,
    UserAlreadyExistsError,
    UserDoesNotExist,
)

logger = logging.getLogger(__name__)


async def not_found_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc)},
    )


async def conflict_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)})


async def invalid_credentials_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": str(exc)})


async def inactive_user_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": str(exc)})


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
    for exception_class in (
        CustomerNotFoundError,
        OrderNotFoundError,
        ProductNotFoundError,
        UserDoesNotExist,
    ):
        app.add_exception_handler(exception_class, not_found_exception_handler)
    app.add_exception_handler(UserAlreadyExistsError, conflict_exception_handler)
    app.add_exception_handler(InvalidCredentialsError, invalid_credentials_exception_handler)
    app.add_exception_handler(InactiveUserError, inactive_user_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
