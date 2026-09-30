from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from meridian_backend.core.config import Settings
from meridian_backend.core.exceptions import (
    InactiveUserError,
    InvalidCredentialsError,
    UserAlreadyExistsError,
    UserDoesNotExist,
    WrongPasswordError,
)
from meridian_backend.core.security import create_access_token, hash_password, verify_password
from meridian_backend.models.user import User, UserRole
from meridian_backend.repositories.user_repository import UserRepository



class AuthService:
    def __init__(
        self, user_repository: UserRepository, session: AsyncSession, settings: Settings
    ) -> None:
        self.user_repository = user_repository
        self.session = session
        self.settings = settings

    async def get_by_email(self, email: str) -> User:
        user = await self.user_repository.get_by_email(email)
        if user is None:
            raise UserDoesNotExist(email)
        return user

    async def register(self, name: str, email: str, password: str) -> User:
        async with self.session.begin():
            existing = await self.user_repository.get_by_email(email)
            if existing is not None:
                raise UserAlreadyExistsError(email)
            user = User(
                id=uuid4(),
                name=name,
                email=email,
                password_hash=hash_password(password),
                role=UserRole.CUSTOMER,
                is_active=True,
            )
            await self.user_repository.add(user)
        return user

    async def authenticate(self, email: str, password: str) -> User:
        user = await self.user_repository.get_by_email(email)
        if user is None:
            raise InvalidCredentialsError()
        if not verify_password(password, user.password_hash):
            raise WrongPasswordError()
        if not user.is_active:
            raise InactiveUserError()
        return user

    async def login(self, email: str, password: str) -> str:
        user = await self.authenticate(email=email, password=password)
        return create_access_token(user_id=user.id, settings=self.settings)
