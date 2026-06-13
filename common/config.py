"""
公共配置管理

使用 pydantic-settings 加载环境变量，
支持 .env 文件和直接环境变量覆盖
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置，自动从 .env / 环境变量加载"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # 忽略 .env 中多余字段（如 DATABASE_URL）
    )

    # ============ 环境 ============
    ENV: str = "dev"
    LOG_LEVEL: str = "INFO"
    USE_SQLITE: bool = True  # 开发时无需 Docker，用 SQLite；上线改为 False

    # ============ 数据库 ============
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "ai_schedule_agent"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres123"

    @property
    def database_url(self) -> str:
        """生成 SQLAlchemy async 连接字符串"""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def database_url_sync(self) -> str:
        """生成 SQLAlchemy sync 连接字符串（Alembic 迁移用）"""
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # ============ Redis ============
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 0

    @property
    def redis_url(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # ============ Qdrant ============
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_API_KEY: str = ""

    # ============ DeepSeek ============
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    # ============ 服务端口 ============
    APP_SERVICE_PORT: int = 8000
    CRAWLER_SERVICE_PORT: int = 8001
    AGENT_SERVICE_PORT: int = 8002
    TIMELINE_SERVICE_PORT: int = 8003
    RAG_SERVICE_PORT: int = 8004

    # ============ JWT ============
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440


# 全局单例
settings = Settings()
