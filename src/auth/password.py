"""
Password hashing utilities using bcrypt.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import base64

import bcrypt


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    # bcrypt has a 72-byte limit, so we pre-hash longer passwords with SHA-256
    pwd_bytes = password.encode("utf-8")
    if len(pwd_bytes) > 72:
        pwd_bytes = base64.b64encode(hashlib.sha256(pwd_bytes).digest())
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    pwd_bytes = plain_password.encode("utf-8")
    if len(pwd_bytes) > 72:
        pwd_bytes = base64.b64encode(hashlib.sha256(pwd_bytes).digest())
    try:
        return bcrypt.checkpw(pwd_bytes, hashed_password.encode("utf-8"))
    except Exception:
        return False
