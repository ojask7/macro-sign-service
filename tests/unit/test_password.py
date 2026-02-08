"""
Unit tests for password hashing.
"""

import pytest

from src.auth.password import hash_password, verify_password


class TestPasswordHashing:
    """Tests for password hashing and verification."""

    def test_hash_and_verify(self):
        password = "secure_password_123"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_wrong_password(self):
        hashed = hash_password("correct_password")
        assert verify_password("wrong_password", hashed) is False

    def test_different_hashes_same_password(self):
        """Bcrypt generates different hashes for same password (salt)."""
        password = "test_password"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        assert hash1 != hash2
        # But both should verify correctly
        assert verify_password(password, hash1) is True
        assert verify_password(password, hash2) is True

    def test_empty_password(self):
        hashed = hash_password("")
        assert verify_password("", hashed) is True
        assert verify_password("not_empty", hashed) is False

    def test_long_password(self):
        password = "a" * 200
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_special_characters(self):
        password = "p@$$w0rd!#%^&*()"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True
