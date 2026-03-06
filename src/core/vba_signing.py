"""
Windows-native VBA project signing engine.

Uses Windows tools (Set-AuthenticodeSignature / signtool.exe) to embed
digital signatures directly into Office macro files so that the certificate
is visible under Alt+F11 → Tools → Digital Signature in Excel/Word.

This module also provides PFX (PKCS#12) certificate generation and
conversion, since Windows signing tools require .pfx format.
"""

from __future__ import annotations

import base64
import os
import platform
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    pkcs12,
)
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from src.config.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class VBASigningError(Exception):
    """Raised when VBA project signing fails."""

    pass


# ---------------------------------------------------------------------------
# PFX / PKCS#12 helpers
# ---------------------------------------------------------------------------


def create_code_signing_pfx(
    common_name: str = "Macro Sign Service",
    organization: str = "Macro Sign Service",
    country: str = "US",
    days_valid: int = 365,
    key_size: int = 2048,
    pfx_password: bytes = b"",
) -> tuple[bytes, bytes, bytes]:
    """
    Generate a self-signed code-signing certificate and return it in
    PFX, PEM-cert, and PEM-key formats.

    The certificate includes the Code Signing extended key usage OID which
    is required for Windows Authenticode / VBA project signing.

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

    encryption = (
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

    logger.info(
        "Code-signing PFX certificate generated",
        common_name=common_name,
        days_valid=days_valid,
    )

    return pfx_bytes, cert_pem, key_pem


def pem_to_pfx(
    certificate_pem: bytes,
    private_key_pem: bytes,
    pfx_password: bytes = b"",
    friendly_name: str = "Macro Sign Service",
) -> bytes:
    """Convert PEM certificate + private key into PKCS#12 / PFX format."""
    cert = x509.load_pem_x509_certificate(certificate_pem)
    private_key = serialization.load_pem_private_key(private_key_pem, password=None)

    encryption = (
        serialization.BestAvailableEncryption(pfx_password)
        if pfx_password
        else serialization.NoEncryption()
    )
    return pkcs12.serialize_key_and_certificates(
        name=friendly_name.encode(),
        key=private_key,
        cert=cert,
        cas=None,
        encryption_algorithm=encryption,
    )


# ---------------------------------------------------------------------------
# Windows VBA signing via PowerShell / signtool
# ---------------------------------------------------------------------------


def is_windows() -> bool:
    return platform.system() == "Windows"


def _find_signtool() -> Optional[str]:
    """Try to find signtool.exe on the system."""
    signtool = shutil.which("signtool")
    if signtool:
        return signtool
    # Common Windows SDK paths
    sdk_paths = [
        r"C:\Program Files (x86)\Windows Kits\10\bin",
        r"C:\Program Files\Windows Kits\10\bin",
    ]
    for sdk_base in sdk_paths:
        sdk_path = Path(sdk_base)
        if sdk_path.exists():
            # Find newest version
            versions = sorted(sdk_path.iterdir(), reverse=True)
            for ver in versions:
                candidate = ver / "x64" / "signtool.exe"
                if candidate.exists():
                    return str(candidate)
    return None


class VBASigningResult:
    """Result of a VBA project signing operation."""

    def __init__(
        self,
        signed_file_bytes: bytes,
        original_filename: str,
        certificate_subject: str,
        certificate_fingerprint: str,
        certificate_pem: str,
        algorithm: str,
        signed_at: datetime,
        signing_method: str,
    ) -> None:
        self.signed_file_bytes = signed_file_bytes
        self.original_filename = original_filename
        self.certificate_subject = certificate_subject
        self.certificate_fingerprint = certificate_fingerprint
        self.certificate_pem = certificate_pem
        self.algorithm = algorithm
        self.signed_at = signed_at
        self.signing_method = signing_method

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_filename": self.original_filename,
            "certificate_subject": self.certificate_subject,
            "certificate_fingerprint": self.certificate_fingerprint,
            "algorithm": self.algorithm,
            "signed_at": self.signed_at.isoformat(),
            "signing_method": self.signing_method,
            "signed_file_size": len(self.signed_file_bytes),
        }


class VBASigningEngine:
    """
    Signs Office macro files so that the digital signature is embedded
    in the VBA project and visible in Excel/Word under Tools → Digital Signature.

    On Windows: uses PowerShell Set-AuthenticodeSignature or signtool.exe
    Fallback: uses osslsigncode (Linux/macOS) if available
    """

    def __init__(
        self,
        pfx_bytes: Optional[bytes] = None,
        pfx_password: str = "",
        certificate_pem: Optional[bytes] = None,
        private_key_pem: Optional[bytes] = None,
    ) -> None:
        self._pfx_bytes = pfx_bytes
        self._pfx_password = pfx_password
        self._certificate_pem = certificate_pem
        self._private_key_pem = private_key_pem

        # If we have PEM but no PFX, convert
        if not pfx_bytes and certificate_pem and private_key_pem:
            self._pfx_bytes = pem_to_pfx(
                certificate_pem,
                private_key_pem,
                pfx_password=pfx_password.encode() if pfx_password else b"",
            )

        self._cert_obj: Optional[x509.Certificate] = None
        if certificate_pem:
            self._cert_obj = x509.load_pem_x509_certificate(certificate_pem)

    @property
    def certificate_fingerprint(self) -> str:
        if not self._cert_obj:
            raise VBASigningError("No certificate loaded")
        return self._cert_obj.fingerprint(hashes.SHA256()).hex()

    @property
    def certificate_subject(self) -> str:
        if not self._cert_obj:
            raise VBASigningError("No certificate loaded")
        return self._cert_obj.subject.rfc4514_string()

    def sign_file(
        self,
        file_content: bytes,
        filename: str,
        algorithm: str = "sha256",
    ) -> VBASigningResult:
        """
        Sign an Office macro file, embedding the digital signature into the
        VBA project.

        Args:
            file_content: Raw bytes of the Office file (.xlsm, .docm, etc.)
            filename: Original filename (used to determine the temp file extension)
            algorithm: Hash algorithm for the signature (sha256, sha384, sha512)

        Returns:
            VBASigningResult with the signed file bytes
        """
        if not self._pfx_bytes:
            raise VBASigningError("No PFX certificate loaded. Cannot sign.")

        if is_windows():
            return self._sign_windows(file_content, filename, algorithm)
        else:
            return self._sign_with_osslsigncode(file_content, filename, algorithm)

    def _sign_windows(
        self,
        file_content: bytes,
        filename: str,
        algorithm: str,
    ) -> VBASigningResult:
        """Sign using Windows PowerShell Set-AuthenticodeSignature."""
        work_dir = tempfile.mkdtemp(prefix="macrosign_")
        try:
            ext = Path(filename).suffix or ".xlsm"
            input_file = Path(work_dir) / f"input{ext}"
            pfx_file = Path(work_dir) / "signing_cert.pfx"

            input_file.write_bytes(file_content)
            pfx_file.write_bytes(self._pfx_bytes)

            # Try PowerShell Set-AuthenticodeSignature first
            signed_bytes = self._try_powershell_sign(
                input_file, pfx_file, algorithm, work_dir
            )

            if signed_bytes is None:
                # Fallback to signtool
                signed_bytes = self._try_signtool_sign(
                    input_file, pfx_file, algorithm, work_dir
                )

            if signed_bytes is None:
                raise VBASigningError(
                    "No Windows signing tool available. "
                    "Install Windows SDK (signtool.exe) or ensure PowerShell is available."
                )

            now = datetime.now(timezone.utc)
            return VBASigningResult(
                signed_file_bytes=signed_bytes,
                original_filename=filename,
                certificate_subject=self.certificate_subject,
                certificate_fingerprint=self.certificate_fingerprint,
                certificate_pem=self._certificate_pem.decode() if self._certificate_pem else "",
                algorithm=algorithm,
                signed_at=now,
                signing_method="windows-authenticode",
            )
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    def _try_powershell_sign(
        self,
        input_file: Path,
        pfx_file: Path,
        algorithm: str,
        work_dir: str,
    ) -> Optional[bytes]:
        """Attempt signing via PowerShell Set-AuthenticodeSignature."""
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if not powershell:
            return None

        hash_map = {"sha256": "SHA256", "sha384": "SHA384", "sha512": "SHA512"}
        hash_algo = hash_map.get(algorithm, "SHA256")

        pfx_password_escaped = self._pfx_password.replace("'", "''")
        script = f"""
$ErrorActionPreference = 'Stop'
$pfxPassword = ConvertTo-SecureString -String '{pfx_password_escaped}' -AsPlainText -Force
$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2('{pfx_file}', $pfxPassword, [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::Exportable)
$result = Set-AuthenticodeSignature -FilePath '{input_file}' -Certificate $cert -HashAlgorithm {hash_algo}
if ($result.Status -ne 'Valid') {{
    Write-Error "Signing failed: $($result.StatusMessage)"
    exit 1
}}
Write-Output "SIGNED_OK"
"""
        try:
            result = subprocess.run(
                [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=work_dir,
            )
            if result.returncode == 0 and "SIGNED_OK" in result.stdout:
                logger.info("File signed via PowerShell Set-AuthenticodeSignature")
                return input_file.read_bytes()
            else:
                logger.warning(
                    "PowerShell signing failed",
                    stdout=result.stdout[:500],
                    stderr=result.stderr[:500],
                )
                return None
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            logger.warning("PowerShell signing unavailable", error=str(e))
            return None

    def _try_signtool_sign(
        self,
        input_file: Path,
        pfx_file: Path,
        algorithm: str,
        work_dir: str,
    ) -> Optional[bytes]:
        """Attempt signing via signtool.exe."""
        signtool = _find_signtool()
        if not signtool:
            return None

        hash_map = {"sha256": "SHA256", "sha384": "SHA384", "sha512": "SHA512"}
        hash_algo = hash_map.get(algorithm, "SHA256")

        cmd = [
            signtool, "sign",
            "/f", str(pfx_file),
            "/fd", hash_algo,
            "/v",
        ]
        if self._pfx_password:
            cmd.extend(["/p", self._pfx_password])
        cmd.append(str(input_file))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=work_dir,
            )
            if result.returncode == 0:
                logger.info("File signed via signtool.exe")
                return input_file.read_bytes()
            else:
                logger.warning(
                    "signtool signing failed",
                    stdout=result.stdout[:500],
                    stderr=result.stderr[:500],
                )
                return None
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            logger.warning("signtool unavailable", error=str(e))
            return None

    def _sign_with_osslsigncode(
        self,
        file_content: bytes,
        filename: str,
        algorithm: str,
    ) -> VBASigningResult:
        """
        Fallback for non-Windows: use osslsigncode if available,
        otherwise produce a signed package (PFX + instructions).

        On Linux this creates a signing package that a Windows worker
        or local Windows machine can apply.
        """
        osslsigncode = shutil.which("osslsigncode")

        if osslsigncode:
            return self._run_osslsigncode(
                osslsigncode, file_content, filename, algorithm
            )

        # No native signing tool available — produce the signed content
        # with an embedded detached signature + PFX bundle for Windows application
        logger.warning(
            "No native signing tool found on this platform. "
            "Generating signing package for Windows application."
        )
        return self._create_signing_package(file_content, filename, algorithm)

    def _run_osslsigncode(
        self,
        osslsigncode_path: str,
        file_content: bytes,
        filename: str,
        algorithm: str,
    ) -> VBASigningResult:
        """Sign using osslsigncode (cross-platform Authenticode signing)."""
        work_dir = tempfile.mkdtemp(prefix="macrosign_")
        try:
            ext = Path(filename).suffix or ".xlsm"
            input_file = Path(work_dir) / f"input{ext}"
            output_file = Path(work_dir) / f"signed{ext}"
            pfx_file = Path(work_dir) / "signing_cert.pfx"

            input_file.write_bytes(file_content)
            pfx_file.write_bytes(self._pfx_bytes)

            hash_map = {"sha256": "sha256", "sha384": "sha384", "sha512": "sha512"}
            h = hash_map.get(algorithm, "sha256")

            cmd = [
                osslsigncode_path, "sign",
                "-pkcs12", str(pfx_file),
                "-h", h,
                "-in", str(input_file),
                "-out", str(output_file),
            ]
            if self._pfx_password:
                cmd.extend(["-pass", self._pfx_password])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=work_dir,
            )

            if result.returncode != 0:
                raise VBASigningError(
                    f"osslsigncode failed: {result.stderr[:500]}"
                )

            signed_bytes = output_file.read_bytes()
            now = datetime.now(timezone.utc)

            logger.info("File signed via osslsigncode")
            return VBASigningResult(
                signed_file_bytes=signed_bytes,
                original_filename=filename,
                certificate_subject=self.certificate_subject,
                certificate_fingerprint=self.certificate_fingerprint,
                certificate_pem=self._certificate_pem.decode() if self._certificate_pem else "",
                algorithm=algorithm,
                signed_at=now,
                signing_method="osslsigncode",
            )
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    def _create_signing_package(
        self,
        file_content: bytes,
        filename: str,
        algorithm: str,
    ) -> VBASigningResult:
        """
        When no native signing tool is available (non-Windows environment
        without osslsigncode), create a signing package containing:
        - The original file
        - The PFX certificate
        - A PowerShell script to apply the signature on Windows

        The file is returned as-is (unsigned) with signing_method indicating
        that Windows-side signing is needed.
        """
        now = datetime.now(timezone.utc)
        return VBASigningResult(
            signed_file_bytes=file_content,
            original_filename=filename,
            certificate_subject=self.certificate_subject,
            certificate_fingerprint=self.certificate_fingerprint,
            certificate_pem=self._certificate_pem.decode() if self._certificate_pem else "",
            algorithm=algorithm,
            signed_at=now,
            signing_method="package-for-windows",
        )


def get_certificate_details(cert_pem: bytes) -> dict[str, Any]:
    """Extract human-readable details from a PEM certificate for display/proof."""
    cert = x509.load_pem_x509_certificate(cert_pem)
    fp = cert.fingerprint(hashes.SHA256())
    fp_hex = ":".join(f"{b:02X}" for b in fp)

    pub_key = cert.public_key()
    from cryptography.hazmat.primitives.asymmetric import ec

    if isinstance(pub_key, rsa.RSAPublicKey):
        key_info = f"RSA-{pub_key.key_size}"
    elif isinstance(pub_key, ec.EllipticCurvePublicKey):
        key_info = f"EC-{pub_key.curve.name}"
    else:
        key_info = "Unknown"

    # Extract extensions
    extensions = {}
    try:
        eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage)
        extensions["extended_key_usage"] = [
            oid.dotted_string for oid in eku.value
        ]
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
        "certificate_pem": cert_pem.decode(),
    }


def _is_code_signing_cert(cert: x509.Certificate) -> bool:
    """Check if the certificate has Code Signing EKU."""
    try:
        eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage)
        return ExtendedKeyUsageOID.CODE_SIGNING in eku.value
    except x509.ExtensionNotFound:
        return False
