"""Application configuration using Pydantic Settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_name: str = "CloudVid Bridge"
    app_env: str = "development"
    debug: bool = False
    secret_key: str = "change-me-in-production"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/callback"
    google_scopes: str = (
        "https://www.googleapis.com/auth/drive.readonly "
        "https://www.googleapis.com/auth/youtube.upload "
        "https://www.googleapis.com/auth/youtube.readonly"
    )

    # Database
    database_url: str = "sqlite+aiosqlite:///./cloudvid_bridge.db"

    # Queue settings
    max_concurrent_uploads: int = 2
    upload_chunk_size: int = 10 * 1024 * 1024  # 10MB

    # Simple authentication
    auth_username: str = ""
    auth_password: str = ""

    @property
    def scopes_list(self) -> list[str]:
        """Return Google scopes as a list."""
        return self.google_scopes.split()

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.app_env == "production"

    @property
    def async_database_url(self) -> str:
        """Get async-compatible database URL.

        Converts Heroku's postgres:// to postgresql+asyncpg://
        and sqlite:// to sqlite+aiosqlite://
        """
        url = self.database_url
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("sqlite://"):
            return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
        return url



@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
