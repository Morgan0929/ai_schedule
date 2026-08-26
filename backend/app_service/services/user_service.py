"""
用户业务逻辑层
"""
from sqlalchemy.ext.asyncio import AsyncSession
from app_service.models.user_model import UserModel
from app_service.repository.user_repo import UserRepository
from common.schemas.user import UserCreateDTO, UserLoginDTO, LoginResultDTO, UserDTO
from common.utils.password import hash_password, verify_password
from common.utils.jwt import create_access_token, create_session_id
from common.utils.auth_session import store_login_session
from common.exceptions import BadRequestException, UnauthorizedException, NotFoundException


class UserService:
    """用户服务"""

    def __init__(self, db: AsyncSession):
        self.repo = UserRepository(db)

    async def register(self, dto: UserCreateDTO) -> UserDTO:
        """用户注册"""
        # 检查用户名唯一性
        existing = await self.repo.find_by_username(dto.username)
        if existing:
            raise BadRequestException(f"用户名 '{dto.username}' 已被占用")

        # 创建用户
        user = UserModel(
            username=dto.username,
            email=dto.email,
            password_hash=hash_password(dto.password),
            role=dto.role,
        )
        user = await self.repo.create(user)
        return UserDTO.model_validate(user)

    async def login(self, dto: UserLoginDTO) -> LoginResultDTO:
        """用户登录"""
        # 查询用户
        user = await self.repo.find_by_username(dto.username)
        if not user:
            raise UnauthorizedException("用户名或密码错误")

        if not user.is_active:
            raise UnauthorizedException("账号已被禁用")

        # 验证密码
        if not verify_password(dto.password, user.password_hash):
            raise UnauthorizedException("用户名或密码错误")

        session_id = create_session_id()
        user_dto = UserDTO.model_validate(user)
        await store_login_session(session_id, user_dto)

        # 生成 token
        token = create_access_token(
            user_id=user.id,
            username=user.username,
            role=user.role,
            session_id=session_id,
        )

        return LoginResultDTO(
            token=token,
            session_id=session_id,
            user=user_dto,
        )

    async def get_user(self, user_id: int) -> UserDTO:
        """获取用户信息"""
        user = await self.repo.find_by_id(user_id)
        if not user:
            raise NotFoundException("用户", user_id)
        return UserDTO.model_validate(user)

    async def list_users(self, page: int = 1, page_size: int = 20) -> tuple[list[UserDTO], int]:
        """分页查询用户列表"""
        users, total = await self.repo.list_all(page, page_size)
        return [UserDTO.model_validate(u) for u in users], total
