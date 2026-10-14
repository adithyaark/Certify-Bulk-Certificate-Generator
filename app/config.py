from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = Field(
        default="sqlite:///./storage/app.db",
        validation_alias="DATABASE_URL",
    )
    storage_dir: str = Field(
        default="./storage",
        validation_alias="STORAGE_DIR",
    )
    max_recipients_per_job: int = Field(
        default=1000,
        ge=1,
        validation_alias="MAX_RECIPIENTS_PER_JOB",
    )
    email_enabled: bool = Field(
        default=False,
        validation_alias="EMAIL_ENABLED",
    )
    smtp_host: str = Field(
        default="smtp.gmail.com",
        validation_alias="SMTP_HOST",
    )
    smtp_port: int = Field(
        default=587,
        ge=1,
        le=65535,
        validation_alias="SMTP_PORT",
    )
    smtp_username: str | None = Field(
        default=None,
        validation_alias="SMTP_USERNAME",
    )
    smtp_password: SecretStr | None = Field(
        default=None,
        validation_alias="SMTP_PASSWORD",
    )
    smtp_from_email: str | None = Field(
        default=None,
        validation_alias="SMTP_FROM_EMAIL",
    )
    smtp_from_name: str = Field(
        default="Certify",
        validation_alias="SMTP_FROM_NAME",
    )
    smtp_use_tls: bool = Field(
        default=True,
        validation_alias="SMTP_USE_TLS",
    )
    smtp_use_ssl: bool = Field(
        default=False,
        validation_alias="SMTP_USE_SSL",
    )
    smtp_timeout: float = Field(
        default=30.0,
        gt=0,
        validation_alias="SMTP_TIMEOUT",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        populate_by_name=True,
    )


@lru_cache

def get_settings() -> Settings:
    return Settings()


def get_storage_path() -> Path:
    return Path(get_settings().storage_dir).resolve()
