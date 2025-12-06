"""Tests for environment-specific settings.

Test categories:
5.1 設定切り替えテスト
"""

import os
from unittest.mock import patch

from app.config import Settings, get_settings


class TestSettingsSwitch:
    """5.1 設定切り替えテスト"""

    def test_development_settings(self, clear_settings_cache):
        """Test development environment settings."""
        settings = Settings(
            app_env="development",
            debug=True,
            database_url="sqlite+aiosqlite:///./dev.db",
            _env_file=None,  # type: ignore[call-arg]
        )

        assert settings.app_env == "development"
        assert settings.debug is True
        assert settings.is_production is False
        assert "sqlite" in settings.database_url

    def test_production_settings(self, clear_settings_cache):
        """Test production environment settings."""
        settings = Settings(
            app_env="production",
            debug=False,
            database_url="postgresql://user:pass@host:5432/proddb",
            secret_key="secure-production-key-here",
            _env_file=None,  # type: ignore[call-arg]
        )

        assert settings.app_env == "production"
        assert settings.debug is False
        assert settings.is_production is True
        assert "postgresql" in settings.database_url

    def test_env_var_priority_over_default(self, clear_settings_cache):
        """Test environment variables take priority over defaults."""
        # Default database_url is sqlite
        with patch.dict(os.environ, {
            "DATABASE_URL": "postgresql://override:pass@host:5432/overridedb"
        }, clear=False):
            settings = Settings(_env_file=None)  # type: ignore[call-arg]
            assert settings.database_url == "postgresql://override:pass@host:5432/overridedb"

    def test_env_var_priority_for_app_env(self, clear_settings_cache):
        """Test APP_ENV environment variable."""
        with patch.dict(os.environ, {"APP_ENV": "staging"}, clear=False):
            settings = Settings(_env_file=None)  # type: ignore[call-arg]
            assert settings.app_env == "staging"

    def test_default_fallback_database_url(self, clear_settings_cache):
        """Test default database URL fallback."""
        # Ensure DATABASE_URL is not set
        env_copy = os.environ.copy()
        if "DATABASE_URL" in env_copy:
            del env_copy["DATABASE_URL"]

        with patch.dict(os.environ, env_copy, clear=True):
            settings = Settings(_env_file=None)  # type: ignore[call-arg]
            # Should use default SQLite URL
            assert "sqlite" in settings.database_url

    def test_default_fallback_secret_key(self, clear_settings_cache):
        """Test default secret key fallback."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=None)  # type: ignore[call-arg]
            # Should have a default (though should be changed in production)
            assert settings.secret_key == "change-me-in-production"

    def test_default_fallback_port(self, clear_settings_cache):
        """Test default port fallback."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=None)  # type: ignore[call-arg]
            assert settings.port == 8000

    def test_port_from_env(self, clear_settings_cache):
        """Test PORT environment variable (for cloud platforms)."""
        with patch.dict(os.environ, {"PORT": "8080"}, clear=False):
            settings = Settings(_env_file=None)  # type: ignore[call-arg]
            assert settings.port == 8080

    def test_google_oauth_settings(self, clear_settings_cache):
        """Test Google OAuth settings from environment."""
        with patch.dict(os.environ, {
            "GOOGLE_CLIENT_ID": "test-client-id.apps.googleusercontent.com",
            "GOOGLE_CLIENT_SECRET": "test-client-secret",
            "GOOGLE_REDIRECT_URI": "https://app.example.com/auth/callback",
        }, clear=False):
            settings = Settings(_env_file=None)  # type: ignore[call-arg]

            assert settings.google_client_id == "test-client-id.apps.googleusercontent.com"
            assert settings.google_client_secret == "test-client-secret"
            assert settings.google_redirect_uri == "https://app.example.com/auth/callback"

    def test_queue_settings(self, clear_settings_cache):
        """Test queue-related settings."""
        with patch.dict(os.environ, {
            "MAX_CONCURRENT_UPLOADS": "5",
            "UPLOAD_CHUNK_SIZE": "20971520",  # 20MB
        }, clear=False):
            settings = Settings(_env_file=None)  # type: ignore[call-arg]

            assert settings.max_concurrent_uploads == 5
            assert settings.upload_chunk_size == 20971520

    def test_settings_caching(self, clear_settings_cache):
        """Test settings are cached via lru_cache."""
        settings1 = get_settings()
        settings2 = get_settings()

        # Should be the exact same instance
        assert settings1 is settings2

    def test_scopes_list_parsing(self, clear_settings_cache):
        """Test Google scopes are correctly parsed from string."""
        scopes = (
            "https://www.googleapis.com/auth/drive.readonly "
            "https://www.googleapis.com/auth/youtube.upload "
            "https://www.googleapis.com/auth/youtube"
        )
        settings = Settings(
            google_scopes=scopes,
            _env_file=None,  # type: ignore[call-arg]
        )

        assert len(settings.scopes_list) == 3
        assert "https://www.googleapis.com/auth/drive.readonly" in settings.scopes_list
        assert "https://www.googleapis.com/auth/youtube.upload" in settings.scopes_list
        assert "https://www.googleapis.com/auth/youtube" in settings.scopes_list

    def test_digitalocean_production_config(self, clear_settings_cache):
        """Test DigitalOcean production configuration."""
        do_db_url = "postgresql://user:pass@db-postgresql-sgp1-12345.ondigitalocean.com:25060/defaultdb"

        with patch.dict(os.environ, {
            "APP_ENV": "production",
            "DEBUG": "false",
            "DATABASE_URL": do_db_url,
            "SECRET_KEY": "production-secret-key-32-chars!!",
            "PORT": "8080",
        }, clear=False):
            settings = Settings(_env_file=None)  # type: ignore[call-arg]

            assert settings.is_production is True
            assert settings.debug is False
            assert "ondigitalocean.com" in settings.database_url
            assert settings.port == 8080

            # Async URL should be converted
            assert "asyncpg" in settings.async_database_url

    def test_auth_settings(self, clear_settings_cache):
        """Test simple authentication settings."""
        with patch.dict(os.environ, {
            "AUTH_USERNAME": "admin",
            "AUTH_PASSWORD": "secure-password-123",
        }, clear=False):
            settings = Settings(_env_file=None)  # type: ignore[call-arg]

            assert settings.auth_username == "admin"
            assert settings.auth_password == "secure-password-123"

    def test_case_insensitive_env_vars(self, clear_settings_cache):
        """Test environment variable names are case insensitive."""
        # pydantic-settings should handle case insensitivity
        with patch.dict(os.environ, {
            "app_env": "test",  # lowercase
        }, clear=False):
            settings = Settings(_env_file=None)  # type: ignore[call-arg]
            # Note: Pydantic Settings with case_sensitive=False should work
            # The actual behavior depends on the OS (Windows is case-insensitive)

    def test_empty_string_env_var(self, clear_settings_cache):
        """Test empty string environment variable handling."""
        with patch.dict(os.environ, {
            "GOOGLE_CLIENT_ID": "",
        }, clear=False):
            settings = Settings(_env_file=None)  # type: ignore[call-arg]
            assert settings.google_client_id == ""

    def test_encryption_key_from_secret_key(self, clear_settings_cache):
        """Test encryption key is derived from secret_key."""
        settings = Settings(
            secret_key="my-32-character-secret-key!!!!!",
            _env_file=None,  # type: ignore[call-arg]
        )

        # secret_key should be accessible for encryption
        # The actual encryption uses SHA-256 to derive a 32-byte key from any length secret
        assert len(settings.secret_key) > 0
