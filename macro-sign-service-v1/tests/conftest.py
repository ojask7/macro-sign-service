"""Shared test fixtures."""

from __future__ import annotations

import os
import struct
import tempfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

# Point config to temp dirs before importing app modules
_tmp = tempfile.mkdtemp(prefix="macrosign_test_")
os.environ["MACRO_SIGN_CERTS_DIR"] = str(Path(_tmp) / "certs")
os.environ["MACRO_SIGN_DB_PATH"] = str(Path(_tmp) / "test_audit.db")
os.environ["MACRO_SIGN_API_KEY"] = ""  # disable auth for tests

from app.certs import CertStore, create_code_signing_pfx
from app.config import Settings, get_settings


@pytest.fixture(scope="session")
def test_certs_dir() -> Path:
    d = Path(_tmp) / "certs"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture(scope="session")
def test_pfx() -> tuple[bytes, bytes, bytes]:
    """Generate a test code-signing PFX certificate (session-scoped)."""
    return create_code_signing_pfx(
        common_name="Test Macro Sign",
        days_valid=30,
    )


@pytest.fixture(scope="session")
def cert_store(test_certs_dir, test_pfx) -> CertStore:
    """Initialized cert store with a default cert."""
    pfx_bytes, _, _ = test_pfx
    store = CertStore(certs_dir=test_certs_dir)
    store.init()  # Will auto-generate default if needed
    return store


@pytest.fixture
async def client(cert_store):
    """Async test client for the FastAPI app."""
    from app.main import app
    from app.routes import set_cert_store

    set_cert_store(cert_store)

    # Init audit DB for tests
    from app.audit import close_db, init_db
    await init_db()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    await close_db()


# ---------------------------------------------------------------------------
# Minimal Office file helpers
# ---------------------------------------------------------------------------

# A minimal OLE Compound File (CFB) header — this is enough to be a valid
# .xlsm/.docm file for signtool to recognize (it may fail to sign it since
# there's no VBA project, but it's structurally valid for upload/validation).

_CFB_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def make_minimal_cfb(size: int = 4096) -> bytes:
    """Create a minimal CFB/OLE header (not a real Office file, but structurally valid)."""
    header = bytearray(512)
    header[0:8] = _CFB_MAGIC
    # Minor version
    struct.pack_into("<H", header, 0x18, 0x003E)
    # Major version (v3)
    struct.pack_into("<H", header, 0x1A, 0x0003)
    # Byte order (little-endian)
    struct.pack_into("<H", header, 0x1C, 0xFFFE)
    # Sector size power (9 = 512 bytes)
    struct.pack_into("<H", header, 0x1E, 0x0009)
    # Mini sector size power (6 = 64 bytes)
    struct.pack_into("<H", header, 0x20, 0x0006)
    # Pad to requested size
    return bytes(header) + b"\x00" * max(0, size - 512)


@pytest.fixture
def minimal_xlsm() -> bytes:
    """Minimal .xlsm-like bytes for upload tests."""
    return make_minimal_cfb()


@pytest.fixture
def minimal_docm() -> bytes:
    """Minimal .docm-like bytes for upload tests."""
    return make_minimal_cfb()


@pytest.fixture
def sample_vba_content() -> bytes:
    """Sample VBA text macro content."""
    return b"""Attribute VB_Name = "Module1"
Sub HelloWorld()
    MsgBox "Hello, World!"
End Sub
"""
