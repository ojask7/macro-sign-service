"""API integration tests."""

from __future__ import annotations

import io
import platform

import pytest

from app.signing import find_signtool

needs_signtool = pytest.mark.skipif(
    platform.system() != "Windows" or find_signtool() is None,
    reason="Requires Windows + signtool.exe",
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class TestHealth:
    async def test_health_returns_json(self, client):
        resp = await client.get("/api/v1/health")
        data = resp.json()
        assert "status" in data
        assert "platform" in data
        assert "signing_ready" in data
        assert "certificates_loaded" in data


# ---------------------------------------------------------------------------
# Certs
# ---------------------------------------------------------------------------


class TestCerts:
    async def test_list_certs(self, client):
        resp = await client.get("/api/v1/certs")
        assert resp.status_code == 200
        data = resp.json()
        assert "certificates" in data
        assert len(data["certificates"]) >= 1

    async def test_get_cert_default(self, client):
        resp = await client.get("/api/v1/certs/default")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_code_signing"] is True

    async def test_get_cert_not_found(self, client):
        resp = await client.get("/api/v1/certs/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Sign — text macros (works on all platforms)
# ---------------------------------------------------------------------------


class TestSignTextMacro:
    async def test_sign_vba(self, client, sample_vba_content):
        resp = await client.post(
            "/api/v1/sign",
            files={"file": ("macro.vba", io.BytesIO(sample_vba_content), "application/octet-stream")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["signing_method"] == "rsa-detached"
        assert "signature_b64" in data
        assert "certificate_fingerprint" in data

    async def test_sign_bas(self, client, sample_vba_content):
        resp = await client.post(
            "/api/v1/sign",
            files={"file": ("module.bas", io.BytesIO(sample_vba_content), "application/octet-stream")},
        )
        assert resp.status_code == 200
        assert resp.json()["signing_method"] == "rsa-detached"

    async def test_sign_with_algorithm(self, client, sample_vba_content):
        resp = await client.post(
            "/api/v1/sign?algorithm=SHA512",
            files={"file": ("macro.vba", io.BytesIO(sample_vba_content), "application/octet-stream")},
        )
        assert resp.status_code == 200
        assert resp.json()["algorithm"] == "SHA512"

    async def test_sign_with_requester_id(self, client, sample_vba_content):
        resp = await client.post(
            "/api/v1/sign?requester_id=SNOW-12345",
            files={"file": ("macro.vba", io.BytesIO(sample_vba_content), "application/octet-stream")},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Sign — Office files (Windows + signtool only)
# ---------------------------------------------------------------------------


@needs_signtool
class TestSignOfficeFile:
    async def test_sign_xlsm(self, client, minimal_xlsm):
        resp = await client.post(
            "/api/v1/sign",
            files={"file": ("report.xlsm", io.BytesIO(minimal_xlsm), "application/octet-stream")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["signing_method"] == "signtool-office-sip"
        assert "file_b64" in data

    async def test_sign_docm(self, client, minimal_docm):
        resp = await client.post(
            "/api/v1/sign",
            files={"file": ("doc.docm", io.BytesIO(minimal_docm), "application/octet-stream")},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


class TestValidationErrors:
    async def test_empty_file(self, client):
        resp = await client.post(
            "/api/v1/sign",
            files={"file": ("empty.xlsm", io.BytesIO(b""), "application/octet-stream")},
        )
        assert resp.status_code == 400
        assert "empty" in resp.json()["detail"].lower()

    async def test_disallowed_extension(self, client):
        resp = await client.post(
            "/api/v1/sign",
            files={"file": ("bad.exe", io.BytesIO(b"MZ..."), "application/octet-stream")},
        )
        assert resp.status_code == 400
        assert "not allowed" in resp.json()["detail"].lower()

    async def test_path_traversal(self, client):
        resp = await client.post(
            "/api/v1/sign",
            files={"file": ("../etc/passwd.xlsm", io.BytesIO(b"x" * 100), "application/octet-stream")},
        )
        assert resp.status_code == 400

    async def test_cert_not_found(self, client, sample_vba_content):
        resp = await client.post(
            "/api/v1/sign?cert_name=nonexistent",
            files={"file": ("macro.vba", io.BytesIO(sample_vba_content), "application/octet-stream")},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class TestAuth:
    async def test_no_auth_when_disabled(self, client, sample_vba_content):
        """With MACRO_SIGN_API_KEY empty, all requests pass."""
        resp = await client.post(
            "/api/v1/sign",
            files={"file": ("macro.vba", io.BytesIO(sample_vba_content), "application/octet-stream")},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


class TestAudit:
    async def test_audit_returns_logs(self, client, sample_vba_content):
        # Do a sign to generate audit entry
        await client.post(
            "/api/v1/sign",
            files={"file": ("macro.vba", io.BytesIO(sample_vba_content), "application/octet-stream")},
        )

        resp = await client.get("/api/v1/audit")
        assert resp.status_code == 200
        data = resp.json()
        assert "logs" in data
        assert "count" in data

    async def test_audit_with_filters(self, client):
        resp = await client.get("/api/v1/audit?action=sign&limit=10")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------


@needs_signtool
class TestVerify:
    async def test_verify_unsigned_file(self, client, minimal_xlsm):
        resp = await client.post(
            "/api/v1/verify",
            files={"file": ("test.xlsm", io.BytesIO(minimal_xlsm), "application/octet-stream")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "valid" in data


# ---------------------------------------------------------------------------
# Root
# ---------------------------------------------------------------------------


class TestRoot:
    async def test_root(self, client):
        resp = await client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "macro-sign-service"
        assert "version" in data
