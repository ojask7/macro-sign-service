#!/usr/bin/env python3
"""
tests/run_live_tests.py
========================
On-demand test runner for Macro Sign Service.

Creates dev and prod signing users, signs all macros from tests/input/ with
the appropriate environment certificate, writes signed files to tests/output/,
and generates a detailed per-file JSON + text report in tests/output/report/.

Usage:
    python tests/run_live_tests.py
    python tests/run_live_tests.py --base-url http://localhost:8000
    python tests/run_live_tests.py --env dev        # only dev macros
    python tests/run_live_tests.py --env prod       # only prod macros
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

# ─── Paths ────────────────────────────────────────────────────────────────────
TESTS_DIR  = Path(__file__).parent
INPUT_DIR  = TESTS_DIR / "input"
OUTPUT_DIR = TESTS_DIR / "output"
REPORT_DIR = TESTS_DIR / "output" / "report"

# ─── Environment definitions ─────────────────────────────────────────────────
ENVIRONMENTS: dict[str, dict] = {
    "dev": {
        "domain":    "dev-signing",
        "algorithm": "sha256",
        "cert_cn":   "dev.macro-sign.local",
        "cert_org":  "Dev Signing Environment",
        "user": {
            "username":  "dev_signer",
            "email":     "dev_signer@macro-sign.local",
            "password":  "DevSign@2026",
            "full_name": "Dev Signing User",
        },
    },
    "prod": {
        "domain":    "prod-signing",
        "algorithm": "sha256",
        "cert_cn":   "prod.macro-sign.local",
        "cert_org":  "Production Signing Environment",
        "user": {
            "username":  "prod_signer",
            "email":     "prod_signer@macro-sign.local",
            "password":  "ProdSign@2026",
            "full_name": "Prod Signing User",
        },
    },
}

# Macro prefix → environment mapping (fallback: dev)
MACRO_ENV_MAP: dict[str, str] = {
    "dev_":  "dev",
    "prod_": "prod",
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _log(msg: str, symbol: str = "·") -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"  {symbol} [{ts}] {msg}")

def _ok(msg: str)   -> None: _log(msg, "✓")
def _fail(msg: str) -> None: _log(msg, "✗")
def _info(msg: str) -> None: _log(msg, "→")

def _env_for_file(filename: str) -> str:
    for prefix, env in MACRO_ENV_MAP.items():
        if filename.lower().startswith(prefix):
            return env
    return "dev"


def _cert_details_from_pem(cert_pem: str) -> dict:
    """Extract X.509 metadata from a PEM certificate string."""
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa as _rsa, ec as _ec

        cert = x509.load_pem_x509_certificate(cert_pem.encode())
        fp = cert.fingerprint(hashes.SHA256())
        fp_str = ":".join(f"{b:02X}" for b in fp)

        pub_key = cert.public_key()
        if isinstance(pub_key, _rsa.RSAPublicKey):
            key_info = f"RSA-{pub_key.key_size}"
        elif isinstance(pub_key, _ec.EllipticCurvePublicKey):
            key_info = f"EC-{pub_key.curve.name}"
        else:
            key_info = "Unknown"

        return {
            "subject":          cert.subject.rfc4514_string(),
            "issuer":           cert.issuer.rfc4514_string(),
            "serial":           str(cert.serial_number),
            "not_valid_before": cert.not_valid_before_utc.isoformat(),
            "not_valid_after":  cert.not_valid_after_utc.isoformat(),
            "fingerprint_sha256": fp_str,
            "key_type":         key_info,
        }
    except ImportError:
        return {"note": "Install 'cryptography' for cert inspection"}
    except Exception as exc:
        return {"error": str(exc)}


def _verify_signature(file_bytes: bytes, signature_hex: str, cert_pem: str, algorithm: str) -> bool:
    """Locally verify RSA/ECDSA signature using the public key from the certificate."""
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding, rsa as _rsa, ec as _ec

        HASH_MAP = {
            "sha256": hashes.SHA256(),
            "sha384": hashes.SHA384(),
            "sha512": hashes.SHA512(),
        }
        hash_algo = HASH_MAP.get(algorithm, hashes.SHA256())
        sig_bytes = binascii.unhexlify(signature_hex)
        cert = x509.load_pem_x509_certificate(cert_pem.encode())
        pub_key = cert.public_key()

        if isinstance(pub_key, _rsa.RSAPublicKey):
            pub_key.verify(sig_bytes, file_bytes, padding.PKCS1v15(), hash_algo)
        elif isinstance(pub_key, _ec.EllipticCurvePublicKey):
            pub_key.verify(sig_bytes, file_bytes, _ec.ECDSA(hash_algo))
        else:
            return False
        return True
    except Exception:
        return False


# ─── API helpers ──────────────────────────────────────────────────────────────

class APIClient:
    def __init__(self, base_url: str) -> None:
        self.base = base_url.rstrip("/")
        self.token: Optional[str] = None
        self.session = requests.Session()
        # NOTE: do NOT set Content-Type at session level —
        # multipart file uploads need requests to set the boundary automatically.

    def _auth_header(self) -> dict:
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    def _json_headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        h.update(self._auth_header())
        return h

    def register(self, username: str, email: str, password: str, full_name: str) -> dict:
        r = self.session.post(
            f"{self.base}/api/v1/auth/register",
            json={"username": username, "email": email, "password": password, "full_name": full_name},
            headers={"Content-Type": "application/json"},
        )
        return r.json()

    def login(self, username: str, password: str) -> bool:
        r = self.session.post(
            f"{self.base}/api/v1/auth/login",
            json={"username": username, "password": password},
            headers={"Content-Type": "application/json"},
        )
        if r.status_code == 200:
            self.token = r.json()["access_token"]
            return True
        return False

    def create_api_key(self, name: str, expires_in_days: int = 90) -> dict:
        r = self.session.post(
            f"{self.base}/api/v1/auth/api-keys",
            json={"name": name, "expires_in_days": expires_in_days},
            headers=self._json_headers(),
        )
        return r.json() if r.status_code in (200, 201) else {}

    def snow_sign(self, file_path: Path, domain: str, algorithm: str,
                  requester_id: Optional[str] = None) -> dict:
        with open(file_path, "rb") as fh:
            r = self.session.post(
                f"{self.base}/api/v1/snow/sign",
                headers={k: v for k, v in self._auth_header().items()},
                files={"file": (file_path.name, fh, "application/octet-stream")},
                data={"algorithm": algorithm, "domain": domain,
                      **({"requester_id": requester_id} if requester_id else {})},
            )
        if r.status_code == 200:
            return r.json()
        return {"error": r.text, "status_code": r.status_code}

    def snow_verify(self, file_path: Path, signature: str, domain: str, algorithm: str) -> dict:
        with open(file_path, "rb") as fh:
            r = self.session.post(
                f"{self.base}/api/v1/snow/verify",
                headers={k: v for k, v in self._auth_header().items()},
                files={"file": (file_path.name, fh, "application/octet-stream")},
                data={"signature": signature, "algorithm": algorithm, "domain": domain},
            )
        return r.json() if r.status_code == 200 else {"error": r.text}

    def list_certs(self) -> list[str]:
        r = self.session.get(f"{self.base}/api/v1/snow/certs", headers=self._auth_header())
        return r.json().get("certificates", []) if r.status_code == 200 else []

    def health(self) -> bool:
        try:
            r = self.session.get(f"{self.base}/api/v1/health", timeout=5)
            return r.status_code == 200
        except Exception:
            return False


# ─── Report writer ────────────────────────────────────────────────────────────

def write_report(report: dict, input_file: Path) -> tuple[Path, Path]:
    """Write JSON and text reports to tests/output/report/."""
    stem = input_file.stem
    json_path = REPORT_DIR / f"{stem}_report.json"
    txt_path  = REPORT_DIR / f"{stem}_report.txt"

    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "=" * 70,
        f"  MACRO SIGNING REPORT",
        "=" * 70,
        "",
        "─── INPUT FILE ───────────────────────────────────────────────────────",
        f"  File name   : {report['input']['filename']}",
        f"  File size   : {report['input']['size_bytes']:,} bytes",
        f"  SHA-256     : {report['input']['sha256']}",
        f"  Environment : {report['environment']}",
        "",
        "─── SIGNING ──────────────────────────────────────────────────────────",
        f"  Domain      : {report['signing']['domain']}",
        f"  Algorithm   : {report['signing']['algorithm']}",
        f"  Signed at   : {report['signing']['signed_at']}",
        f"  Signature   : {report['signing']['signature'][:64]}…",
        f"  File hash   : {report['signing']['file_hash']}",
        "",
        "─── CERTIFICATE (PRIVATE KEY USED FOR SIGNING) ───────────────────────",
    ]

    cert = report.get("certificate", {})
    lines += [
        f"  Subject     : {cert.get('subject', '—')}",
        f"  Issuer      : {cert.get('issuer', '—')}",
        f"  Key type    : {cert.get('key_type', '—')}",
        f"  Valid from  : {cert.get('not_valid_before', '—')}",
        f"  Valid until : {cert.get('not_valid_after', '—')}",
        f"  Fingerprint : {cert.get('fingerprint_sha256', '—')}",
        "",
        "─── OUTPUT FILE ──────────────────────────────────────────────────────",
        f"  File name   : {report['output']['filename']}",
        f"  File size   : {report['output']['size_bytes']:,} bytes",
        f"  SHA-256     : {report['output']['sha256']}",
        "",
        "─── VERIFICATION (PUBLIC KEY) ────────────────────────────────────────",
        f"  API result  : {'✓ VALID' if report['verification']['api_valid'] else '✗ INVALID'}",
        f"  Local check : {'✓ VALID' if report['verification']['local_valid'] else '✗ INVALID'}",
        f"  Message     : {report['verification']['message']}",
        "",
        "=" * 70,
    ]

    txt_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, txt_path


# ─── Main runner ─────────────────────────────────────────────────────────────

def run(base_url: str, env_filter: Optional[str] = None) -> None:
    print()
    print("╔══════════════════════════════════════════════════╗")
    print("║   Macro Sign Service — Live Test Runner          ║")
    print("╚══════════════════════════════════════════════════╝")
    print(f"  Base URL : {base_url}")
    print(f"  Input    : {INPUT_DIR}")
    print(f"  Output   : {OUTPUT_DIR}")
    print(f"  Reports  : {REPORT_DIR}")
    print()

    # Ensure output dirs exist
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    client = APIClient(base_url)

    # ── 1. Health check ────────────────────────────────────────────────────────
    print("── Health Check ──────────────────────────────────────────────────────")
    if not client.health():
        _fail(f"API at {base_url} is not reachable. Is the service running?")
        sys.exit(1)
    _ok("API is healthy")
    print()

    # ── 2. Create / login users for each environment ───────────────────────────
    print("── User Setup ────────────────────────────────────────────────────────")
    tokens: dict[str, str] = {}
    api_keys: dict[str, str] = {}

    envs_to_run = [env_filter] if env_filter else list(ENVIRONMENTS.keys())

    for env_name in envs_to_run:
        cfg = ENVIRONMENTS[env_name]
        u   = cfg["user"]

        _info(f"[{env_name}] Registering user '{u['username']}'…")
        reg = client.register(u["username"], u["email"], u["password"], u["full_name"])
        if "id" in reg:
            _ok(f"[{env_name}] Created user {u['username']} (id={reg['id'][:8]}…)")
        elif "already" in str(reg).lower() or "exists" in str(reg).lower() or "unique" in str(reg).lower():
            _info(f"[{env_name}] User '{u['username']}' already exists — logging in")
        else:
            _info(f"[{env_name}] Register response: {reg}")

        if client.login(u["username"], u["password"]):
            tokens[env_name] = client.token  # type: ignore[assignment]
            _ok(f"[{env_name}] Logged in as '{u['username']}'")
        else:
            _fail(f"[{env_name}] Login failed for '{u['username']}'")
            continue

        # Create an API key for this environment
        key_resp = client.create_api_key(f"{env_name}-runner-key")
        if "api_key" in key_resp:
            api_keys[env_name] = key_resp["api_key"]
            _ok(f"[{env_name}] API key created: {key_resp['api_key'][:20]}…")
        elif "prefix" in key_resp:
            _ok(f"[{env_name}] API key prefix: {key_resp.get('prefix', '?')}")
    print()

    # ── 3. Discover input macros ────────────────────────────────────────────────
    print("── Input Macros ─────────────────────────────────────────────────────")
    input_files = sorted(INPUT_DIR.glob("*.*"))
    if not input_files:
        _fail(f"No files found in {INPUT_DIR}")
        sys.exit(1)

    for f in input_files:
        env = _env_for_file(f.name)
        _info(f"{f.name}  →  [{env}]  ({f.stat().st_size:,} bytes)")
    print()

    # ── 4. Sign each macro ─────────────────────────────────────────────────────
    print("── Signing ──────────────────────────────────────────────────────────")
    results: list[dict] = []

    for input_file in input_files:
        env_name = _env_for_file(input_file.name)
        if env_filter and env_name != env_filter:
            continue

        env_cfg = ENVIRONMENTS[env_name]
        domain    = env_cfg["domain"]
        algorithm = env_cfg["algorithm"]

        # Switch to the correct user's token
        if env_name in tokens:
            client.token = tokens[env_name]
        else:
            _fail(f"No token for env '{env_name}', skipping {input_file.name}")
            continue

        _info(f"Signing {input_file.name} [{env_name}] domain={domain} algo={algorithm}")

        # Read original bytes + compute hash
        file_bytes = input_file.read_bytes()
        input_sha256 = hashlib.sha256(file_bytes).hexdigest()

        sign_resp = client.snow_sign(
            input_file, domain=domain, algorithm=algorithm,
            requester_id=f"test-runner-{env_name}",
        )

        if "error" in sign_resp:
            _fail(f"  Signing FAILED: {sign_resp['error'][:120]}")
            results.append({"file": input_file.name, "env": env_name, "status": "failed", "error": sign_resp["error"]})
            continue

        # Save signed content (base64-decoded original — identical to input for VBA files)
        signed_bytes = base64.b64decode(sign_resp["signed_content_b64"])
        output_filename = f"{input_file.stem}_signed{input_file.suffix}"
        output_path = OUTPUT_DIR / output_filename
        output_path.write_bytes(signed_bytes)
        output_sha256 = hashlib.sha256(signed_bytes).hexdigest()

        # Verify via API
        verify_resp = client.snow_verify(
            input_file,
            signature=sign_resp["signature"],
            domain=domain,
            algorithm=algorithm,
        )
        api_valid = verify_resp.get("is_valid", False)

        # Verify locally using public key from cert PEM
        local_valid = _verify_signature(
            file_bytes, sign_resp["signature"], sign_resp["certificate_pem"], algorithm
        )

        # Extract cert details
        cert_details = _cert_details_from_pem(sign_resp["certificate_pem"])

        report: dict = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "environment":  env_name,
            "input": {
                "filename":   input_file.name,
                "size_bytes": len(file_bytes),
                "sha256":     input_sha256,
                "path":       str(input_file),
            },
            "signing": {
                "domain":     domain,
                "algorithm":  algorithm,
                "signed_at":  sign_resp.get("signed_at", ""),
                "signature":  sign_resp["signature"],
                "file_hash":  sign_resp["file_hash"],
                "cert_fingerprint": sign_resp["certificate_fingerprint"],
            },
            "certificate": {
                **cert_details,
                "subject_from_api": sign_resp.get("certificate_subject", ""),
                "pem_snippet":      sign_resp["certificate_pem"][:200] + "…",
            },
            "output": {
                "filename":   output_filename,
                "size_bytes": len(signed_bytes),
                "sha256":     output_sha256,
                "path":       str(output_path),
            },
            "verification": {
                "api_valid":   api_valid,
                "local_valid": local_valid,
                "message":     verify_resp.get("message", ""),
                "cert_subject": verify_resp.get("certificate_subject", ""),
                "cert_expiry":  verify_resp.get("certificate_expiry", ""),
            },
        }

        json_path, txt_path = write_report(report, input_file)
        results.append({"file": input_file.name, "env": env_name, "status": "ok",
                         "api_valid": api_valid, "local_valid": local_valid})

        valid_str = "✓ API + local verified" if (api_valid and local_valid) else "⚠ verification issue"
        _ok(f"  {input_file.name} → {output_filename}  [{valid_str}]")
        _info(f"  Report: {txt_path.name}")
    print()

    # ── 5. List final certificates in key store ────────────────────────────────
    print("── Certificates in Key Store ─────────────────────────────────────────")
    if tokens:
        client.token = list(tokens.values())[0]
        certs = client.list_certs()
        for c in certs:
            _info(c)
    print()

    # ── 6. Summary ─────────────────────────────────────────────────────────────
    print("── Summary ──────────────────────────────────────────────────────────")
    ok_count   = sum(1 for r in results if r["status"] == "ok")
    fail_count = sum(1 for r in results if r["status"] == "failed")
    print(f"  Files processed : {len(results)}")
    print(f"  Signed OK       : {ok_count}")
    print(f"  Failed          : {fail_count}")
    print(f"  Reports written : {REPORT_DIR}")
    print()

    if fail_count:
        print("  ⚠ Some files failed. Check errors above.")
        sys.exit(1)
    else:
        print("  All macros signed and verified successfully.")
    print()


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Macro Sign Service live test runner")
    parser.add_argument("--base-url", default="http://localhost:8000",
                        help="API base URL (default: http://localhost:8000)")
    parser.add_argument("--env", choices=["dev", "prod"],
                        help="Only run macros for this environment")
    args = parser.parse_args()
    run(args.base_url, env_filter=args.env)
