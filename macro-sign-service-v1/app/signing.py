"""Signing engine — signtool wrapper for Office files + RSA for text macros."""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, utils
from cryptography.hazmat.primitives.serialization import pkcs12

log = logging.getLogger(__name__)


class SigningError(Exception):
    """Raised when signing fails."""


# ---------------------------------------------------------------------------
# signtool discovery
# ---------------------------------------------------------------------------

_signtool_cache: Optional[str] = None


def find_signtool() -> Optional[str]:
    """Locate signtool.exe — PATH first, then Windows SDK directories."""
    global _signtool_cache
    if _signtool_cache:
        return _signtool_cache

    st = shutil.which("signtool")
    if st:
        _signtool_cache = st
        return st

    sdk_bases = [
        r"C:\Program Files (x86)\Windows Kits\10\bin",
        r"C:\Program Files\Windows Kits\10\bin",
    ]
    for sdk_base in sdk_bases:
        p = Path(sdk_base)
        if not p.exists():
            continue
        for ver_dir in sorted(p.iterdir(), reverse=True):
            candidate = ver_dir / "x64" / "signtool.exe"
            if candidate.exists():
                _signtool_cache = str(candidate)
                return _signtool_cache

    return None


# ---------------------------------------------------------------------------
# Office SIP check
# ---------------------------------------------------------------------------


def check_office_sip() -> dict:
    """Check whether Office SIP DLLs are registered (required for VBA signing)."""
    checks: dict = {
        "signtool_found": find_signtool() is not None,
        "signtool_path": find_signtool(),
        "office_sip_status": "unknown",
    }

    sip_dlls = [
        r"C:\Program Files\Microsoft Office\root\Office16\msosip.dll",
        r"C:\Program Files (x86)\Microsoft Office\root\Office16\msosip.dll",
        r"C:\Program Files\Microsoft Office\Office16\msosip.dll",
        r"C:\Program Files (x86)\Microsoft Office\Office16\msosip.dll",
        r"C:\Program Files\Microsoft Office\root\Office15\msosip.dll",
    ]

    for dll_path in sip_dlls:
        if Path(dll_path).exists():
            checks["office_sip_status"] = "found"
            checks["office_sip_path"] = dll_path
            return checks

    # Try registry via PowerShell
    try:
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                "Get-ItemProperty "
                "'HKLM:\\SOFTWARE\\Microsoft\\Cryptography\\OID\\EncodingType 0"
                "\\CryptSIPDllVerifyIndirectData"
                "\\{000C10F1-0000-0000-C000-000000000046}' "
                "-ErrorAction SilentlyContinue | Select-Object -ExpandProperty Dll",
            ],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            checks["office_sip_status"] = "registered"
            checks["office_sip_dll"] = result.stdout.strip()
        else:
            checks["office_sip_status"] = "not_found"
    except Exception:
        checks["office_sip_status"] = "check_failed"

    return checks


# ---------------------------------------------------------------------------
# Office file signing (signtool + Office SIP)
# ---------------------------------------------------------------------------


def _sign_office_file_sync(
    file_bytes: bytes,
    filename: str,
    pfx_bytes: bytes,
    pfx_password: str = "",
    hash_algorithm: str = "SHA256",
) -> tuple[bytes, dict]:
    """Sign an Office file using signtool.exe (synchronous, runs in thread)."""
    signtool = find_signtool()
    if not signtool:
        raise SigningError("signtool.exe not found. Install Windows SDK.")

    work_dir = tempfile.mkdtemp(prefix="macrosign_")
    try:
        ext = Path(filename).suffix or ".xlsm"
        input_file = Path(work_dir) / f"macro_file{ext}"
        pfx_file = Path(work_dir) / "signing_cert.pfx"

        input_file.write_bytes(file_bytes)
        pfx_file.write_bytes(pfx_bytes)

        cmd = [
            signtool, "sign",
            "/f", str(pfx_file),
            "/fd", hash_algorithm,
        ]
        if pfx_password:
            cmd.extend(["/p", pfx_password])
        cmd.extend(["/v", str(input_file)])

        log.info("Running signtool sign: %s", input_file.name)
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120, cwd=work_dir,
        )

        if result.returncode != 0:
            log.error("signtool failed: %s %s", result.stdout[:500], result.stderr[:500])
            raise SigningError(
                f"signtool failed (exit {result.returncode}): "
                f"{result.stderr or result.stdout}"
            )

        signed_bytes = input_file.read_bytes()

        # Verify
        verify_result = subprocess.run(
            [signtool, "verify", "/pa", "/v", str(input_file)],
            capture_output=True, text=True, timeout=30, cwd=work_dir,
        )

        metadata = {
            "signing_method": "signtool-office-sip",
            "signtool_output": result.stdout[:1000],
            "verification_passed": verify_result.returncode == 0,
            "hash_algorithm": hash_algorithm,
            "signed_at": datetime.now(timezone.utc).isoformat(),
            "file_size": len(signed_bytes),
        }

        log.info("Signed successfully: %s (%d bytes)", filename, len(signed_bytes))
        return signed_bytes, metadata

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


async def sign_office_file(
    file_bytes: bytes,
    filename: str,
    pfx_bytes: bytes,
    pfx_password: str = "",
    hash_algorithm: str = "SHA256",
) -> tuple[bytes, dict]:
    """Sign an Office file (async wrapper — runs signtool in a thread)."""
    return await asyncio.to_thread(
        _sign_office_file_sync,
        file_bytes, filename, pfx_bytes, pfx_password, hash_algorithm,
    )


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------


def _verify_file_sync(file_bytes: bytes, filename: str) -> dict:
    """Verify a signed file using signtool (synchronous)."""
    signtool = find_signtool()
    if not signtool:
        raise SigningError("signtool.exe not found")

    work_dir = tempfile.mkdtemp(prefix="macrosign_verify_")
    try:
        ext = Path(filename).suffix or ".xlsm"
        file_path = Path(work_dir) / f"verify{ext}"
        file_path.write_bytes(file_bytes)

        result = subprocess.run(
            [signtool, "verify", "/pa", "/v", str(file_path)],
            capture_output=True, text=True, timeout=30, cwd=work_dir,
        )

        return {
            "valid": result.returncode == 0,
            "output": result.stdout[:2000],
            "errors": result.stderr[:2000] if result.returncode != 0 else None,
        }
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


async def verify_file(file_bytes: bytes, filename: str) -> dict:
    """Verify a signed file (async wrapper)."""
    return await asyncio.to_thread(_verify_file_sync, file_bytes, filename)


# ---------------------------------------------------------------------------
# Text macro RSA signing (.vba, .bas, .cls)
# ---------------------------------------------------------------------------


def _sign_text_macro_sync(
    content: bytes,
    pfx_bytes: bytes,
    pfx_password: str = "",
    hash_algorithm: str = "SHA256",
) -> tuple[bytes, bytes, dict]:
    """
    Create an RSA detached signature for a text macro file.

    Returns:
        (original_content, signature_bytes, metadata)
    """
    password = pfx_password.encode() if pfx_password else None
    private_key, cert, _ = pkcs12.load_key_and_certificates(pfx_bytes, password)

    if private_key is None or cert is None:
        raise SigningError("PFX does not contain a private key and certificate")

    hash_map = {
        "SHA256": hashes.SHA256(),
        "SHA384": hashes.SHA384(),
        "SHA512": hashes.SHA512(),
    }
    chosen_hash = hash_map.get(hash_algorithm.upper(), hashes.SHA256())

    signature = private_key.sign(
        content,
        padding.PKCS1v15(),
        chosen_hash,
    )

    fingerprint = cert.fingerprint(hashes.SHA256()).hex()
    metadata = {
        "signing_method": "rsa-detached",
        "hash_algorithm": hash_algorithm,
        "certificate_fingerprint": fingerprint,
        "certificate_subject": cert.subject.rfc4514_string(),
        "signed_at": datetime.now(timezone.utc).isoformat(),
        "content_size": len(content),
        "signature_size": len(signature),
    }

    return content, signature, metadata


async def sign_text_macro(
    content: bytes,
    pfx_bytes: bytes,
    pfx_password: str = "",
    hash_algorithm: str = "SHA256",
) -> tuple[bytes, bytes, dict]:
    """Sign a text macro file (async wrapper)."""
    return await asyncio.to_thread(
        _sign_text_macro_sync, content, pfx_bytes, pfx_password, hash_algorithm,
    )
