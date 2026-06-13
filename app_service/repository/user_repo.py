"""
用户数据访问层
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app_service.models import UserModel


class UserRepository:
    """用户 Repository"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def find_by_id(self, user_id: int) -> UserModel | None:
        """按 ID 查询用户"""
        result = await self.db.execute(
            select(UserModel).where(UserModel.id == user_id, UserModel.is_active == True)
        )
        return result.scalar_one_or_none()

    async def find_by_username(self, username: str) -> UserModel | None:
        """按用户名查询"""
        result = await self.db.execute(
            select(UserModel).where(UserModel.username == username)
        )
        return result.scalar_one_or_none()

    async def create(self, user: UserModel) -> UserModel:
        """创建用户"""
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def update(self, user: UserModel) -> UserModel:
        """更新用户"""
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def delete(self, user_id: int) -> bool:
        """软删除用户"""
        user = await self.find_by_id(user_id)
        if user:
            user.is_active = False
            await self.db.flush()
            return True
        return False

    async def list_all(self, page: int = 1, page_size: int = 20) -> tuple[list[UserModel], int]:
        """分页查询用户列表"""
        # 总数
        count_query = select(UserModel).where(UserModel.is_active == True)
        count_result = await self.db.execute(count_query)
        total = len(count_result.scalars().all())

        # 分页
        query = (
            select(UserModel)
            .where(UserModel.is_active == True)
            .offset((page - 1) * page_size)
            .limit(page_size)
            .order_by(UserModel.created_at.desc())
        )
        result = await self.db.execute(query)
        users = list(result.scalars().all())

        return users, total
