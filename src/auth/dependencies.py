"""
FastAPI authentication dependencies.
Provides current user extraction from JWT tokens and API keys.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
    APIKeyHeader,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.jwt_handler import AuthenticationError, verify_api_key, verify_token
from src.config.logging import get_logger
from src.models.database import get_db
from src.models.schemas import APIKey, User, UserRole

logger = get_logger(__name__)

# Security schemes
bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_current_user(
    request: Request,
    bearer: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_header),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Extract and validate the current user from JWT token or API key.
    Supports both Bearer token and X-API-Key authentication.
    """
    user = None

    # Try JWT Bearer token first
    if bearer and bearer.credentials:
        try:
            payload = verify_token(bearer.credentials)
            user_id = payload.get("sub")
            if user_id:
                result = await db.execute(
                    select(User).where(User.id == UUID(user_id))
                )
                user = result.scalar_one_or_none()
        except AuthenticationError:
            pass

    # Fall back to API key
    if user is None and api_key:
        key_hash = verify_api_key(api_key)
        result = await db.execute(
            select(APIKey)
            .where(APIKey.key_hash == key_hash, APIKey.is_active == True)
        )
        api_key_record = result.scalar_one_or_none()

        if api_key_record:
            # Check expiry
            if (
                api_key_record.expires_at
                and api_key_record.expires_at < datetime.now(timezone.utc)
            ):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="API key has expired",
                )

            # Update last used timestamp
            api_key_record.last_used_at = datetime.now(timezone.utc)
            await db.flush()

            # Get user
            result = await db.execute(
                select(User).where(User.id == api_key_record.user_id)
            )
            user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Get the current active user."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )
    return current_user


def require_role(*roles: UserRole):
    """
    Dependency factory that requires the current user to have one of the specified roles.

    Usage:
        @router.get("/admin", dependencies=[Depends(require_role(UserRole.ADMIN))])
    """

    async def role_checker(
        current_user: User = Depends(get_current_user),
    ) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required roles: {[r.value for r in roles]}",
            )
        return current_user

    return role_checker


class RBACPermission:
    """Role-based access control permission checker."""

    PERMISSIONS = {
        UserRole.ADMIN: {
            "sign", "verify", "manage_users", "manage_teams",
            "manage_certs", "manage_profiles", "view_audit",
            "manage_webhooks", "view_analytics",
        },
        UserRole.MANAGER: {
            "sign", "verify", "manage_teams", "manage_profiles",
            "view_audit", "manage_webhooks", "view_analytics",
        },
        UserRole.DEVELOPER: {
            "sign", "verify", "view_audit",
        },
        UserRole.VIEWER: {
            "verify", "view_audit",
        },
    }

    def __init__(self, permission: str) -> None:
        self.permission = permission

    async def __call__(
        self, current_user: User = Depends(get_current_user)
    ) -> User:
        user_permissions = self.PERMISSIONS.get(current_user.role, set())
        if self.permission not in user_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{self.permission}' denied for role '{current_user.role.value}'",
            )
        return current_user
