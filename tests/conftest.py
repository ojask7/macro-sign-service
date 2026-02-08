"""
Shared test fixtures and configuration.
"""

import os
import pytest

# Set testing environment before any imports
os.environ["APP_ENV"] = "testing"
os.environ["APP_DEBUG"] = "true"
os.environ["APP_SECRET_KEY"] = "test-secret-key"
os.environ["JWT_SECRET_KEY"] = "test-jwt-secret"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///test.db"
os.environ["CERT_STORE_BACKEND"] = "local"


@pytest.fixture(autouse=True)
def reset_settings_cache():
    """Clear the settings cache between tests."""
    from src.config.settings import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
