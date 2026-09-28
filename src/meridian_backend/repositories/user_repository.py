from sqlalchemy.ext.asyncio import AsyncSession
from meridian_backend.models.user import User
from sqlalchemy import select
from meridian_backend.db.models.user import UserModel
from meridian_backend.db.mappers import user_model_to_domain


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _user_query():
        return select(UserModel)

    async def get_by_email(self, email: str) -> User | None:
        model = await self.session.scalar(self._user_query().where(UserModel.email == email))
        return user_model_to_domain(model) if model is not None else None

    async def add(self, user: User) -> None:
        model = UserModel(
            id = user.id,
            name = user.name,
            email = user.email,
            password_hash = user.password_hash,
            role = "CUSTOMER",
            is_active = user.is_active
        )
        self.session.add(model)
        await self.session.flush()