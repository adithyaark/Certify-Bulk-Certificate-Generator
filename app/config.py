from functools import lru_cache
from pathlib import Path

from pydantic import Field
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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache

def get_settings() -> Settings:
    return Settings()


def get_storage_path() -> Path:
    return Path(get_settings().storage_dir).resolve()
