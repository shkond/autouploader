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
    app_name: str = "AutoUploader"
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
        "https://www.googleapis.com/auth/youtube"
    )

    # Database
    database_url: str = "sqlite+aiosqlite:///./autouploader.db"

    # Queue settings
    max_concurrent_uploads: int = 2
    upload_chunk_size: int = 10 * 1024 * 1024  # 10MB

    @property
    def scopes_list(self) -> list[str]:
        """Return Google scopes as a list."""
        return self.google_scopes.split()

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
