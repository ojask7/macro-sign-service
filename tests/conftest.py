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


# ---------------------------------------------------------------------------
# Shared fixtures for SNOW / signing tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def session_cert_dir(tmp_path_factory):
    """
    Session-scoped temp directory pre-populated with:
    - default.*          (general dev cert)
    - snow-test-domain.* (SNOW test-domain cert)
    """
    from src.core.signing_engine import create_self_signed_cert

    d = tmp_path_factory.mktemp("session_certs")
    cert_pem, key_pem = create_self_signed_cert(
        common_name="snow-test.macro-sign.local",
        organization="SNOW Test Domain",
        days_valid=365,
    )
    (d / "snow-test-domain.pem").write_bytes(cert_pem)
    (d / "snow-test-domain.key").write_bytes(key_pem)
    (d / "default.pem").write_bytes(cert_pem)
    (d / "default.key").write_bytes(key_pem)
    return d


@pytest.fixture(scope="session")
def session_cert_store(session_cert_dir):
    """Session-scoped LocalCertificateStore backed by the temp session cert directory."""
    from src.core.certificate_store import LocalCertificateStore

    return LocalCertificateStore(base_path=str(session_cert_dir))
