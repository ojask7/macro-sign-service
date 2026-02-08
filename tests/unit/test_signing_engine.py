"""
Unit tests for the core signing engine.
"""

import pytest
from datetime import datetime, timezone

from src.core.signing_engine import (
    SigningEngine,
    SigningError,
    SigningResult,
    VerificationResult,
    create_self_signed_cert,
)


@pytest.fixture
def cert_pair():
    """Generate a test certificate pair."""
    cert_pem, key_pem = create_self_signed_cert(
        common_name="Test Cert",
        organization="Test Org",
        days_valid=365,
    )
    return cert_pem, key_pem


@pytest.fixture
def signing_engine(cert_pair):
    """Create a signing engine with test certificates."""
    cert_pem, key_pem = cert_pair
    return SigningEngine(private_key_pem=key_pem, certificate_pem=cert_pem)


@pytest.fixture
def sample_macro():
    """Sample VBA macro content."""
    return b"""
    Sub AutoOpen()
        MsgBox "Hello from Macro Sign Service Test"
    End Sub
    """


class TestCreateSelfSignedCert:
    """Tests for certificate generation."""

    def test_generates_valid_cert_and_key(self):
        cert_pem, key_pem = create_self_signed_cert()
        assert cert_pem.startswith(b"-----BEGIN CERTIFICATE-----")
        assert key_pem.startswith(b"-----BEGIN PRIVATE KEY-----")

    def test_custom_common_name(self):
        cert_pem, key_pem = create_self_signed_cert(
            common_name="My Custom Cert"
        )
        engine = SigningEngine(certificate_pem=cert_pem)
        assert "My Custom Cert" in engine.certificate_subject

    def test_custom_key_size(self):
        cert_pem, key_pem = create_self_signed_cert(key_size=4096)
        assert cert_pem is not None
        assert key_pem is not None


class TestSigningEngine:
    """Tests for the signing engine."""

    def test_load_certificate(self, cert_pair):
        cert_pem, _ = cert_pair
        engine = SigningEngine()
        engine.load_certificate(cert_pem)
        assert engine.certificate_subject is not None
        assert engine.certificate_fingerprint is not None

    def test_load_private_key(self, cert_pair):
        _, key_pem = cert_pair
        engine = SigningEngine()
        engine.load_private_key(key_pem)

    def test_load_invalid_certificate(self):
        engine = SigningEngine()
        with pytest.raises(SigningError, match="Failed to load certificate"):
            engine.load_certificate(b"invalid cert data")

    def test_load_invalid_private_key(self):
        engine = SigningEngine()
        with pytest.raises(SigningError, match="Failed to load private key"):
            engine.load_private_key(b"invalid key data")

    def test_certificate_fingerprint(self, signing_engine):
        fingerprint = signing_engine.certificate_fingerprint
        assert isinstance(fingerprint, str)
        assert len(fingerprint) == 64  # SHA-256 hex digest

    def test_certificate_subject(self, signing_engine):
        subject = signing_engine.certificate_subject
        assert "Test Cert" in subject

    def test_certificate_expiry(self, signing_engine):
        expiry = signing_engine.certificate_expiry
        assert expiry > datetime.now(timezone.utc)

    def test_fingerprint_without_cert_raises(self):
        engine = SigningEngine()
        with pytest.raises(SigningError, match="No certificate loaded"):
            _ = engine.certificate_fingerprint


class TestSigning:
    """Tests for signing operations."""

    def test_sign_macro(self, signing_engine, sample_macro):
        result = signing_engine.sign(sample_macro)
        assert isinstance(result, SigningResult)
        assert result.signature is not None
        assert len(result.signature) > 0
        assert result.algorithm == "sha256"
        assert result.file_hash is not None
        assert result.certificate_fingerprint is not None
        assert result.signed_at is not None

    def test_sign_with_different_algorithms(self, signing_engine, sample_macro):
        for algo in ["sha256", "sha384", "sha512"]:
            result = signing_engine.sign(sample_macro, algorithm=algo)
            assert result.algorithm == algo

    def test_sign_with_invalid_algorithm(self, signing_engine, sample_macro):
        with pytest.raises(SigningError, match="Unsupported algorithm"):
            signing_engine.sign(sample_macro, algorithm="md5")

    def test_sign_without_key_raises(self, cert_pair):
        cert_pem, _ = cert_pair
        engine = SigningEngine(certificate_pem=cert_pem)
        with pytest.raises(SigningError, match="No private key loaded"):
            engine.sign(b"test content")

    def test_sign_without_cert_raises(self, cert_pair):
        _, key_pem = cert_pair
        engine = SigningEngine(private_key_pem=key_pem)
        with pytest.raises(SigningError, match="No certificate loaded"):
            engine.sign(b"test content")

    def test_sign_result_to_dict(self, signing_engine, sample_macro):
        result = signing_engine.sign(sample_macro)
        d = result.to_dict()
        assert "signature" in d
        assert "algorithm" in d
        assert "certificate_fingerprint" in d
        assert "signed_at" in d
        assert "file_hash" in d

    def test_sign_with_metadata(self, signing_engine, sample_macro):
        metadata = {"team": "engineering", "pipeline": "ci-main"}
        result = signing_engine.sign(sample_macro, metadata=metadata)
        assert result.metadata == metadata

    def test_compute_file_hash(self, signing_engine, sample_macro):
        hash1 = signing_engine.compute_file_hash(sample_macro)
        hash2 = signing_engine.compute_file_hash(sample_macro)
        assert hash1 == hash2  # Deterministic

        # Different content = different hash
        hash3 = signing_engine.compute_file_hash(b"different content")
        assert hash1 != hash3


class TestVerification:
    """Tests for signature verification."""

    def test_verify_valid_signature(self, signing_engine, sample_macro):
        sign_result = signing_engine.sign(sample_macro)
        verify_result = signing_engine.verify(
            sample_macro, sign_result.signature
        )
        assert verify_result.is_valid is True
        assert "valid" in verify_result.message.lower()

    def test_verify_tampered_content(self, signing_engine, sample_macro):
        sign_result = signing_engine.sign(sample_macro)
        tampered = sample_macro + b" tampered"
        verify_result = signing_engine.verify(tampered, sign_result.signature)
        assert verify_result.is_valid is False

    def test_verify_invalid_signature(self, signing_engine, sample_macro):
        verify_result = signing_engine.verify(
            sample_macro, b"invalid_signature"
        )
        assert verify_result.is_valid is False

    def test_verify_with_external_certificate(self, sample_macro):
        cert_pem, key_pem = create_self_signed_cert(common_name="Signer")
        signer = SigningEngine(private_key_pem=key_pem, certificate_pem=cert_pem)
        sign_result = signer.sign(sample_macro)

        # Verify with a fresh engine using the same cert
        verifier = SigningEngine()
        verify_result = verifier.verify(
            sample_macro,
            sign_result.signature,
            certificate_pem=cert_pem,
        )
        assert verify_result.is_valid is True
        assert "Signer" in verify_result.certificate_subject

    def test_verify_without_certificate(self, sample_macro):
        engine = SigningEngine()
        result = engine.verify(sample_macro, b"some_signature")
        assert result.is_valid is False
        assert "No certificate" in result.message

    def test_verify_result_to_dict(self, signing_engine, sample_macro):
        sign_result = signing_engine.sign(sample_macro)
        verify_result = signing_engine.verify(
            sample_macro, sign_result.signature
        )
        d = verify_result.to_dict()
        assert "is_valid" in d
        assert "certificate_subject" in d
        assert "message" in d

    def test_verify_different_algorithm(self, signing_engine, sample_macro):
        """Sign with sha256, try to verify with sha512 - should fail."""
        sign_result = signing_engine.sign(sample_macro, algorithm="sha256")
        verify_result = signing_engine.verify(
            sample_macro, sign_result.signature, algorithm="sha512"
        )
        assert verify_result.is_valid is False

    def test_cross_certificate_verification_fails(self, sample_macro):
        """Signing with one cert and verifying with another should fail."""
        cert1, key1 = create_self_signed_cert(common_name="Cert 1")
        cert2, key2 = create_self_signed_cert(common_name="Cert 2")

        signer = SigningEngine(private_key_pem=key1, certificate_pem=cert1)
        sign_result = signer.sign(sample_macro)

        verifier = SigningEngine(certificate_pem=cert2)
        verify_result = verifier.verify(sample_macro, sign_result.signature)
        assert verify_result.is_valid is False
