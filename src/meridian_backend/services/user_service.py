from sqlalchemy.ext.asyncio import AsyncSession
from meridian_backend.repositories.user_repository import UserRepository
from meridian_backend.models.user import User
from meridian_backend.core.exceptions import UserDoesNotExist

class UserService:
    def __init__(self, user_repository: UserRepository, session: AsyncSession) -> None:
        self.user_repository = user_repository
        self.session = session

    async def get_by_email(self, email:str) -> User:
        user = await self.user_repository.get_by_email(email)
        if user is None:
            raise UserDoesNotExist(email)
        return user