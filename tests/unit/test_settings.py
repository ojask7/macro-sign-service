"""
Unit tests for configuration settings.
"""

import pytest
import os

from src.config.settings import (
    AppSettings,
    CertStoreBackend,
    CertificateSettings,
    Environment,
    Settings,
    SigningSettings,
    get_settings,
)


class TestAppSettings:
    """Tests for application settings."""

    def test_default_values(self):
        settings = AppSettings()
        assert settings.name == "macro-sign-service"
        # Note: APP_ENV is set to "testing" in conftest.py
        assert settings.env in (Environment.DEVELOPMENT, Environment.TESTING)
        assert settings.port == 8000

    def test_is_production(self):
        settings = AppSettings(env=Environment.PRODUCTION)
        assert settings.is_production is True

    def test_is_not_production(self):
        settings = AppSettings(env=Environment.DEVELOPMENT)
        assert settings.is_production is False

    def test_is_testing(self):
        settings = AppSettings(env=Environment.TESTING)
        assert settings.is_testing is True


class TestSigningSettings:
    """Tests for signing settings."""

    def test_allowed_extensions_list(self):
        settings = SigningSettings()
        extensions = settings.allowed_extensions_list
        assert ".vba" in extensions
        assert ".bas" in extensions
        assert ".cls" in extensions
        assert ".xlsm" in extensions
        assert ".pptm" in extensions
        assert ".docm" in extensions

    def test_max_file_size_bytes(self):
        settings = SigningSettings(max_file_size_mb=50)
        assert settings.max_file_size_bytes == 50 * 1024 * 1024


class TestCertificateSettings:
    """Tests for certificate settings."""

    def test_default_backend(self):
        settings = CertificateSettings()
        assert settings.store_backend == CertStoreBackend.LOCAL


class TestGetSettings:
    """Tests for the settings factory."""

    def test_returns_settings(self):
        settings = get_settings()
        assert isinstance(settings, Settings)
        assert settings.app is not None
        assert settings.database is not None
        assert settings.jwt is not None
