"""
Core signing engine for macro files.
Handles digital signature creation and verification using X.509 certificates.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa, utils
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    load_pem_private_key,
)
from cryptography.x509.oid import NameOID

from src.config.logging import get_logger
from src.config.settings import get_settings

logger = get_logger(__name__)


class SigningError(Exception):
    """Raised when a signing operation fails."""

    pass


class VerificationError(Exception):
    """Raised when a signature verification fails."""

    pass


class SigningResult:
    """Result of a signing operation."""

    def __init__(
        self,
        signature: bytes,
        algorithm: str,
        certificate_fingerprint: str,
        signed_at: datetime,
        file_hash: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        self.signature = signature
        self.algorithm = algorithm
        self.certificate_fingerprint = certificate_fingerprint
        self.signed_at = signed_at
        self.file_hash = file_hash
        self.metadata = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "signature": self.signature.hex(),
            "algorithm": self.algorithm,
            "certificate_fingerprint": self.certificate_fingerprint,
            "signed_at": self.signed_at.isoformat(),
            "file_hash": self.file_hash,
            "metadata": self.metadata,
        }


class VerificationResult:
    """Result of a signature verification."""

    def __init__(
        self,
        is_valid: bool,
        certificate_subject: Optional[str] = None,
        certificate_issuer: Optional[str] = None,
        certificate_expiry: Optional[datetime] = None,
        message: str = "",
    ) -> None:
        self.is_valid = is_valid
        self.certificate_subject = certificate_subject
        self.certificate_issuer = certificate_issuer
        self.certificate_expiry = certificate_expiry
        self.message = message

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "certificate_subject": self.certificate_subject,
            "certificate_issuer": self.certificate_issuer,
            "certificate_expiry": (
                self.certificate_expiry.isoformat()
                if self.certificate_expiry
                else None
            ),
            "message": self.message,
        }


class SigningEngine:
    """
    Core engine for signing and verifying macro files.
    Supports RSA and ECDSA signing with configurable hash algorithms.
    """

    SUPPORTED_ALGORITHMS = {
        "sha256": hashes.SHA256(),
        "sha384": hashes.SHA384(),
        "sha512": hashes.SHA512(),
    }

    def __init__(
        self,
        private_key_pem: Optional[bytes] = None,
        certificate_pem: Optional[bytes] = None,
        key_password: Optional[bytes] = None,
    ) -> None:
        self._private_key = None
        self._certificate = None

        if private_key_pem:
            self.load_private_key(private_key_pem, key_password)
        if certificate_pem:
            self.load_certificate(certificate_pem)

    def load_private_key(
        self, key_pem: bytes, password: Optional[bytes] = None
    ) -> None:
        """Load a PEM-encoded private key."""
        try:
            self._private_key = load_pem_private_key(key_pem, password=password)
            logger.info("Private key loaded successfully")
        except Exception as e:
            logger.error("Failed to load private key", error=str(e))
            raise SigningError(f"Failed to load private key: {e}") from e

    def load_certificate(self, cert_pem: bytes) -> None:
        """Load a PEM-encoded X.509 certificate."""
        try:
            self._certificate = x509.load_pem_x509_certificate(cert_pem)
            logger.info(
                "Certificate loaded",
                subject=self._certificate.subject.rfc4514_string(),
                expires=self._certificate.not_valid_after_utc.isoformat(),
            )
        except Exception as e:
            logger.error("Failed to load certificate", error=str(e))
            raise SigningError(f"Failed to load certificate: {e}") from e

    @property
    def certificate_fingerprint(self) -> str:
        """Get SHA-256 fingerprint of the loaded certificate."""
        if not self._certificate:
            raise SigningError("No certificate loaded")
        return self._certificate.fingerprint(hashes.SHA256()).hex()

    @property
    def certificate_subject(self) -> Optional[str]:
        """Get the certificate subject."""
        if self._certificate:
            return self._certificate.subject.rfc4514_string()
        return None

    @property
    def certificate_expiry(self) -> Optional[datetime]:
        """Get the certificate expiry date."""
        if self._certificate:
            return self._certificate.not_valid_after_utc
        return None

    def _get_hash_algorithm(self, algorithm: str) -> hashes.HashAlgorithm:
        """Get hash algorithm instance by name."""
        algo = self.SUPPORTED_ALGORITHMS.get(algorithm.lower())
        if not algo:
            raise SigningError(
                f"Unsupported algorithm: {algorithm}. "
                f"Supported: {list(self.SUPPORTED_ALGORITHMS.keys())}"
            )
        return algo

    def compute_file_hash(
        self, file_content: bytes, algorithm: str = "sha256"
    ) -> str:
        """Compute hash of file content."""
        hash_algo = self._get_hash_algorithm(algorithm)
        digest = hashes.Hash(hash_algo)
        digest.update(file_content)
        return digest.finalize().hex()

    def sign(
        self,
        file_content: bytes,
        algorithm: str = "sha256",
        metadata: Optional[dict[str, Any]] = None,
    ) -> SigningResult:
        """
        Sign a macro file's content.

        Args:
            file_content: Raw bytes of the macro file
            algorithm: Hash algorithm to use (sha256, sha384, sha512)
            metadata: Optional metadata to include in the signing result

        Returns:
            SigningResult with the digital signature and metadata
        """
        if not self._private_key:
            raise SigningError("No private key loaded. Cannot sign.")
        if not self._certificate:
            raise SigningError("No certificate loaded. Cannot sign.")

        # Check certificate validity
        now = datetime.now(timezone.utc)
        if now > self._certificate.not_valid_after_utc:
            raise SigningError("Certificate has expired")
        if now < self._certificate.not_valid_before_utc:
            raise SigningError("Certificate is not yet valid")

        hash_algo = self._get_hash_algorithm(algorithm)
        file_hash = self.compute_file_hash(file_content, algorithm)

        try:
            if isinstance(self._private_key, rsa.RSAPrivateKey):
                signature = self._private_key.sign(
                    file_content,
                    padding.PKCS1v15(),
                    hash_algo,
                )
            elif isinstance(self._private_key, ec.EllipticCurvePrivateKey):
                signature = self._private_key.sign(
                    file_content,
                    ec.ECDSA(hash_algo),
                )
            else:
                raise SigningError(
                    f"Unsupported key type: {type(self._private_key)}"
                )

            result = SigningResult(
                signature=signature,
                algorithm=algorithm,
                certificate_fingerprint=self.certificate_fingerprint,
                signed_at=now,
                file_hash=file_hash,
                metadata=metadata,
            )

            logger.info(
                "File signed successfully",
                algorithm=algorithm,
                file_hash=file_hash,
                cert_fingerprint=self.certificate_fingerprint[:16] + "...",
            )

            return result

        except SigningError:
            raise
        except Exception as e:
            logger.error("Signing operation failed", error=str(e))
            raise SigningError(f"Signing operation failed: {e}") from e

    def verify(
        self,
        file_content: bytes,
        signature: bytes,
        algorithm: str = "sha256",
        certificate_pem: Optional[bytes] = None,
    ) -> VerificationResult:
        """
        Verify a digital signature on a macro file.

        Args:
            file_content: Raw bytes of the macro file
            signature: The digital signature to verify
            algorithm: Hash algorithm used for signing
            certificate_pem: Optional certificate PEM to use for verification
                             (uses loaded certificate if not provided)

        Returns:
            VerificationResult indicating if the signature is valid
        """
        cert = self._certificate
        if certificate_pem:
            try:
                cert = x509.load_pem_x509_certificate(certificate_pem)
            except Exception as e:
                return VerificationResult(
                    is_valid=False,
                    message=f"Invalid certificate: {e}",
                )

        if not cert:
            return VerificationResult(
                is_valid=False,
                message="No certificate available for verification",
            )

        # Check certificate validity
        now = datetime.now(timezone.utc)
        cert_subject = cert.subject.rfc4514_string()
        cert_issuer = cert.issuer.rfc4514_string()
        cert_expiry = cert.not_valid_after_utc

        if now > cert_expiry:
            return VerificationResult(
                is_valid=False,
                certificate_subject=cert_subject,
                certificate_issuer=cert_issuer,
                certificate_expiry=cert_expiry,
                message="Certificate has expired",
            )

        hash_algo = self._get_hash_algorithm(algorithm)
        public_key = cert.public_key()

        try:
            if isinstance(public_key, rsa.RSAPublicKey):
                public_key.verify(
                    signature,
                    file_content,
                    padding.PKCS1v15(),
                    hash_algo,
                )
            elif isinstance(public_key, ec.EllipticCurvePublicKey):
                public_key.verify(
                    signature,
                    file_content,
                    ec.ECDSA(hash_algo),
                )
            else:
                return VerificationResult(
                    is_valid=False,
                    message=f"Unsupported key type: {type(public_key)}",
                )

            logger.info(
                "Signature verification successful",
                cert_subject=cert_subject,
            )

            return VerificationResult(
                is_valid=True,
                certificate_subject=cert_subject,
                certificate_issuer=cert_issuer,
                certificate_expiry=cert_expiry,
                message="Signature is valid",
            )

        except Exception as e:
            logger.warning(
                "Signature verification failed",
                error=str(e),
                cert_subject=cert_subject,
            )
            return VerificationResult(
                is_valid=False,
                certificate_subject=cert_subject,
                certificate_issuer=cert_issuer,
                certificate_expiry=cert_expiry,
                message=f"Signature verification failed: {e}",
            )


def create_self_signed_cert(
    common_name: str = "Macro Sign Service Dev",
    organization: str = "Development",
    days_valid: int = 365,
    key_size: int = 2048,
) -> tuple[bytes, bytes]:
    """
    Generate a self-signed certificate and private key for development.

    Returns:
        Tuple of (certificate_pem, private_key_pem)
    """
    from cryptography.x509.oid import ExtendedKeyUsageOID

    # Generate RSA key pair
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_size,
    )

    # Build certificate
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization),
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
    ])

    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + __import__("datetime").timedelta(days=days_valid))
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_encipherment=False,
                content_commitment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CODE_SIGNING]),
            critical=False,
        )
        .sign(private_key, hashes.SHA256())
    )

    cert_pem = cert.public_bytes(Encoding.PEM)
    key_pem = private_key.private_bytes(
        Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )

    logger.info(
        "Self-signed certificate generated",
        subject=common_name,
        days_valid=days_valid,
    )

    return cert_pem, key_pem
