"""PFX certificate store — directory-based, with auto-generation."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.serialization import Encoding, pkcs12
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from app.config import get_settings

log = logging.getLogger(__name__)


class CertStoreError(Exception):
    """Raised when certificate store operations fail."""


def create_code_signing_pfx(
    common_name: str = "Macro Sign Service",
    organization: str = "Macro Sign Service",
    country: str = "US",
    days_valid: int = 365,
    key_size: int = 2048,
    pfx_password: bytes = b"",
) -> tuple[bytes, bytes, bytes]:
    """
    Generate a self-signed code-signing certificate.

    Returns:
        (pfx_bytes, certificate_pem, private_key_pem)
    """
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_size,
    )

    now = datetime.now(timezone.utc)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization),
        x509.NameAttribute(NameOID.COUNTRY_NAME, country),
    ])

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=days_valid))
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

    encryption: serialization.KeySerializationEncryption = (
        serialization.BestAvailableEncryption(pfx_password)
        if pfx_password
        else serialization.NoEncryption()
    )
    pfx_bytes = pkcs12.serialize_key_and_certificates(
        name=common_name.encode(),
        key=private_key,
        cert=cert,
        cas=None,
        encryption_algorithm=encryption,
    )

    log.info("Generated code-signing PFX: CN=%s, valid %d days", common_name, days_valid)
    return pfx_bytes, cert_pem, key_pem


def get_certificate_details(cert_pem: bytes) -> dict[str, Any]:
    """Extract human-readable details from a PEM certificate."""
    cert = x509.load_pem_x509_certificate(cert_pem)
    fp = cert.fingerprint(hashes.SHA256())
    fp_hex = ":".join(f"{b:02X}" for b in fp)

    pub_key = cert.public_key()
    if isinstance(pub_key, rsa.RSAPublicKey):
        key_info = f"RSA-{pub_key.key_size}"
    elif isinstance(pub_key, ec.EllipticCurvePublicKey):
        key_info = f"EC-{pub_key.curve.name}"
    else:
        key_info = "Unknown"

    extensions: dict[str, Any] = {}
    try:
        eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage)
        extensions["extended_key_usage"] = [oid.dotted_string for oid in eku.value]
    except x509.ExtensionNotFound:
        pass
    try:
        ku = cert.extensions.get_extension_for_class(x509.KeyUsage)
        usage = []
        if ku.value.digital_signature:
            usage.append("digitalSignature")
        if ku.value.content_commitment:
            usage.append("contentCommitment")
        if ku.value.key_encipherment:
            usage.append("keyEncipherment")
        extensions["key_usage"] = usage
    except x509.ExtensionNotFound:
        pass

    return {
        "subject": cert.subject.rfc4514_string(),
        "issuer": cert.issuer.rfc4514_string(),
        "serial_number": str(cert.serial_number),
        "not_valid_before": cert.not_valid_before_utc.isoformat(),
        "not_valid_after": cert.not_valid_after_utc.isoformat(),
        "fingerprint_sha256": fp_hex,
        "key_type": key_info,
        "extensions": extensions,
        "is_code_signing": _is_code_signing_cert(cert),
    }


def _is_code_signing_cert(cert: x509.Certificate) -> bool:
    try:
        eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage)
        return ExtendedKeyUsageOID.CODE_SIGNING in eku.value
    except x509.ExtensionNotFound:
        return False


class CertStore:
    """Directory-based PFX certificate store."""

    def __init__(self, certs_dir: Optional[Path] = None, pfx_password: str = ""):
        settings = get_settings()
        self.certs_dir = certs_dir or settings.certs_dir
        self.pfx_password = pfx_password or settings.pfx_password
        self._certs: dict[str, tuple[bytes, bytes]] = {}  # name -> (pfx_bytes, cert_pem)

    def init(self) -> None:
        """Load existing certs and auto-generate default if none exist."""
        self.certs_dir.mkdir(parents=True, exist_ok=True)
        self._load_all()

        if not self._certs:
            log.info("No certificates found — generating default cert")
            self.generate("default")

    def _load_all(self) -> None:
        """Load all PFX files from the certs directory."""
        for pfx_path in self.certs_dir.glob("*.pfx"):
            name = pfx_path.stem
            try:
                pfx_bytes = pfx_path.read_bytes()
                password = self.pfx_password.encode() if self.pfx_password else None
                private_key, cert, _ = pkcs12.load_key_and_certificates(pfx_bytes, password)
                if cert is None:
                    log.warning("Skipping %s: no certificate in PFX", name)
                    continue
                cert_pem = cert.public_bytes(Encoding.PEM)
                self._certs[name] = (pfx_bytes, cert_pem)
                log.info("Loaded certificate: %s", name)
            except Exception as e:
                log.error("Failed to load %s: %s", pfx_path, e)

    def generate(self, name: str) -> dict[str, Any]:
        """Generate a new self-signed code-signing certificate."""
        pfx_password = self.pfx_password.encode() if self.pfx_password else b""
        pfx_bytes, cert_pem, _ = create_code_signing_pfx(
            common_name=f"Macro Sign Service ({name})",
            pfx_password=pfx_password,
        )
        pfx_path = self.certs_dir / f"{name}.pfx"
        pfx_path.write_bytes(pfx_bytes)
        self._certs[name] = (pfx_bytes, cert_pem)
        log.info("Generated and saved certificate: %s", name)
        return get_certificate_details(cert_pem)

    def list_certs(self) -> list[dict[str, Any]]:
        """Return summary info for all loaded certificates."""
        result = []
        for name, (_, cert_pem) in self._certs.items():
            details = get_certificate_details(cert_pem)
            details["name"] = name
            result.append(details)
        return result

    def get_cert(self, name: str) -> dict[str, Any]:
        """Get details for a specific certificate."""
        if name not in self._certs:
            raise CertStoreError(f"Certificate '{name}' not found")
        _, cert_pem = self._certs[name]
        details = get_certificate_details(cert_pem)
        details["name"] = name
        return details

    def get_pfx(self, name: str) -> bytes:
        """Get the raw PFX bytes for a certificate."""
        if name not in self._certs:
            raise CertStoreError(f"Certificate '{name}' not found")
        return self._certs[name][0]

    def get_cert_pem(self, name: str) -> bytes:
        """Get the PEM-encoded certificate."""
        if name not in self._certs:
            raise CertStoreError(f"Certificate '{name}' not found")
        return self._certs[name][1]

    def get_fingerprint(self, name: str) -> str:
        """Get the SHA256 fingerprint for a certificate."""
        cert_pem = self.get_cert_pem(name)
        cert = x509.load_pem_x509_certificate(cert_pem)
        return cert.fingerprint(hashes.SHA256()).hex()
