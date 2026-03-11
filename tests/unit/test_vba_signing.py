"""
Unit tests for the VBA signing engine.

These tests validate:
  - PFX certificate generation with Code Signing EKU
  - PEM-to-PFX conversion
  - VBASigningEngine initialization and certificate properties
  - Fallback behaviour on Linux (unsigned-requires-windows)
  - Windows agent delegation (mocked HTTP)
  - Certificate details extraction
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.core.vba_signing import (
    VBASigningEngine,
    VBASigningError,
    VBASigningResult,
    create_code_signing_pfx,
    get_certificate_details,
    pem_to_pfx,
    _is_code_signing_cert,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def code_signing_cert():
    """Generate a code-signing PFX + PEM cert + key for tests."""
    pfx, cert_pem, key_pem = create_code_signing_pfx(
        common_name="Test Signer",
        organization="Test Org",
        days_valid=30,
        key_size=2048,
    )
    return pfx, cert_pem, key_pem


@pytest.fixture
def sample_xlsm_content():
    """Minimal bytes to act as a fake .xlsm file (just for flow testing)."""
    return b"PK\x03\x04" + b"\x00" * 100  # ZIP header + padding


# ---------------------------------------------------------------------------
# PFX generation
# ---------------------------------------------------------------------------


class TestCreateCodeSigningPfx:
    def test_returns_three_byte_objects(self):
        pfx, cert, key = create_code_signing_pfx()
        assert isinstance(pfx, bytes) and len(pfx) > 0
        assert isinstance(cert, bytes) and b"BEGIN CERTIFICATE" in cert
        assert isinstance(key, bytes) and b"BEGIN PRIVATE KEY" in key

    def test_certificate_has_code_signing_eku(self):
        _, cert_pem, _ = create_code_signing_pfx()
        from cryptography import x509
        cert = x509.load_pem_x509_certificate(cert_pem)
        assert _is_code_signing_cert(cert)

    def test_custom_common_name(self):
        _, cert_pem, _ = create_code_signing_pfx(common_name="My Custom CN")
        details = get_certificate_details(cert_pem)
        assert "My Custom CN" in details["subject"]

    def test_pfx_with_password(self):
        pfx, _, _ = create_code_signing_pfx(pfx_password=b"secret123")
        assert isinstance(pfx, bytes) and len(pfx) > 0

    def test_key_size_respected(self):
        _, cert_pem, _ = create_code_signing_pfx(key_size=4096)
        details = get_certificate_details(cert_pem)
        assert details["key_type"] == "RSA-4096"


# ---------------------------------------------------------------------------
# PEM to PFX conversion
# ---------------------------------------------------------------------------


class TestPemToPfx:
    def test_converts_successfully(self, code_signing_cert):
        _, cert_pem, key_pem = code_signing_cert
        pfx = pem_to_pfx(cert_pem, key_pem)
        assert isinstance(pfx, bytes) and len(pfx) > 0

    def test_with_password(self, code_signing_cert):
        _, cert_pem, key_pem = code_signing_cert
        pfx = pem_to_pfx(cert_pem, key_pem, pfx_password=b"pass")
        assert isinstance(pfx, bytes) and len(pfx) > 0


# ---------------------------------------------------------------------------
# VBASigningEngine initialisation
# ---------------------------------------------------------------------------


class TestVBASigningEngineInit:
    def test_init_from_pem(self, code_signing_cert):
        _, cert_pem, key_pem = code_signing_cert
        engine = VBASigningEngine(certificate_pem=cert_pem, private_key_pem=key_pem)
        assert engine._pfx_bytes is not None
        assert engine.certificate_subject
        assert engine.certificate_fingerprint

    def test_init_from_pfx(self, code_signing_cert):
        pfx, cert_pem, _ = code_signing_cert
        engine = VBASigningEngine(pfx_bytes=pfx, certificate_pem=cert_pem)
        assert engine._pfx_bytes == pfx

    def test_no_cert_raises_on_subject(self):
        engine = VBASigningEngine()
        with pytest.raises(VBASigningError):
            _ = engine.certificate_subject

    def test_no_cert_raises_on_fingerprint(self):
        engine = VBASigningEngine()
        with pytest.raises(VBASigningError):
            _ = engine.certificate_fingerprint


# ---------------------------------------------------------------------------
# sign_file — fallback on Linux (no agent URL)
# ---------------------------------------------------------------------------


class TestSignFileFallback:
    @patch("src.core.vba_signing.is_windows", return_value=False)
    def test_returns_unsigned_on_linux_without_agent(self, _mock, code_signing_cert, sample_xlsm_content):
        _, cert_pem, key_pem = code_signing_cert
        engine = VBASigningEngine(
            certificate_pem=cert_pem,
            private_key_pem=key_pem,
            windows_agent_url="",
        )
        result = engine.sign_file(sample_xlsm_content, "test.xlsm")

        assert result.signing_method == "unsigned-requires-windows"
        assert result.signed_file_bytes == sample_xlsm_content
        assert result.certificate_subject
        assert result.certificate_fingerprint

    def test_no_pfx_raises(self):
        engine = VBASigningEngine()
        with pytest.raises(VBASigningError, match="No PFX"):
            engine.sign_file(b"data", "test.xlsm")


# ---------------------------------------------------------------------------
# sign_file — Windows agent delegation (mocked)
# ---------------------------------------------------------------------------


class TestSignViaAgent:
    @patch("src.core.vba_signing.is_windows", return_value=False)
    def test_delegates_to_agent_on_linux(self, _mock, code_signing_cert, sample_xlsm_content):
        _, cert_pem, key_pem = code_signing_cert
        signed_content = b"SIGNED_" + sample_xlsm_content

        # Mock httpx calls
        mock_health_response = MagicMock()
        mock_health_response.json.return_value = {"signing_ready": True}

        mock_sign_response = MagicMock()
        mock_sign_response.status_code = 200
        mock_sign_response.json.return_value = {
            "signed_file_b64": base64.b64encode(signed_content).decode(),
            "signed": True,
            "metadata": {"hash_algorithm": "SHA256"},
        }

        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_health_response
        mock_client_instance.post.return_value = mock_sign_response
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)

        with patch("src.core.vba_signing.httpx.Client", return_value=mock_client_instance):
            engine = VBASigningEngine(
                certificate_pem=cert_pem,
                private_key_pem=key_pem,
                windows_agent_url="http://windows-vm:9001",
            )
            result = engine.sign_file(sample_xlsm_content, "report.xlsm")

        assert result.signing_method == "windows-agent-signtool-sip"
        assert result.signed_file_bytes == signed_content
        assert result.original_filename == "report.xlsm"

    @patch("src.core.vba_signing.is_windows", return_value=False)
    def test_falls_back_when_agent_unhealthy(self, _mock, code_signing_cert, sample_xlsm_content):
        _, cert_pem, key_pem = code_signing_cert

        mock_health_response = MagicMock()
        mock_health_response.json.return_value = {"signing_ready": False}

        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_health_response
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)

        with patch("src.core.vba_signing.httpx.Client", return_value=mock_client_instance):
            engine = VBASigningEngine(
                certificate_pem=cert_pem,
                private_key_pem=key_pem,
                windows_agent_url="http://windows-vm:9001",
            )
            result = engine.sign_file(sample_xlsm_content, "report.xlsm")

        assert result.signing_method == "unsigned-requires-windows"

    @patch("src.core.vba_signing.is_windows", return_value=False)
    def test_falls_back_when_agent_unreachable(self, _mock, code_signing_cert, sample_xlsm_content):
        _, cert_pem, key_pem = code_signing_cert

        import httpx
        mock_client_instance = MagicMock()
        mock_client_instance.get.side_effect = httpx.ConnectError("Connection refused")
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)

        with patch("src.core.vba_signing.httpx.Client", return_value=mock_client_instance):
            engine = VBASigningEngine(
                certificate_pem=cert_pem,
                private_key_pem=key_pem,
                windows_agent_url="http://windows-vm:9001",
            )
            result = engine.sign_file(sample_xlsm_content, "report.xlsm")

        assert result.signing_method == "unsigned-requires-windows"


# ---------------------------------------------------------------------------
# Certificate details
# ---------------------------------------------------------------------------


class TestGetCertificateDetails:
    def test_returns_all_fields(self, code_signing_cert):
        _, cert_pem, _ = code_signing_cert
        details = get_certificate_details(cert_pem)

        assert "subject" in details
        assert "issuer" in details
        assert "serial_number" in details
        assert "not_valid_before" in details
        assert "not_valid_after" in details
        assert "fingerprint_sha256" in details
        assert "key_type" in details
        assert "extensions" in details
        assert "is_code_signing" in details
        assert "certificate_pem" in details

    def test_code_signing_flag(self, code_signing_cert):
        _, cert_pem, _ = code_signing_cert
        details = get_certificate_details(cert_pem)
        assert details["is_code_signing"] is True

    def test_fingerprint_format(self, code_signing_cert):
        _, cert_pem, _ = code_signing_cert
        details = get_certificate_details(cert_pem)
        # Should be colon-separated hex pairs
        parts = details["fingerprint_sha256"].split(":")
        assert len(parts) == 32  # SHA-256 = 32 bytes
        for part in parts:
            assert len(part) == 2
            int(part, 16)  # Should be valid hex

    def test_extensions_include_eku(self, code_signing_cert):
        _, cert_pem, _ = code_signing_cert
        details = get_certificate_details(cert_pem)
        assert "extended_key_usage" in details["extensions"]
        # Code Signing OID
        assert "1.3.6.1.5.5.7.3.3" in details["extensions"]["extended_key_usage"]


# ---------------------------------------------------------------------------
# VBASigningResult
# ---------------------------------------------------------------------------


class TestVBASigningResult:
    def test_to_dict(self):
        result = VBASigningResult(
            signed_file_bytes=b"data",
            original_filename="test.xlsm",
            certificate_subject="CN=Test",
            certificate_fingerprint="aabbcc",
            certificate_pem="PEM",
            algorithm="sha256",
            signed_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            signing_method="signtool-office-sip",
        )
        d = result.to_dict()
        assert d["original_filename"] == "test.xlsm"
        assert d["signing_method"] == "signtool-office-sip"
        assert d["signed_file_size"] == 4
        assert d["algorithm"] == "sha256"
