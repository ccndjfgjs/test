from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Environment variables override the local .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "SpecIQ Market Intelligence"
    app_env: str = "development"
    database_url: str = "sqlite+aiosqlite:///./catalog.db"
    redis_url: str = "redis://localhost:6379/0"
    use_celery: bool = False
    seed_demo_data: bool = True
    source_user_agent: str = "SpecIQ-Market-Intelligence/0.1 (+authorized-data-ingestion)"
    authorized_source_hosts: str = ""
    ingestion_api_key: str | None = None

    @property
    def allowed_source_hosts(self) -> list[str]:
        return [host.strip() for host in self.authorized_source_hosts.split(",") if host.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
