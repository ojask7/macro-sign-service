"""
Windows Signing Agent — lightweight HTTP service for Office VBA project signing.

This is a standalone Flask/FastAPI micro-service designed to run on a Windows
machine that has:
  1. Microsoft Office installed (provides msosip.dll / msosipx.dll SIP DLLs)
  2. Windows SDK or signtool.exe on PATH
  3. Python 3.9+ with flask installed

Architecture:
  Linux API server  ──(HTTP)──►  Windows Signing Agent  ──(signtool+SIP)──►  Signed file
                                 (this service)

The Office SIP (Subject Interface Package) DLLs are registered automatically
when Office is installed. They tell signtool how to locate and sign the VBA
project data stream inside Office file formats (.xlsm, .docm, .pptm, etc.).

Without these SIP DLLs, signtool produces Authenticode signatures on the file
envelope — which is NOT what Office checks when you open Alt+F11 → Tools →
Digital Signature. Office only checks the VBA project signature.

Usage:
    pip install flask
    python windows_signing_agent.py --port 9001

    # Or as a Windows Service via NSSM:
    nssm install MacroSignAgent "C:\\Python311\\python.exe" "C:\\macro-sign\\windows_signing_agent.py"
"""

from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

try:
    from flask import Flask, jsonify, request
except ImportError:
    print("Flask is required. Install with: pip install flask", file=sys.stderr)
    sys.exit(1)

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("signing-agent")

# ---------------------------------------------------------------------------
# signtool discovery
# ---------------------------------------------------------------------------

SIGNTOOL_PATH: Optional[str] = None


def find_signtool() -> Optional[str]:
    """Locate signtool.exe — check PATH first, then Windows SDK directories."""
    global SIGNTOOL_PATH
    if SIGNTOOL_PATH:
        return SIGNTOOL_PATH

    st = shutil.which("signtool")
    if st:
        SIGNTOOL_PATH = st
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
                SIGNTOOL_PATH = str(candidate)
                return SIGNTOOL_PATH

    return None


def check_office_sip_registered() -> dict:
    """
    Verify that the Office SIP DLLs are registered.
    These are required for signtool to sign VBA projects inside Office files.
    """
    checks = {
        "signtool_found": find_signtool() is not None,
        "signtool_path": find_signtool(),
        "platform": sys.platform,
        "office_sip_status": "unknown",
    }

    # Check for common Office SIP DLL locations
    sip_dlls = [
        r"C:\Program Files\Microsoft Office\root\Office16\msosip.dll",
        r"C:\Program Files (x86)\Microsoft Office\root\Office16\msosip.dll",
        r"C:\Program Files\Microsoft Office\Office16\msosip.dll",
        r"C:\Program Files (x86)\Microsoft Office\Office16\msosip.dll",
        r"C:\Program Files\Microsoft Office\root\Office15\msosip.dll",
    ]

    found_sip = None
    for dll_path in sip_dlls:
        if Path(dll_path).exists():
            found_sip = dll_path
            break

    if found_sip:
        checks["office_sip_status"] = "found"
        checks["office_sip_path"] = found_sip
    else:
        # Try registry check via PowerShell
        try:
            result = subprocess.run(
                [
                    "powershell", "-NoProfile", "-Command",
                    "Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Cryptography\\OID\\EncodingType 0\\CryptSIPDllVerifyIndirectData\\{000C10F1-0000-0000-C000-000000000046}' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Dll"
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
# Signing logic
# ---------------------------------------------------------------------------


def sign_office_file_with_signtool(
    file_bytes: bytes,
    filename: str,
    pfx_bytes: bytes,
    pfx_password: str = "",
    hash_algorithm: str = "SHA256",
) -> tuple[bytes, dict]:
    """
    Sign an Office file using signtool.exe with Office SIP.

    This produces a VBA project signature that is recognized by
    Excel/Word under Alt+F11 → Tools → Digital Signature.

    Args:
        file_bytes: Raw Office file content
        filename: Original filename (for extension detection)
        pfx_bytes: PFX/PKCS#12 certificate bytes
        pfx_password: Password for the PFX file
        hash_algorithm: SHA256, SHA384, or SHA512

    Returns:
        (signed_file_bytes, metadata_dict)
    """
    signtool = find_signtool()
    if not signtool:
        raise RuntimeError(
            "signtool.exe not found. Install Windows SDK or add signtool to PATH."
        )

    work_dir = tempfile.mkdtemp(prefix="macrosign_win_")
    try:
        ext = Path(filename).suffix or ".xlsm"
        input_file = Path(work_dir) / f"macro_file{ext}"
        pfx_file = Path(work_dir) / "signing_cert.pfx"

        input_file.write_bytes(file_bytes)
        pfx_file.write_bytes(pfx_bytes)

        # Build signtool command
        # Key: signtool with Office SIP registered will sign the VBA project
        cmd = [
            signtool, "sign",
            "/f", str(pfx_file),
            "/fd", hash_algorithm,
        ]
        if pfx_password:
            cmd.extend(["/p", pfx_password])
        # /v for verbose output to capture details
        cmd.append("/v")
        cmd.append(str(input_file))

        log.info(f"Running signtool: {' '.join(cmd[:4])} ... {input_file.name}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=work_dir,
        )

        if result.returncode != 0:
            log.error(f"signtool failed:\nstdout: {result.stdout}\nstderr: {result.stderr}")
            raise RuntimeError(
                f"signtool failed (exit {result.returncode}): {result.stderr or result.stdout}"
            )

        signed_bytes = input_file.read_bytes()
        log.info(f"File signed successfully: {filename} ({len(signed_bytes)} bytes)")

        # Verify the signature
        verify_cmd = [signtool, "verify", "/pa", "/v", str(input_file)]
        verify_result = subprocess.run(
            verify_cmd, capture_output=True, text=True, timeout=30, cwd=work_dir,
        )

        metadata = {
            "signed": True,
            "signtool_output": result.stdout[:1000],
            "verification_output": verify_result.stdout[:1000],
            "verification_passed": verify_result.returncode == 0,
            "hash_algorithm": hash_algorithm,
            "signed_at": datetime.now(timezone.utc).isoformat(),
            "file_size": len(signed_bytes),
        }

        return signed_bytes, metadata

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------


@app.route("/health", methods=["GET"])
def health():
    """Health check with signing capability status."""
    sip_info = check_office_sip_registered()
    healthy = sip_info["signtool_found"] and sip_info["office_sip_status"] in ("found", "registered")
    return jsonify({
        "status": "healthy" if healthy else "degraded",
        "service": "windows-signing-agent",
        "signing_ready": healthy,
        **sip_info,
    }), 200 if healthy else 503


@app.route("/sign", methods=["POST"])
def sign_file():
    """
    Sign an Office macro file.

    Expects JSON body:
    {
        "file_b64": "<base64-encoded Office file>",
        "filename": "report.xlsm",
        "pfx_b64": "<base64-encoded PFX certificate>",
        "pfx_password": "",
        "hash_algorithm": "SHA256"
    }

    Returns JSON:
    {
        "signed_file_b64": "<base64-encoded signed file>",
        "signed": true,
        "metadata": { ... }
    }
    """
    try:
        data = request.get_json(force=True)

        file_bytes = base64.b64decode(data["file_b64"])
        filename = data.get("filename", "macro.xlsm")
        pfx_bytes = base64.b64decode(data["pfx_b64"])
        pfx_password = data.get("pfx_password", "")
        hash_algorithm = data.get("hash_algorithm", "SHA256")

        log.info(f"Sign request: {filename} ({len(file_bytes)} bytes), algo={hash_algorithm}")

        signed_bytes, metadata = sign_office_file_with_signtool(
            file_bytes=file_bytes,
            filename=filename,
            pfx_bytes=pfx_bytes,
            pfx_password=pfx_password,
            hash_algorithm=hash_algorithm,
        )

        return jsonify({
            "signed_file_b64": base64.b64encode(signed_bytes).decode(),
            "signed": True,
            "filename": filename,
            "metadata": metadata,
        })

    except KeyError as e:
        return jsonify({"error": f"Missing required field: {e}"}), 400
    except RuntimeError as e:
        return jsonify({"error": str(e), "signed": False}), 500
    except Exception as e:
        log.exception("Unexpected error during signing")
        return jsonify({"error": f"Internal error: {e}", "signed": False}), 500


@app.route("/verify", methods=["POST"])
def verify_file():
    """
    Verify an Office file's digital signature using signtool.

    Expects JSON body:
    {
        "file_b64": "<base64-encoded signed Office file>",
        "filename": "report_signed.xlsm"
    }
    """
    try:
        data = request.get_json(force=True)
        file_bytes = base64.b64decode(data["file_b64"])
        filename = data.get("filename", "signed.xlsm")

        signtool = find_signtool()
        if not signtool:
            return jsonify({"error": "signtool.exe not found"}), 503

        work_dir = tempfile.mkdtemp(prefix="macrosign_verify_")
        try:
            ext = Path(filename).suffix or ".xlsm"
            file_path = Path(work_dir) / f"verify{ext}"
            file_path.write_bytes(file_bytes)

            result = subprocess.run(
                [signtool, "verify", "/pa", "/v", str(file_path)],
                capture_output=True, text=True, timeout=30, cwd=work_dir,
            )

            return jsonify({
                "valid": result.returncode == 0,
                "output": result.stdout[:2000],
                "errors": result.stderr[:2000] if result.returncode != 0 else None,
            })
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Windows Signing Agent for Office VBA macros")
    parser.add_argument("--port", type=int, default=9001, help="Port to listen on")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--check", action="store_true", help="Check signing prerequisites and exit")
    args = parser.parse_args()

    if args.check:
        print("=== Windows Signing Agent Prerequisites Check ===")
        info = check_office_sip_registered()
        for k, v in info.items():
            print(f"  {k}: {v}")
        ready = info["signtool_found"] and info["office_sip_status"] in ("found", "registered")
        print(f"\n  Signing Ready: {'YES' if ready else 'NO'}")
        if not ready:
            print("\n  To fix:")
            if not info["signtool_found"]:
                print("    - Install Windows SDK: https://developer.microsoft.com/en-us/windows/downloads/windows-sdk/")
            if info["office_sip_status"] not in ("found", "registered"):
                print("    - Install Microsoft Office (provides msosip.dll SIP DLLs)")
        sys.exit(0 if ready else 1)

    log.info(f"Starting Windows Signing Agent on {args.host}:{args.port}")
    info = check_office_sip_registered()
    log.info(f"signtool: {info.get('signtool_path', 'NOT FOUND')}")
    log.info(f"Office SIP: {info.get('office_sip_status', 'unknown')}")

    app.run(host=args.host, port=args.port, debug=False)
