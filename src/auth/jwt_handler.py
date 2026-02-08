"""
JWT token creation and verification.
"""

from __future__ import annotations

import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from jose import JWTError, jwt

from src.config.logging import get_logger
from src.config.settings import get_settings

logger = get_logger(__name__)


class AuthenticationError(Exception):
    """Raised when authentication fails."""

    pass


def create_access_token(
    subject: str,
    role: str,
    additional_claims: Optional[dict[str, Any]] = None,
) -> str:
    """Create a JWT access token."""
    settings = get_settings()
    expires_delta = timedelta(minutes=settings.jwt.access_token_expire_minutes)
    expire = datetime.now(timezone.utc) + expires_delta

    payload = {
        "sub": subject,
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }

    if additional_claims:
        payload.update(additional_claims)

    return jwt.encode(payload, settings.jwt.secret_key, algorithm=settings.jwt.algorithm)


def create_refresh_token(subject: str) -> str:
    """Create a JWT refresh token."""
    settings = get_settings()
    expires_delta = timedelta(minutes=settings.jwt.refresh_token_expire_minutes)
    expire = datetime.now(timezone.utc) + expires_delta

    payload = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "refresh",
    }

    return jwt.encode(payload, settings.jwt.secret_key, algorithm=settings.jwt.algorithm)


def verify_token(token: str, token_type: str = "access") -> dict[str, Any]:
    """
    Verify and decode a JWT token.

    Returns:
        Decoded token payload

    Raises:
        AuthenticationError: If token is invalid or expired
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token, settings.jwt.secret_key, algorithms=[settings.jwt.algorithm]
        )

        if payload.get("type") != token_type:
            raise AuthenticationError(f"Invalid token type. Expected {token_type}")

        return payload

    except JWTError as e:
        logger.warning("Token verification failed", error=str(e))
        raise AuthenticationError(f"Invalid token: {e}") from e


def generate_api_key() -> tuple[str, str, str]:
    """
    Generate a new API key.

    Returns:
        Tuple of (full_key, key_prefix, key_hash)
    """
    # Generate a secure random key
    key = f"mss_{secrets.token_urlsafe(32)}"
    prefix = key[:10]
    key_hash = hashlib.sha256(key.encode()).hexdigest()

    return key, prefix, key_hash


def verify_api_key(key: str) -> str:
    """
    Hash an API key for database lookup.

    Returns:
        SHA-256 hash of the key
    """
    return hashlib.sha256(key.encode()).hexdigest()
