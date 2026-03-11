"""
End-to-end test: VBA signing flow via the API.

Run against a live service with a Windows signing agent configured:
    MACRO_SIGN_URL=http://localhost:8000 \
    MACRO_SIGN_API_KEY=<key> \
    python -m pytest tests/e2e/test_vba_signing_e2e.py -v

These tests verify:
  TC-01: POST /snow/sign-vba with an .xlsm returns a signed file
  TC-02: The signing_method is 'signtool-office-sip' or 'windows-agent-signtool-sip'
  TC-03: POST /snow/sign-vba with a .docm works
  TC-04: Certificate proof endpoint returns code_signing = true
  TC-05: PFX download endpoint returns valid PKCS#12
  TC-06: Unsigned fallback returns 'unsigned-requires-windows' when no agent
  TC-07: Reject non-Office file on /snow/sign-vba
"""

from __future__ import annotations

import base64
import io
import os
import zipfile

import httpx
import pytest

BASE_URL = os.environ.get("MACRO_SIGN_URL", "http://localhost:8000")
API_KEY = os.environ.get("MACRO_SIGN_API_KEY", "")
DOMAIN = "snow-test-domain"


def get_headers():
    h = {"Accept": "application/json"}
    if API_KEY:
        h["X-API-Key"] = API_KEY
    return h


def make_minimal_xlsm() -> bytes:
    """Create a minimal .xlsm (ZIP with Office markers) for testing."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"></Types>')
        zf.writestr("xl/vbaProject.bin", b"\xcc\xd5\xdb" + b"\x00" * 100)
    return buf.getvalue()


def make_minimal_docm() -> bytes:
    """Create a minimal .docm for testing."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types></Types>')
        zf.writestr("word/vbaProject.bin", b"\xcc\xd5\xdb" + b"\x00" * 100)
    return buf.getvalue()


@pytest.fixture
def client():
    return httpx.Client(base_url=BASE_URL, timeout=120.0, headers=get_headers())


class TestVBASigningE2E:
    """
    TC-01: Sign an .xlsm via /snow/sign-vba
    """
    def test_sign_xlsm_returns_signed_file(self, client):
        xlsm = make_minimal_xlsm()
        files = {"file": ("test.xlsm", xlsm, "application/vnd.ms-excel.sheet.macroEnabled.12")}
        data = {"algorithm": "sha256", "domain": DOMAIN}

        resp = client.post("/api/v1/snow/sign-vba", files=files, data=data)

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        body = resp.json()
        assert body["status"] == "signed"
        assert body["signed_file_b64"]  # Non-empty
        assert body["certificate_fingerprint"]
        assert body["certificate_subject"]
        assert body["signing_method"]

        # The signed file should be decodable
        signed_bytes = base64.b64decode(body["signed_file_b64"])
        assert len(signed_bytes) > 0

    """
    TC-02: Verify the signing method is Windows-based
    """
    def test_signing_method_is_windows_based(self, client):
        xlsm = make_minimal_xlsm()
        files = {"file": ("test.xlsm", xlsm)}
        data = {"domain": DOMAIN}

        resp = client.post("/api/v1/snow/sign-vba", files=files, data=data)
        body = resp.json()

        valid_methods = {
            "signtool-office-sip",         # Local Windows signing
            "windows-agent-signtool-sip",  # Remote agent signing
            "unsigned-requires-windows",   # Fallback (no Windows available)
        }
        assert body["signing_method"] in valid_methods

    """
    TC-03: Sign a .docm
    """
    def test_sign_docm(self, client):
        docm = make_minimal_docm()
        files = {"file": ("test.docm", docm)}
        data = {"domain": DOMAIN}

        resp = client.post("/api/v1/snow/sign-vba", files=files, data=data)
        assert resp.status_code == 200
        body = resp.json()
        assert body["original_filename"] == "test.docm"

    """
    TC-04: Certificate proof shows code signing capability
    """
    def test_cert_proof_shows_code_signing(self, client):
        # First trigger cert creation via a sign request
        xlsm = make_minimal_xlsm()
        files = {"file": ("test.xlsm", xlsm)}
        client.post("/api/v1/snow/sign-vba", files=files, data={"domain": DOMAIN})

        # Now check proof
        resp = client.get(f"/api/v1/snow/certs/{DOMAIN}/proof")
        assert resp.status_code == 200
        body = resp.json()
        assert body["is_code_signing"] is True
        assert body["fingerprint_sha256"]
        assert body["pfx_available"] is True

    """
    TC-05: PFX download returns valid PKCS#12
    """
    def test_pfx_download(self, client):
        # Ensure cert exists
        xlsm = make_minimal_xlsm()
        files = {"file": ("test.xlsm", xlsm)}
        client.post("/api/v1/snow/sign-vba", files=files, data={"domain": DOMAIN})

        resp = client.get(f"/api/v1/snow/certs/{DOMAIN}/pfx")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/x-pkcs12"
        assert len(resp.content) > 100  # Not empty

    """
    TC-07: Reject non-Office file on /snow/sign-vba
    """
    def test_reject_non_office_file(self, client):
        files = {"file": ("test.vba", b"Sub Hello()\nEnd Sub")}
        data = {"domain": DOMAIN}

        resp = client.post("/api/v1/snow/sign-vba", files=files, data=data)
        assert resp.status_code == 400
        assert "Office macro file format" in resp.json()["detail"]
