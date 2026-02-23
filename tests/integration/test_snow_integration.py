"""
ServiceNow (SNOW) Integration Tests
=====================================
Simulates the end-to-end scenario where a SNOW client:
  1. Sends a macro file to the signing API
  2. The API signs it with standard keys under the test domain
  3. The signed content (base64 + signature) is returned directly to the SNOW form
  4. The same user can verify the returned signature

All external dependencies (DB, Celery, real certs directory) are mocked so these
tests run without any infrastructure.  Real cryptography is used throughout so the
signing/verification math is genuine.

Test Scenarios
--------------
SNOW-001  Happy path – VBA file signed and signed_content_b64 returned to SNOW form
SNOW-002  Happy path – .bas file signed and returned
SNOW-003  Happy path – .cls file signed and returned
SNOW-004  Algorithm variants – sha256 / sha384 / sha512 all produce valid signatures
SNOW-005  Signed content round-trip – SNOW stores signature, later verifies the file
SNOW-006  User who sent the file is the one who receives and can verify the result
SNOW-007  requester_id is echoed in response (SNOW form tracking)
SNOW-008  Error – unsupported file extension (.py) is rejected
SNOW-009  Error – file too large is rejected
SNOW-010  Error – unauthenticated request returns 401
SNOW-011  Error – tampered file fails verification
SNOW-012  Error – tampered signature fails verification
SNOW-013  Keystore – /snow/certs lists available certificates
SNOW-014  Keystore – get_or_create provisions cert when absent
SNOW-015  Keystore – get_or_create returns existing cert without re-creating it
SNOW-016  Keystore – certificate rotation: new cert verifies; old signature fails
SNOW-017  SNOW form receives PEM cert in response for client-side verification
SNOW-018  Multiple files can be signed in sequence (stateless endpoint)
"""

from __future__ import annotations

import base64
import io
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers / sample content
# ---------------------------------------------------------------------------

SAMPLE_VBA = b"""\
Attribute VB_Name = "Module1"
Sub HelloWorld()
    MsgBox "Hello from SNOW!"
End Sub
"""

SAMPLE_BAS = b"""\
Attribute VB_Name = "BASModule"
Function Add(a As Integer, b As Integer) As Integer
    Add = a + b
End Function
"""

SAMPLE_CLS = b"""\
VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
END
Attribute VB_Name = "ClsModule"
Public Sub DoWork()
End Sub
"""

LARGE_VBA = b"' x" + b"A" * (51 * 1024 * 1024)  # 51 MB – exceeds 50 MB limit

DANGEROUS_VBA = b"""\
Attribute VB_Name = "BadMacro"
Sub RunCmd()
    Shell "cmd.exe /c whoami"
End Sub
"""


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def cert_dir(tmp_path_factory) -> Path:
    """Temp directory pre-populated with a real snow-test-domain certificate."""
    from src.core.signing_engine import create_self_signed_cert

    d = tmp_path_factory.mktemp("certs")
    cert_pem, key_pem = create_self_signed_cert(
        common_name="snow-test.macro-sign.local",
        organization="SNOW Test Domain",
        days_valid=365,
    )
    (d / "snow-test-domain.pem").write_bytes(cert_pem)
    (d / "snow-test-domain.key").write_bytes(key_pem)
    # Also write a "default" cert so the rest of the app doesn't break
    (d / "default.pem").write_bytes(cert_pem)
    (d / "default.key").write_bytes(key_pem)
    return d


@pytest.fixture(scope="module")
def snow_cert_store(cert_dir):
    """Real LocalCertificateStore backed by the temp cert directory."""
    from src.core.certificate_store import LocalCertificateStore

    return LocalCertificateStore(base_path=str(cert_dir))


@pytest.fixture(scope="module")
def mock_user():
    """Mock User with DEVELOPER role (has 'sign' and 'verify' permissions)."""
    from src.models.schemas import User, UserRole

    user = MagicMock(spec=User)
    user.id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    user.username = "snow-requester"
    user.email = "snow@example.com"
    user.role = UserRole.DEVELOPER
    user.is_active = True
    return user


@pytest.fixture(scope="module")
def mock_db() -> AsyncMock:
    """Mock async DB session – just accepts add/flush without touching a database."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture(scope="module")
def client(mock_user, mock_db, snow_cert_store) -> Generator[TestClient, None, None]:
    """
    Full TestClient with:
    - Auth bypassed (mock_user always returned)
    - DB bypassed (mock_db session)
    - LocalCertificateStore using the temp cert_dir
    """
    import os

    os.environ["APP_ENV"] = "testing"
    os.environ["APP_DEBUG"] = "true"
    os.environ["APP_SECRET_KEY"] = "test-secret-key"
    os.environ["JWT_SECRET_KEY"] = "test-jwt-secret"
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_snow.db"
    os.environ["CERT_STORE_BACKEND"] = "local"

    # Clear settings cache so env vars are picked up
    from src.config.settings import get_settings
    get_settings.cache_clear()

    from src.auth.dependencies import get_current_user
    from src.models.database import get_db

    async def _override_get_db():
        yield mock_db

    from src.main import create_app

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_db] = _override_get_db

    with patch(
        "src.core.certificate_store.get_certificate_store",
        return_value=snow_cert_store,
    ):
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c

    # Cleanup
    app.dependency_overrides.clear()
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------


def _snow_sign(client: TestClient, content: bytes, filename: str, **kwargs) -> dict:
    """POST /api/v1/snow/sign and return the parsed JSON response."""
    data = {"algorithm": kwargs.get("algorithm", "sha256")}
    if "domain" in kwargs:
        data["domain"] = kwargs["domain"]
    if "requester_id" in kwargs:
        data["requester_id"] = kwargs["requester_id"]
    if "table" in kwargs:
        data["table"] = kwargs["table"]

    resp = client.post(
        "/api/v1/snow/sign",
        files={"file": (filename, io.BytesIO(content), "application/octet-stream")},
        data=data,
    )
    return resp


def _snow_verify(
    client: TestClient,
    content: bytes,
    filename: str,
    signature: str,
    algorithm: str = "sha256",
    domain: str = "snow-test-domain",
) -> dict:
    """POST /api/v1/snow/verify and return the parsed JSON response."""
    return client.post(
        "/api/v1/snow/verify",
        files={"file": (filename, io.BytesIO(content), "application/octet-stream")},
        data={"signature": signature, "algorithm": algorithm, "domain": domain},
    )


# ===========================================================================
# SNOW-001 to SNOW-003 – Happy path, various file types
# ===========================================================================


class TestSNOWHappyPath:
    """SNOW-001 / 002 / 003: Happy-path sign scenarios for different file types."""

    @pytest.mark.parametrize(
        "filename,content",
        [
            ("macro.vba", SAMPLE_VBA),
            ("module.bas", SAMPLE_BAS),
            ("class.cls", SAMPLE_CLS),
        ],
    )
    def test_sign_returns_200_and_signed_status(
        self, client, filename, content
    ):
        """SNOW-001/002/003: API returns 200 with status=signed for supported file types."""
        resp = _snow_sign(client, content, filename)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "signed"

    @pytest.mark.parametrize(
        "filename,content",
        [
            ("macro.vba", SAMPLE_VBA),
            ("module.bas", SAMPLE_BAS),
            ("class.cls", SAMPLE_CLS),
        ],
    )
    def test_sign_response_fields_are_complete(self, client, filename, content):
        """All required response fields are present and non-empty."""
        body = _snow_sign(client, content, filename).json()
        assert body["original_filename"] == filename
        assert body["file_size"] == len(content)
        assert body["signature"]  # non-empty hex string
        assert body["file_hash"]
        assert body["certificate_fingerprint"]
        assert body["certificate_subject"]
        assert body["certificate_pem"].startswith("-----BEGIN CERTIFICATE-----")
        assert body["algorithm"] == "sha256"
        assert body["signed_at"]

    @pytest.mark.parametrize(
        "filename,content",
        [
            ("macro.vba", SAMPLE_VBA),
            ("module.bas", SAMPLE_BAS),
        ],
    )
    def test_signed_content_b64_decodes_to_original(self, client, filename, content):
        """signed_content_b64 can be base64-decoded back to the exact original bytes."""
        body = _snow_sign(client, content, filename).json()
        decoded = base64.b64decode(body["signed_content_b64"])
        assert decoded == content, "Decoded content must equal the original file bytes"


# ===========================================================================
# SNOW-004 – Algorithm variants
# ===========================================================================


class TestSNOWAlgorithms:
    """SNOW-004: sha256 / sha384 / sha512 all produce valid, distinct signatures."""

    @pytest.mark.parametrize("algorithm", ["sha256", "sha384", "sha512"])
    def test_algorithm_variants_succeed(self, client, algorithm):
        """Each supported algorithm produces a signed response."""
        resp = _snow_sign(client, SAMPLE_VBA, "macro.vba", algorithm=algorithm)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["algorithm"] == algorithm
        assert len(body["signature"]) > 0

    def test_different_algorithms_produce_different_signatures(self, client):
        """sha256 and sha512 produce different signatures for the same file."""
        sig256 = _snow_sign(client, SAMPLE_VBA, "macro.vba", algorithm="sha256").json()["signature"]
        sig512 = _snow_sign(client, SAMPLE_VBA, "macro.vba", algorithm="sha512").json()["signature"]
        assert sig256 != sig512


# ===========================================================================
# SNOW-005 / 006 – Round-trip: sign then verify (same user flow)
# ===========================================================================


class TestSNOWRoundTrip:
    """SNOW-005/006: File signed by the service can be verified by the same SNOW user."""

    def test_signed_vba_verifies_successfully(self, client):
        """SNOW-005: signature from /snow/sign is accepted by /snow/verify."""
        sign_body = _snow_sign(
            client, SAMPLE_VBA, "macro.vba", requester_id="sys_snow_user_001"
        ).json()
        assert sign_body["status"] == "signed"

        verify_resp = _snow_verify(
            client,
            SAMPLE_VBA,
            "macro.vba",
            signature=sign_body["signature"],
        )
        assert verify_resp.status_code == 200, verify_resp.text
        verify_body = verify_resp.json()
        assert verify_body["is_valid"] is True
        assert "valid" in verify_body["message"].lower()

    def test_requester_id_echoed_in_sign_response(self, client):
        """SNOW-007: requester_id passed by the SNOW form is echoed in the response."""
        snow_sys_id = "sys_u_ab12cd34ef56"
        body = _snow_sign(
            client, SAMPLE_VBA, "macro.vba", requester_id=snow_sys_id
        ).json()
        assert body["requester_id"] == snow_sys_id

    def test_same_user_sign_and_verify_flow(self, client):
        """
        SNOW-006: Full SNOW form flow – user submits file, API signs it,
        SNOW stores the result, user later verifies the macro from SNOW.
        """
        # Step 1: SNOW form submits file on behalf of the user
        sign_resp = _snow_sign(
            client,
            SAMPLE_BAS,
            "module.bas",
            requester_id="sys_dev_user_42",
            table="sys_script_include",
        )
        assert sign_resp.status_code == 200
        sign_data = sign_resp.json()

        # Step 2: SNOW stores signed_content_b64 and signature in a field
        stored_content_b64 = sign_data["signed_content_b64"]
        stored_signature = sign_data["signature"]
        stored_algorithm = sign_data["algorithm"]

        # Step 3: Later, user wants to verify the macro from the SNOW form
        file_to_verify = base64.b64decode(stored_content_b64)
        verify_resp = _snow_verify(
            client,
            file_to_verify,
            "module.bas",
            signature=stored_signature,
            algorithm=stored_algorithm,
        )
        assert verify_resp.status_code == 200
        verify_data = verify_resp.json()
        assert verify_data["is_valid"] is True
        assert verify_data["certificate_subject"] is not None

    @pytest.mark.parametrize("algorithm", ["sha256", "sha384", "sha512"])
    def test_round_trip_all_algorithms(self, client, algorithm):
        """SNOW-005 extended: sign + verify round-trip passes for all algorithms."""
        sign_body = _snow_sign(
            client, SAMPLE_VBA, "macro.vba", algorithm=algorithm
        ).json()
        verify_resp = _snow_verify(
            client,
            SAMPLE_VBA,
            "macro.vba",
            signature=sign_body["signature"],
            algorithm=algorithm,
        )
        assert verify_resp.json()["is_valid"] is True


# ===========================================================================
# SNOW-008 / 009 – Error: invalid input
# ===========================================================================


class TestSNOWInputValidation:
    """SNOW-008/009: API rejects invalid file types and oversized files."""

    @pytest.mark.parametrize(
        "bad_filename",
        ["script.py", "program.exe", "doc.docx", "data.csv", "archive.zip"],
    )
    def test_unsupported_extension_returns_400(self, client, bad_filename):
        """SNOW-008: Files with unsupported extensions are rejected with 400."""
        resp = _snow_sign(client, b"some content", bad_filename)
        assert resp.status_code == 400, f"Expected 400 for {bad_filename}, got {resp.status_code}"
        assert "extension" in resp.json().get("detail", "").lower() or resp.status_code == 400

    def test_large_file_returns_400(self, client):
        """SNOW-009: Files exceeding 50 MB are rejected with 400."""
        resp = _snow_sign(client, LARGE_VBA, "large.vba")
        assert resp.status_code == 400, resp.text

    def test_empty_file_returns_400(self, client):
        """Empty files are rejected by the validator with 400 (FileValidator._validate_not_empty)."""
        resp = _snow_sign(client, b"", "empty.vba")
        assert resp.status_code == 400
        assert "empty" in resp.json().get("detail", "").lower()


# ===========================================================================
# SNOW-010 – Authentication
# ===========================================================================


class TestSNOWAuthentication:
    """SNOW-010: Unauthenticated requests are rejected."""

    def test_unauthenticated_sign_returns_401(self):
        """SNOW-010: Without auth headers, the sign endpoint returns 401."""
        import os
        os.environ["APP_ENV"] = "testing"
        os.environ["APP_SECRET_KEY"] = "test-secret-key"
        os.environ["JWT_SECRET_KEY"] = "test-jwt-secret"
        os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_snow_auth.db"
        os.environ["CERT_STORE_BACKEND"] = "local"

        from src.config.settings import get_settings
        get_settings.cache_clear()

        from src.main import create_app
        app = create_app()
        # No dependency overrides — real auth will reject missing credentials

        mock_db_local = AsyncMock()
        mock_db_local.add = MagicMock()
        mock_db_local.flush = AsyncMock()
        mock_db_local.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

        from src.models.database import get_db

        async def _db():
            yield mock_db_local

        app.dependency_overrides[get_db] = _db

        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.post(
                "/api/v1/snow/sign",
                files={"file": ("macro.vba", io.BytesIO(SAMPLE_VBA), "application/octet-stream")},
                data={"algorithm": "sha256"},
            )
        assert resp.status_code == 401
        get_settings.cache_clear()


# ===========================================================================
# SNOW-011 / 012 – Tampered content / signature
# ===========================================================================


class TestSNOWTamperDetection:
    """SNOW-011/012: Tampered files and signatures are rejected by verify."""

    def test_tampered_file_fails_verification(self, client):
        """SNOW-011: Modifying file content after signing invalidates the signature."""
        sign_body = _snow_sign(client, SAMPLE_VBA, "macro.vba").json()
        original_sig = sign_body["signature"]

        tampered_content = SAMPLE_VBA + b"\n' tampered line"
        verify_resp = _snow_verify(
            client, tampered_content, "macro.vba", signature=original_sig
        )
        assert verify_resp.status_code == 200
        assert verify_resp.json()["is_valid"] is False

    def test_tampered_signature_fails_verification(self, client):
        """SNOW-012: Corrupted signature hex is rejected."""
        sign_body = _snow_sign(client, SAMPLE_VBA, "macro.vba").json()
        # Flip the last byte of the hex signature
        original_sig = sign_body["signature"]
        bad_sig = original_sig[:-2] + (
            "00" if original_sig[-2:] != "00" else "ff"
        )
        verify_resp = _snow_verify(client, SAMPLE_VBA, "macro.vba", signature=bad_sig)
        assert verify_resp.status_code == 200
        assert verify_resp.json()["is_valid"] is False

    def test_invalid_hex_signature_returns_400(self, client):
        """Non-hex signature string returns 400 Bad Request."""
        verify_resp = _snow_verify(
            client, SAMPLE_VBA, "macro.vba", signature="not-valid-hex!!"
        )
        assert verify_resp.status_code == 400


# ===========================================================================
# SNOW-013 – Key store listing
# ===========================================================================


class TestSNOWCertListing:
    """SNOW-013: GET /snow/certs lists available certificates."""

    def test_list_certs_returns_200(self, client):
        """SNOW-013: /snow/certs returns 200 with a list of certificate names."""
        resp = client.get("/api/v1/snow/certs")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "certificates" in body
        assert "count" in body
        assert isinstance(body["certificates"], list)

    def test_list_certs_includes_test_domain(self, client):
        """SNOW-013: The snow-test-domain certificate appears in the list."""
        body = client.get("/api/v1/snow/certs").json()
        assert "snow-test-domain" in body["certificates"]

    def test_list_certs_count_matches_list_length(self, client):
        """SNOW-013: count field equals len(certificates)."""
        body = client.get("/api/v1/snow/certs").json()
        assert body["count"] == len(body["certificates"])


# ===========================================================================
# SNOW-014 / 015 – Key store: get_or_create
# ===========================================================================


class TestKeystoreGetOrCreate:
    """SNOW-014/015: get_or_create_certificate provisions or reuses certs."""

    @pytest.mark.asyncio
    async def test_get_or_create_provisions_missing_cert(self, tmp_path):
        """SNOW-014: get_or_create creates a new cert when the name doesn't exist."""
        from src.core.certificate_store import LocalCertificateStore, CertificateStoreError

        store = LocalCertificateStore(base_path=str(tmp_path))
        name = "brand-new-domain"

        # Cert should not exist yet
        with pytest.raises(CertificateStoreError):
            await store.get_certificate(name)

        cert_info = await store.get_or_create_certificate(
            name,
            common_name="brand-new.local",
            organization="Test Org",
            days_valid=30,
        )
        assert cert_info.name == name
        assert cert_info.certificate_pem
        assert cert_info.private_key_pem

        # Confirm it's now on disk
        assert (tmp_path / f"{name}.pem").exists()
        assert (tmp_path / f"{name}.key").exists()

    @pytest.mark.asyncio
    async def test_get_or_create_returns_existing_cert_without_overwrite(
        self, tmp_path
    ):
        """SNOW-015: get_or_create returns the existing cert without re-generating it."""
        from src.core.certificate_store import LocalCertificateStore

        store = LocalCertificateStore(base_path=str(tmp_path))
        name = "existing-domain"

        # First call: creates the cert
        first = await store.get_or_create_certificate(
            name, common_name="existing.local", organization="Test"
        )

        # Second call: must return the same cert (same fingerprint)
        second = await store.get_or_create_certificate(
            name, common_name="different-cn-ignored.local", organization="Ignored"
        )

        assert first.certificate_pem == second.certificate_pem, (
            "get_or_create must not overwrite an existing certificate"
        )

    @pytest.mark.asyncio
    async def test_get_or_create_metadata_marks_auto_generated(self, tmp_path):
        """SNOW-014: auto-created certs have auto_generated=True in metadata."""
        from src.core.certificate_store import LocalCertificateStore

        store = LocalCertificateStore(base_path=str(tmp_path))
        cert_info = await store.get_or_create_certificate(
            "auto-cert",
            common_name="auto.local",
            organization="Auto Org",
        )
        assert cert_info.metadata.get("auto_generated") is True
        assert cert_info.metadata.get("purpose") == "test"


# ===========================================================================
# SNOW-016 – Certificate rotation
# ===========================================================================


class TestKeystoreRotation:
    """SNOW-016: After rotation, new cert verifies; old signature no longer valid."""

    @pytest.mark.asyncio
    async def test_rotation_invalidates_old_signature(self, tmp_path):
        """SNOW-016: Signature made with old key fails after cert rotation."""
        from src.core.certificate_store import LocalCertificateStore
        from src.core.signing_engine import SigningEngine, create_self_signed_cert

        store = LocalCertificateStore(base_path=str(tmp_path))

        # Generate two distinct certs (old and new)
        old_cert_pem, old_key_pem = create_self_signed_cert(
            common_name="old-cert.local", organization="Old"
        )
        new_cert_pem, new_key_pem = create_self_signed_cert(
            common_name="new-cert.local", organization="New"
        )

        await store.store_certificate("domain-a", old_cert_pem, old_key_pem)

        # Sign with old key
        old_info = await store.get_certificate("domain-a")
        engine_old = SigningEngine(
            private_key_pem=old_info.private_key_pem,
            certificate_pem=old_info.certificate_pem,
        )
        result_old = engine_old.sign(SAMPLE_VBA)

        # Rotate to new cert
        await store.rotate_certificate("domain-a", new_cert_pem, new_key_pem)

        # Verify with new (rotated) cert — old signature should be invalid
        new_info = await store.get_certificate("domain-a")
        engine_new = SigningEngine(certificate_pem=new_info.certificate_pem)
        verify_result = engine_new.verify(SAMPLE_VBA, result_old.signature)
        assert verify_result.is_valid is False, (
            "Old signature must be invalid after certificate rotation"
        )

    @pytest.mark.asyncio
    async def test_rotation_backup_file_created(self, tmp_path):
        """SNOW-016: Rotating a local cert creates a timestamped backup."""
        from src.core.certificate_store import LocalCertificateStore
        from src.core.signing_engine import create_self_signed_cert

        store = LocalCertificateStore(base_path=str(tmp_path))
        cert1, key1 = create_self_signed_cert(common_name="before.local")
        cert2, key2 = create_self_signed_cert(common_name="after.local")

        await store.store_certificate("rotating-cert", cert1, key1)
        await store.rotate_certificate("rotating-cert", cert2, key2)

        # At least one backup .pem should exist
        backups = list(tmp_path.glob("rotating-cert.backup.*.pem"))
        assert len(backups) == 1, "Exactly one backup should be created on rotation"


# ===========================================================================
# SNOW-017 – Certificate PEM in response
# ===========================================================================


class TestSNOWCertPEMInResponse:
    """SNOW-017: The response includes the public cert PEM for client-side verification."""

    def test_sign_response_includes_valid_cert_pem(self, client):
        """SNOW-017: certificate_pem in response is a valid PEM X.509 certificate."""
        from cryptography import x509

        body = _snow_sign(client, SAMPLE_VBA, "macro.vba").json()
        cert_pem = body["certificate_pem"].encode()
        # Should parse without raising
        cert = x509.load_pem_x509_certificate(cert_pem)
        assert cert is not None

    def test_cert_subject_matches_test_domain(self, client):
        """SNOW-017: Certificate subject CN matches the SNOW test domain."""
        body = _snow_sign(client, SAMPLE_VBA, "macro.vba").json()
        assert "snow-test.macro-sign.local" in body["certificate_subject"]

    def test_cert_pem_can_be_used_to_verify_signature(self, client):
        """SNOW-017: The PEM cert returned by sign can independently verify the signature."""
        from src.core.signing_engine import SigningEngine

        body = _snow_sign(client, SAMPLE_VBA, "macro.vba").json()
        cert_pem = body["certificate_pem"].encode()
        sig_bytes = bytes.fromhex(body["signature"])
        algorithm = body["algorithm"]

        engine = SigningEngine(certificate_pem=cert_pem)
        result = engine.verify(SAMPLE_VBA, sig_bytes, algorithm=algorithm)
        assert result.is_valid is True


# ===========================================================================
# SNOW-018 – Sequential / stateless signing
# ===========================================================================


class TestSNOWSequentialSigning:
    """SNOW-018: Multiple independent files can be signed in sequence."""

    def test_multiple_files_signed_sequentially(self, client):
        """SNOW-018: Each successive sign call is independent and produces valid signatures."""
        files = [
            ("file1.vba", SAMPLE_VBA),
            ("file2.bas", SAMPLE_BAS),
            ("file3.cls", SAMPLE_CLS),
        ]
        signed = []
        for filename, content in files:
            body = _snow_sign(client, content, filename).json()
            assert body["status"] == "signed"
            signed.append((content, body))

        # All signatures are distinct (different content)
        sigs = [s[1]["signature"] for s in signed]
        assert len(set(sigs)) == len(sigs), "Each file must produce a unique signature"

    def test_same_file_signed_twice_yields_same_hash(self, client):
        """Signing the same file twice yields the same file_hash (deterministic hash)."""
        b1 = _snow_sign(client, SAMPLE_VBA, "macro.vba").json()
        b2 = _snow_sign(client, SAMPLE_VBA, "macro.vba").json()
        assert b1["file_hash"] == b2["file_hash"]


# ===========================================================================
# Keystore – LocalCertificateStore unit-level tests
# ===========================================================================


class TestLocalCertificateStoreOps:
    """Additional unit-level coverage for LocalCertificateStore CRUD operations."""

    @pytest.mark.asyncio
    async def test_store_and_retrieve_certificate(self, tmp_path):
        """store_certificate followed by get_certificate returns the same PEM."""
        from src.core.certificate_store import LocalCertificateStore
        from src.core.signing_engine import create_self_signed_cert

        store = LocalCertificateStore(base_path=str(tmp_path))
        cert_pem, key_pem = create_self_signed_cert(common_name="store-test.local")
        await store.store_certificate("my-cert", cert_pem, key_pem, {"env": "test"})

        info = await store.get_certificate("my-cert")
        assert info.certificate_pem == cert_pem
        assert info.private_key_pem == key_pem
        assert info.metadata["env"] == "test"

    @pytest.mark.asyncio
    async def test_list_certificates_after_store(self, tmp_path):
        """list_certificates returns names of stored certs."""
        from src.core.certificate_store import LocalCertificateStore
        from src.core.signing_engine import create_self_signed_cert

        store = LocalCertificateStore(base_path=str(tmp_path))
        c1, k1 = create_self_signed_cert(common_name="list-a.local")
        c2, k2 = create_self_signed_cert(common_name="list-b.local")
        await store.store_certificate("list-a", c1, k1)
        await store.store_certificate("list-b", c2, k2)

        names = await store.list_certificates()
        assert "list-a" in names
        assert "list-b" in names

    @pytest.mark.asyncio
    async def test_delete_certificate(self, tmp_path):
        """delete_certificate removes all files; subsequent get raises."""
        from src.core.certificate_store import (
            CertificateStoreError,
            LocalCertificateStore,
        )
        from src.core.signing_engine import create_self_signed_cert

        store = LocalCertificateStore(base_path=str(tmp_path))
        c, k = create_self_signed_cert(common_name="delete-me.local")
        await store.store_certificate("delete-me", c, k)
        await store.delete_certificate("delete-me")

        with pytest.raises(CertificateStoreError):
            await store.get_certificate("delete-me")

    @pytest.mark.asyncio
    async def test_get_nonexistent_certificate_raises(self, tmp_path):
        """Requesting a certificate that doesn't exist raises CertificateStoreError."""
        from src.core.certificate_store import (
            CertificateStoreError,
            LocalCertificateStore,
        )

        store = LocalCertificateStore(base_path=str(tmp_path))
        with pytest.raises(CertificateStoreError, match="not found"):
            await store.get_certificate("does-not-exist")
