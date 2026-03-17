"""Unit tests for the certificate store."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.certs import CertStore, CertStoreError, create_code_signing_pfx, get_certificate_details


class TestCreateCodeSigningPfx:
    def test_generates_pfx_cert_key(self):
        pfx, cert_pem, key_pem = create_code_signing_pfx()
        assert len(pfx) > 0
        assert b"BEGIN CERTIFICATE" in cert_pem
        assert b"BEGIN PRIVATE KEY" in key_pem

    def test_cert_is_code_signing(self):
        _, cert_pem, _ = create_code_signing_pfx()
        details = get_certificate_details(cert_pem)
        assert details["is_code_signing"] is True

    def test_custom_common_name(self):
        _, cert_pem, _ = create_code_signing_pfx(common_name="My Cert")
        details = get_certificate_details(cert_pem)
        assert "My Cert" in details["subject"]

    def test_with_password(self):
        pfx, _, _ = create_code_signing_pfx(pfx_password=b"secret123")
        assert len(pfx) > 0

        # Should be loadable with password
        from cryptography.hazmat.primitives.serialization import pkcs12
        private_key, cert, _ = pkcs12.load_key_and_certificates(pfx, b"secret123")
        assert private_key is not None
        assert cert is not None


class TestGetCertificateDetails:
    def test_returns_expected_fields(self):
        _, cert_pem, _ = create_code_signing_pfx()
        details = get_certificate_details(cert_pem)

        assert "subject" in details
        assert "issuer" in details
        assert "serial_number" in details
        assert "not_valid_before" in details
        assert "not_valid_after" in details
        assert "fingerprint_sha256" in details
        assert "key_type" in details
        assert details["key_type"].startswith("RSA-")

    def test_fingerprint_format(self):
        _, cert_pem, _ = create_code_signing_pfx()
        details = get_certificate_details(cert_pem)
        # Colon-separated hex
        assert ":" in details["fingerprint_sha256"]
        parts = details["fingerprint_sha256"].split(":")
        assert len(parts) == 32  # SHA256 = 32 bytes


class TestCertStore:
    def test_init_auto_generates_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CertStore(certs_dir=Path(tmp))
            store.init()
            certs = store.list_certs()
            assert len(certs) >= 1
            names = [c["name"] for c in certs]
            assert "default" in names

    def test_generate_and_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CertStore(certs_dir=Path(tmp))
            store.init()
            store.generate("custom")
            certs = store.list_certs()
            names = [c["name"] for c in certs]
            assert "custom" in names

    def test_get_cert_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CertStore(certs_dir=Path(tmp))
            store.init()
            details = store.get_cert("default")
            assert details["is_code_signing"] is True
            assert details["name"] == "default"

    def test_get_cert_not_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CertStore(certs_dir=Path(tmp))
            store.init()
            with pytest.raises(CertStoreError, match="not found"):
                store.get_cert("nonexistent")

    def test_get_pfx(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CertStore(certs_dir=Path(tmp))
            store.init()
            pfx = store.get_pfx("default")
            assert isinstance(pfx, bytes)
            assert len(pfx) > 0

    def test_get_fingerprint(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CertStore(certs_dir=Path(tmp))
            store.init()
            fp = store.get_fingerprint("default")
            assert isinstance(fp, str)
            assert len(fp) == 64  # hex SHA256

    def test_persists_to_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            # First store generates
            store1 = CertStore(certs_dir=Path(tmp))
            store1.init()
            fp1 = store1.get_fingerprint("default")

            # Second store loads from disk
            store2 = CertStore(certs_dir=Path(tmp))
            store2.init()
            fp2 = store2.get_fingerprint("default")

            assert fp1 == fp2
