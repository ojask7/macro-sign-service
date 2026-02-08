"""
Unit tests for JWT token handling.
"""

import pytest
from datetime import datetime, timezone

from src.auth.jwt_handler import (
    AuthenticationError,
    create_access_token,
    create_refresh_token,
    generate_api_key,
    verify_api_key,
    verify_token,
)


class TestAccessToken:
    """Tests for access token creation and verification."""

    def test_create_and_verify(self):
        token = create_access_token("user-123", "developer")
        payload = verify_token(token, token_type="access")
        assert payload["sub"] == "user-123"
        assert payload["role"] == "developer"
        assert payload["type"] == "access"

    def test_token_with_additional_claims(self):
        token = create_access_token(
            "user-123", "admin", additional_claims={"team_id": "team-456"}
        )
        payload = verify_token(token, token_type="access")
        assert payload["team_id"] == "team-456"

    def test_invalid_token(self):
        with pytest.raises(AuthenticationError, match="Invalid token"):
            verify_token("invalid.token.here")

    def test_wrong_token_type(self):
        token = create_access_token("user-123", "developer")
        with pytest.raises(AuthenticationError, match="Invalid token type"):
            verify_token(token, token_type="refresh")


class TestRefreshToken:
    """Tests for refresh token creation and verification."""

    def test_create_and_verify(self):
        token = create_refresh_token("user-123")
        payload = verify_token(token, token_type="refresh")
        assert payload["sub"] == "user-123"
        assert payload["type"] == "refresh"

    def test_refresh_token_not_valid_as_access(self):
        token = create_refresh_token("user-123")
        with pytest.raises(AuthenticationError, match="Invalid token type"):
            verify_token(token, token_type="access")


class TestAPIKey:
    """Tests for API key generation and verification."""

    def test_generate_api_key(self):
        full_key, prefix, key_hash = generate_api_key()
        assert full_key.startswith("mss_")
        assert len(prefix) == 10
        assert len(key_hash) == 64  # SHA-256 hex

    def test_verify_api_key(self):
        full_key, prefix, key_hash = generate_api_key()
        computed_hash = verify_api_key(full_key)
        assert computed_hash == key_hash

    def test_different_keys_different_hashes(self):
        _, _, hash1 = generate_api_key()
        _, _, hash2 = generate_api_key()
        assert hash1 != hash2

    def test_api_key_prefix_consistency(self):
        full_key, prefix, _ = generate_api_key()
        assert full_key[:10] == prefix
