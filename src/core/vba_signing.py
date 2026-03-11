"""
VBA project signing engine.

IMPORTANT — WHY ONLY WINDOWS CAN SIGN VBA PROJECTS:
  Office VBA project signing requires Microsoft's Office SIP (Subject Interface
  Package) DLLs (msosip.dll / msosipx.dll).  These DLLs are installed
  automatically when Microsoft Office is present on Windows.  They register
  with the Windows CryptoAPI as a SIP provider and tell signtool.exe how to
  locate, hash, and embed a digital signature inside the VBA project stream
  of an Office compound document (.xlsm, .docm, .pptm, etc.).

  WITHOUT the Office SIP DLLs:
    - osslsigncode → signs the PE/Authenticode envelope, NOT the VBA project.
      Office ignores this.
    - Set-AuthenticodeSignature → same issue; produces an Authenticode sig
      that Office does not check for VBA macros.
    - Any Linux-based tool → cannot produce what Office expects.

  Office checks the VBA project signature (Alt+F11 -> Tools -> Digital
  Signature).  That signature lives inside the OLE compound document and can
  ONLY be created by signtool.exe when the Office SIP is registered.

Architecture:
  1. On Windows (with Office + Windows SDK): sign locally via signtool.exe
  2. On Linux / Docker: delegate to a remote Windows Signing Agent over HTTP
     (see scripts/windows_signing_agent.py)
  3. Fallback: return the unsigned file + PFX + instructions so the caller
     can sign on a Windows machine manually.

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

import httpx
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
    is required for signtool / VBA project signing on Windows.

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
# Helpers
# ---------------------------------------------------------------------------


def is_windows() -> bool:
    return platform.system() == "Windows"


def _find_signtool() -> Optional[str]:
    """Try to find signtool.exe on the system."""
    signtool = shutil.which("signtool")
    if signtool:
        return signtool
    sdk_paths = [
        r"C:\Program Files (x86)\Windows Kits\10\bin",
        r"C:\Program Files\Windows Kits\10\bin",
    ]
    for sdk_base in sdk_paths:
        sdk_path = Path(sdk_base)
        if sdk_path.exists():
            versions = sorted(sdk_path.iterdir(), reverse=True)
            for ver in versions:
                candidate = ver / "x64" / "signtool.exe"
                if candidate.exists():
                    return str(candidate)
    return None


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class VBASigningEngine:
    """
    Signs Office macro files so the digital signature is embedded in the
    VBA project and visible in Excel/Word under Tools -> Digital Signature.

    Priority order:
      1. Local Windows signtool.exe  (requires Office SIP DLLs on this machine)
      2. Remote Windows Signing Agent (HTTP call — see scripts/windows_signing_agent.py)
      3. Fallback: returns unsigned file + PFX for manual Windows signing
    """

    def __init__(
        self,
        pfx_bytes: Optional[bytes] = None,
        pfx_password: str = "",
        certificate_pem: Optional[bytes] = None,
        private_key_pem: Optional[bytes] = None,
        windows_agent_url: Optional[str] = None,
    ) -> None:
        self._pfx_bytes = pfx_bytes
        self._pfx_password = pfx_password
        self._certificate_pem = certificate_pem
        self._private_key_pem = private_key_pem
        self._windows_agent_url = (
            windows_agent_url
            or os.environ.get("WINDOWS_SIGNING_AGENT_URL", "")
        )

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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def sign_file(
        self,
        file_content: bytes,
        filename: str,
        algorithm: str = "sha256",
    ) -> VBASigningResult:
        """
        Sign an Office macro file so the certificate is visible in the
        VBA editor Digital Signature dialog.

        Tries in order:
          1. Local signtool.exe (Windows + Office SIP)
          2. Remote Windows Signing Agent (HTTP)
          3. Fallback: unsigned file + PFX for manual signing
        """
        if not self._pfx_bytes:
            raise VBASigningError("No PFX certificate loaded. Cannot sign.")

        # 1. Local Windows signing (signtool + Office SIP)
        if is_windows():
            result = self._sign_local_signtool(file_content, filename, algorithm)
            if result:
                return result

        # 2. Remote Windows Signing Agent
        if self._windows_agent_url:
            result = self._sign_via_agent(file_content, filename, algorithm)
            if result:
                return result

        # 3. Fallback — no signing capability
        logger.warning(
            "No Windows signing capability available. "
            "VBA project signing requires signtool.exe + Office SIP DLLs "
            "(only on Windows with Microsoft Office installed). "
            "Set WINDOWS_SIGNING_AGENT_URL to point to a Windows signing agent, "
            "or run this service on Windows with Office installed.",
            filename=filename,
        )
        return self._create_unsigned_package(file_content, filename, algorithm)

    # ------------------------------------------------------------------
    # Method 1: local signtool.exe on Windows
    # ------------------------------------------------------------------

    def _sign_local_signtool(
        self,
        file_content: bytes,
        filename: str,
        algorithm: str,
    ) -> Optional[VBASigningResult]:
        """
        Sign using local signtool.exe with Office SIP DLLs.
        Only works on Windows with Office installed.
        """
        signtool = _find_signtool()
        if not signtool:
            logger.warning("signtool.exe not found on this Windows machine")
            return None

        work_dir = tempfile.mkdtemp(prefix="macrosign_")
        try:
            ext = Path(filename).suffix or ".xlsm"
            input_file = Path(work_dir) / f"input{ext}"
            pfx_file = Path(work_dir) / "signing_cert.pfx"

            input_file.write_bytes(file_content)
            pfx_file.write_bytes(self._pfx_bytes)

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

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120, cwd=work_dir,
            )

            if result.returncode != 0:
                logger.error(
                    "signtool signing failed",
                    stdout=result.stdout[:500],
                    stderr=result.stderr[:500],
                )
                return None

            # Verify
            verify_cmd = [signtool, "verify", "/pa", "/v", str(input_file)]
            verify_result = subprocess.run(
                verify_cmd, capture_output=True, text=True, timeout=30, cwd=work_dir,
            )

            signed_bytes = input_file.read_bytes()
            now = datetime.now(timezone.utc)

            logger.info(
                "File signed via local signtool + Office SIP",
                filename=filename,
                verified=verify_result.returncode == 0,
            )

            return VBASigningResult(
                signed_file_bytes=signed_bytes,
                original_filename=filename,
                certificate_subject=self.certificate_subject,
                certificate_fingerprint=self.certificate_fingerprint,
                certificate_pem=self._certificate_pem.decode() if self._certificate_pem else "",
                algorithm=algorithm,
                signed_at=now,
                signing_method="signtool-office-sip",
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            logger.error("Local signtool signing failed", error=str(e))
            return None
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Method 2: remote Windows Signing Agent
    # ------------------------------------------------------------------

    def _sign_via_agent(
        self,
        file_content: bytes,
        filename: str,
        algorithm: str,
    ) -> Optional[VBASigningResult]:
        """
        Delegate signing to the Windows Signing Agent
        (scripts/windows_signing_agent.py running on a Windows VM).
        """
        agent_url = self._windows_agent_url.rstrip("/")
        hash_map = {"sha256": "SHA256", "sha384": "SHA384", "sha512": "SHA512"}
        hash_algo = hash_map.get(algorithm, "SHA256")

        payload = {
            "file_b64": base64.b64encode(file_content).decode(),
            "filename": filename,
            "pfx_b64": base64.b64encode(self._pfx_bytes).decode(),
            "pfx_password": self._pfx_password,
            "hash_algorithm": hash_algo,
        }

        try:
            # Health check
            with httpx.Client(timeout=10.0) as client:
                health = client.get(f"{agent_url}/health")
                health_data = health.json()
                if not health_data.get("signing_ready"):
                    logger.warning(
                        "Windows Signing Agent not ready",
                        agent_url=agent_url,
                        status=health_data,
                    )
                    return None

            # Sign
            with httpx.Client(timeout=120.0) as client:
                response = client.post(f"{agent_url}/sign", json=payload)

            if response.status_code != 200:
                logger.error(
                    "Windows Signing Agent error",
                    status_code=response.status_code,
                    body=response.text[:500],
                )
                return None

            result_data = response.json()
            if not result_data.get("signed"):
                logger.error(
                    "Windows Signing Agent signing failed",
                    error=result_data.get("error"),
                )
                return None

            signed_bytes = base64.b64decode(result_data["signed_file_b64"])
            now = datetime.now(timezone.utc)

            logger.info(
                "File signed via Windows Signing Agent",
                filename=filename,
                agent_url=agent_url,
            )

            return VBASigningResult(
                signed_file_bytes=signed_bytes,
                original_filename=filename,
                certificate_subject=self.certificate_subject,
                certificate_fingerprint=self.certificate_fingerprint,
                certificate_pem=self._certificate_pem.decode() if self._certificate_pem else "",
                algorithm=algorithm,
                signed_at=now,
                signing_method="windows-agent-signtool-sip",
            )

        except httpx.ConnectError:
            logger.warning("Cannot reach Windows Signing Agent", agent_url=agent_url)
            return None
        except Exception as e:
            logger.error("Windows Signing Agent error", agent_url=agent_url, error=str(e))
            return None

    # ------------------------------------------------------------------
    # Method 3: fallback — unsigned package
    # ------------------------------------------------------------------

    def _create_unsigned_package(
        self,
        file_content: bytes,
        filename: str,
        algorithm: str,
    ) -> VBASigningResult:
        """
        No Windows signing available.  Return the file unsigned with
        signing_method='unsigned-requires-windows'.  The API layer will
        include the PFX so the caller can sign on a Windows machine.
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
            signing_method="unsigned-requires-windows",
        )


# ---------------------------------------------------------------------------
# Certificate details helper
# ---------------------------------------------------------------------------


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

    extensions = {}
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
        "certificate_pem": cert_pem.decode(),
    }


def _is_code_signing_cert(cert: x509.Certificate) -> bool:
    """Check if the certificate has Code Signing EKU."""
    try:
        eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage)
        return ExtendedKeyUsageOID.CODE_SIGNING in eku.value
    except x509.ExtensionNotFound:
        return False
