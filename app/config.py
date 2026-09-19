from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "production", "test"] = Field(
        default="development", alias="APP_ENV"
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/doc_intel",
        alias="DATABASE_URL",
    )
    sync_database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/doc_intel",
        alias="SYNC_DATABASE_URL",
    )

    # Redis & Celery
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    celery_broker_url: str = Field(default="redis://localhost:6379/1", alias="CELERY_BROKER_URL")

    # Auth
    jwt_secret: SecretStr = Field(
        default=SecretStr("default-insecure-secret-for-dev-only-min-32-chars"),
        alias="JWT_SECRET",
    )
    jwt_expire_minutes: int = Field(default=1440, alias="JWT_EXPIRE_MINUTES")

    # CORS
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        alias="CORS_ORIGINS",
    )

    # Storage
    storage_backend: Literal["local", "s3"] = Field(default="local", alias="STORAGE_BACKEND")
    storage_path: str = Field(default="/app/storage", alias="STORAGE_PATH")
    s3_endpoint: str = Field(default="http://localhost:9000", alias="S3_ENDPOINT")
    s3_bucket: str = Field(default="documents", alias="S3_BUCKET")
    s3_access_key: SecretStr = Field(default=SecretStr("minioadmin"), alias="S3_ACCESS_KEY")
    s3_secret_key: SecretStr = Field(default=SecretStr("minioadmin"), alias="S3_SECRET_KEY")

    # Upload Constraints
    max_upload_mb: int = Field(default=25, alias="MAX_UPLOAD_MB")
    max_pages: int = Field(default=150, alias="MAX_PAGES")
    max_image_pixels: int = Field(default=89478485, alias="MAX_IMAGE_PIXELS")
    allowed_mime: list[str] = Field(
        default=["application/pdf", "image/jpeg", "image/png"],
        alias="ALLOWED_MIME",
    )
    upload_rate_limit: str = Field(default="10/minute", alias="UPLOAD_RATE_LIMIT")

    # Extractor & LLM
    extractor: Literal["hybrid", "llm", "rules", "mock"] = Field(
        default="hybrid", alias="EXTRACTOR"
    )
    gemini_api_key: SecretStr | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-3.6-flash", alias="GEMINI_MODEL")
    llm_timeout_s: int = Field(default=30, alias="LLM_TIMEOUT_S")
    llm_max_concurrency: int = Field(default=5, alias="LLM_MAX_CONCURRENCY")
    llm_send_image: Literal["auto", "always", "never"] = Field(
        default="auto", alias="LLM_SEND_IMAGE"
    )

    # OCR
    tesseract_langs: str = Field(default="eng+hin", alias="TESSERACT_LANGS")
    render_dpi: int = Field(default=200, alias="RENDER_DPI")
    text_layer_min_chars: int = Field(default=50, alias="TEXT_LAYER_MIN_CHARS")

    # Confidence Thresholds
    conf_extracted_min: float = Field(default=0.85, alias="CONF_EXTRACTED_MIN")
    conf_partial_min: float = Field(default=0.60, alias="CONF_PARTIAL_MIN")

    # Workers
    worker_concurrency: int = Field(default=4, alias="WORKER_CONCURRENCY")
    task_soft_time_limit: int = Field(default=300, alias="TASK_SOFT_TIME_LIMIT")
    task_hard_time_limit: int = Field(default=360, alias="TASK_HARD_TIME_LIMIT")


@lru_cache
def get_settings() -> Settings:
    return Settings()
