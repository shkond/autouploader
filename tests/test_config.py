"""Tests for configuration."""

import os
from unittest.mock import patch

from app.config import Settings, get_settings


def test_default_settings() -> None:
    """Test default settings values."""
    # Create settings without env file
    with patch.dict(os.environ, {}, clear=True):
        settings = Settings(
            _env_file=None,  # type: ignore[call-arg]
        )
        assert settings.app_name == "AutoUploader"
        assert settings.app_env == "development"
        assert settings.debug is False
        assert settings.port == 8000


def test_scopes_list() -> None:
    """Test that scopes are parsed correctly."""
    settings = Settings(
        google_scopes="scope1 scope2 scope3",
        _env_file=None,  # type: ignore[call-arg]
    )
    assert settings.scopes_list == ["scope1", "scope2", "scope3"]


def test_is_production() -> None:
    """Test production environment detection."""
    dev_settings = Settings(
        app_env="development",
        _env_file=None,  # type: ignore[call-arg]
    )
    assert dev_settings.is_production is False

    prod_settings = Settings(
        app_env="production",
        _env_file=None,  # type: ignore[call-arg]
    )
    assert prod_settings.is_production is True


def test_get_settings_cached() -> None:
    """Test that settings are cached."""
    # Clear cache first
    get_settings.cache_clear()

    settings1 = get_settings()
    settings2 = get_settings()
    assert settings1 is settings2
