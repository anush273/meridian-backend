from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from meridian_backend.core.exceptions import UserAlreadyExistsError
from meridian_backend.db.mappers import user_model_to_domain
from meridian_backend.db.models.user import UserModel
from meridian_backend.models.user import User


def _is_duplicate_email(error: IntegrityError) -> bool:
    """Identify email uniqueness violations from PostgreSQL or SQLite."""
    # asyncpg keeps constraint details on the underlying driver exception.
    driver_error = getattr(error.orig, "__cause__", None)
    sqlstate = getattr(driver_error, "sqlstate", None)
    constraint = getattr(driver_error, "constraint_name", None)

    if sqlstate == "23505" and constraint == "users_email_key":
        return True

    return str(error.orig) == "UNIQUE constraint failed: users.email"


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session


    async def get_by_email(self, email: str) -> User | None:
        query = select(UserModel).where(UserModel.email == email)
        model = await self.session.scalar(query)
        return user_model_to_domain(model) if model is not None else None
    
    async def get_by_id(self, user_id: UUID) -> User | None:
        query = select(UserModel).where(UserModel.id == user_id)
        model = await self.session.scalar(query)
        return user_model_to_domain(model) if model is not None else None

    async def add(self, user: User) -> None:
        model = UserModel(
            id=user.id,
            name=user.name,
            email=user.email,
            password_hash=user.password_hash,
            role=user.role,
            is_active=user.is_active,
        )
        self.session.add(model)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            if _is_duplicate_email(exc):
                raise UserAlreadyExistsError(user.email) from exc
            raise



