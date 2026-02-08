"""
Unit tests for certificate store implementations.
"""

import pytest
import tempfile
import os

from src.core.certificate_store import (
    CertificateInfo,
    CertificateStoreError,
    LocalCertificateStore,
)
from src.core.signing_engine import create_self_signed_cert


@pytest.fixture
def temp_cert_dir():
    """Create a temporary directory for certificate storage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def local_store(temp_cert_dir):
    """Create a local certificate store with temp directory."""
    return LocalCertificateStore(base_path=temp_cert_dir)


@pytest.fixture
def test_cert():
    """Generate a test certificate."""
    cert_pem, key_pem = create_self_signed_cert(
        common_name="Test Store Cert",
        days_valid=365,
    )
    return cert_pem, key_pem


class TestLocalCertificateStore:
    """Tests for the local filesystem certificate store."""

    @pytest.mark.asyncio
    async def test_store_and_retrieve(self, local_store, test_cert):
        cert_pem, key_pem = test_cert
        await local_store.store_certificate(
            "test-cert", cert_pem, key_pem, metadata={"env": "test"}
        )
        info = await local_store.get_certificate("test-cert")
        assert info.name == "test-cert"
        assert info.certificate_pem == cert_pem
        assert info.private_key_pem == key_pem
        assert info.metadata.get("env") == "test"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, local_store):
        with pytest.raises(CertificateStoreError, match="not found"):
            await local_store.get_certificate("nonexistent")

    @pytest.mark.asyncio
    async def test_list_certificates(self, local_store, test_cert):
        cert_pem, key_pem = test_cert
        await local_store.store_certificate("cert-a", cert_pem, key_pem)
        await local_store.store_certificate("cert-b", cert_pem, key_pem)

        certs = await local_store.list_certificates()
        assert "cert-a" in certs
        assert "cert-b" in certs

    @pytest.mark.asyncio
    async def test_delete_certificate(self, local_store, test_cert):
        cert_pem, key_pem = test_cert
        await local_store.store_certificate("to-delete", cert_pem, key_pem)
        await local_store.delete_certificate("to-delete")

        with pytest.raises(CertificateStoreError, match="not found"):
            await local_store.get_certificate("to-delete")

    @pytest.mark.asyncio
    async def test_rotate_certificate(self, local_store, test_cert):
        cert_pem, key_pem = test_cert
        await local_store.store_certificate("rotate-test", cert_pem, key_pem)

        new_cert_pem, new_key_pem = create_self_signed_cert(
            common_name="Rotated Cert"
        )
        await local_store.rotate_certificate(
            "rotate-test", new_cert_pem, new_key_pem
        )

        info = await local_store.get_certificate("rotate-test")
        assert info.certificate_pem == new_cert_pem

    @pytest.mark.asyncio
    async def test_store_without_key(self, local_store, test_cert):
        cert_pem, _ = test_cert
        await local_store.store_certificate("cert-only", cert_pem)

        info = await local_store.get_certificate("cert-only")
        assert info.certificate_pem == cert_pem
        assert info.private_key_pem is None


class TestCertificateInfo:
    """Tests for the CertificateInfo dataclass."""

    def test_creation(self):
        info = CertificateInfo(
            name="test",
            certificate_pem=b"cert data",
            private_key_pem=b"key data",
            metadata={"key": "value"},
        )
        assert info.name == "test"
        assert info.certificate_pem == b"cert data"
        assert info.private_key_pem == b"key data"
        assert info.metadata["key"] == "value"

    def test_default_metadata(self):
        info = CertificateInfo(name="test", certificate_pem=b"cert")
        assert info.metadata == {}
        assert info.private_key_pem is None
