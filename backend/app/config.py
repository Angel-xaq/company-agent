from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # 后端项目的根路径


class Settings(BaseSettings):
    # 基础
    JWT_SECRET_KEY: str
    DATABASE_URL: str
    JWT_ALGORITHM: str = "HS256"
    # Access Token 15 分钟；Refresh Token 7 天
    JWT_ACCESS_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_EXPIRE_DAYS: int = 7
    REFRESH_COOKIE_NAME: str = "refresh_token"
    COOKIE_SECURE: bool = False
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # 大模型（OpenAI 兼容协议）
    LLM_KEY: str = ""
    LLM_BASE_URL: str = "https://api.deepseek.com/v1"
    LLM_MODEL: str = "deepseek-flash"
    LLM_TEMPERATURE: float = 0.2
    LLM_TIMEOUT: int = 60

    # Embedding
    EMBEDDING_PROVIDER: str = "local"  # local / openai
    EMBEDDING_KEY: str = ""
    EMBEDDING_BASE_URL: str = ""
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    EMBEDDING_DIM: int = 1024

    # 向量库
    VECTOR_STORE: str = "chroma"  # chroma / pgvector
    CHROMA_DIR: str = str(BASE_DIR / "data" / "chroma")

    # 文件
    UPLOAD_DIR: str = str(BASE_DIR / "uploads")
    KNOWLEDGE_MAX_MB: int = 20

    # 业务规则
    TIMEZONE: str = "Asia/Shanghai"
    BUSINESS_START: str = "09:30"
    BUSINESS_END: str = "21:00"
    SLOT_MINUTES: int = 30
    BOOKING_MAX_HOURS: int = 4
    BOOKING_MAX_DAYS: int = 30
    BOOKING_MAX_PER_DAY: int = 3

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


# 配置项来自 .env，Pylance 无法感知，故忽略“缺少参数”提示
settings = Settings()  # type: ignore[call-arg]
