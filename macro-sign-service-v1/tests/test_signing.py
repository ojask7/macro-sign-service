"""Signing engine tests.

Office file tests require signtool.exe + Office SIP — they are skipped on
non-Windows platforms. Text macro RSA signing works everywhere.
"""

from __future__ import annotations

import platform
import sys

import pytest

from app.certs import create_code_signing_pfx
from app.signing import (
    SigningError,
    find_signtool,
    sign_office_file,
    sign_text_macro,
    verify_file,
)

needs_signtool = pytest.mark.skipif(
    platform.system() != "Windows" or find_signtool() is None,
    reason="Requires Windows + signtool.exe",
)


# ---------------------------------------------------------------------------
# signtool discovery
# ---------------------------------------------------------------------------


class TestFindSigntool:
    def test_returns_str_or_none(self):
        result = find_signtool()
        assert result is None or isinstance(result, str)

    @needs_signtool
    def test_finds_signtool_on_windows(self):
        assert find_signtool() is not None


# ---------------------------------------------------------------------------
# Text macro RSA signing (works on all platforms)
# ---------------------------------------------------------------------------


class TestSignTextMacro:
    @pytest.fixture
    def pfx_bytes(self) -> bytes:
        pfx, _, _ = create_code_signing_pfx()
        return pfx

    async def test_sign_vba_content(self, pfx_bytes, sample_vba_content):
        original, signature, metadata = await sign_text_macro(
            content=sample_vba_content,
            pfx_bytes=pfx_bytes,
        )
        assert original == sample_vba_content
        assert len(signature) > 0
        assert metadata["signing_method"] == "rsa-detached"
        assert "certificate_fingerprint" in metadata
        assert "signed_at" in metadata

    async def test_sign_sha384(self, pfx_bytes, sample_vba_content):
        _, signature, metadata = await sign_text_macro(
            content=sample_vba_content,
            pfx_bytes=pfx_bytes,
            hash_algorithm="SHA384",
        )
        assert metadata["hash_algorithm"] == "SHA384"
        assert len(signature) > 0

    async def test_sign_sha512(self, pfx_bytes, sample_vba_content):
        _, signature, metadata = await sign_text_macro(
            content=sample_vba_content,
            pfx_bytes=pfx_bytes,
            hash_algorithm="SHA512",
        )
        assert metadata["hash_algorithm"] == "SHA512"

    async def test_signature_verifiable(self, pfx_bytes, sample_vba_content):
        """Verify the RSA signature is correct using the public key."""
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.primitives.serialization import pkcs12

        original, signature, _ = await sign_text_macro(
            content=sample_vba_content,
            pfx_bytes=pfx_bytes,
        )

        # Extract public key from PFX
        _, cert, _ = pkcs12.load_key_and_certificates(pfx_bytes, None)
        public_key = cert.public_key()

        # Verify — should not raise
        public_key.verify(
            signature,
            original,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )


# ---------------------------------------------------------------------------
# Office file signing (Windows + signtool only)
# ---------------------------------------------------------------------------


@needs_signtool
class TestSignOfficeFile:
    @pytest.fixture
    def pfx_bytes(self) -> bytes:
        pfx, _, _ = create_code_signing_pfx()
        return pfx

    async def test_sign_xlsm(self, pfx_bytes, minimal_xlsm):
        signed, metadata = await sign_office_file(
            file_bytes=minimal_xlsm,
            filename="test.xlsm",
            pfx_bytes=pfx_bytes,
        )
        assert len(signed) > 0
        assert metadata["signing_method"] == "signtool-office-sip"

    async def test_sign_docm(self, pfx_bytes, minimal_docm):
        signed, metadata = await sign_office_file(
            file_bytes=minimal_docm,
            filename="test.docm",
            pfx_bytes=pfx_bytes,
        )
        assert len(signed) > 0

    async def test_sign_sha384(self, pfx_bytes, minimal_xlsm):
        signed, metadata = await sign_office_file(
            file_bytes=minimal_xlsm,
            filename="test.xlsm",
            pfx_bytes=pfx_bytes,
            hash_algorithm="SHA384",
        )
        assert metadata["hash_algorithm"] == "SHA384"

    async def test_verify_signed_file(self, pfx_bytes, minimal_xlsm):
        signed, _ = await sign_office_file(
            file_bytes=minimal_xlsm,
            filename="test.xlsm",
            pfx_bytes=pfx_bytes,
        )
        result = await verify_file(signed, "test.xlsm")
        assert isinstance(result["valid"], bool)
