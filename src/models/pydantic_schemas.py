"""
Pydantic models for API request/response validation.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


# ============================================================================
# Enums
# ============================================================================


class JobStatusEnum(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class UserRoleEnum(str, Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    DEVELOPER = "developer"
    VIEWER = "viewer"


# ============================================================================
# Auth Schemas
# ============================================================================


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenPayload(BaseModel):
    sub: str
    role: str
    exp: int


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8)


class RegisterRequest(BaseModel):
    email: str = Field(..., max_length=255)
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = Field(None, max_length=255)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if "@" not in v:
            raise ValueError("Invalid email address")
        return v.lower()


class APIKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    expires_in_days: Optional[int] = Field(None, ge=1, le=365)


class APIKeyResponse(BaseModel):
    id: str
    name: str
    key_prefix: str
    is_active: bool
    created_at: datetime
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None


class APIKeyCreatedResponse(APIKeyResponse):
    """Response when creating a new API key (includes the full key)."""

    api_key: str  # Only shown once at creation time


# ============================================================================
# User Schemas
# ============================================================================


class UserBase(BaseModel):
    email: str
    username: str
    full_name: Optional[str] = None


class UserResponse(UserBase):
    id: str
    role: str
    is_active: bool
    team_id: Optional[str] = None
    created_at: datetime
    last_login: Optional[datetime] = None

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[UserRoleEnum] = None
    is_active: Optional[bool] = None
    team_id: Optional[str] = None


# ============================================================================
# Team Schemas
# ============================================================================


class TeamCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None


class TeamResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    is_active: bool
    created_at: datetime
    member_count: int = 0

    model_config = {"from_attributes": True}


class TeamUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    is_active: Optional[bool] = None


# ============================================================================
# Signing Schemas
# ============================================================================


class SigningRequest(BaseModel):
    """Request body for signing operations (file is uploaded separately)."""

    profile: Optional[str] = Field(None, description="Signing profile name")
    algorithm: Optional[str] = Field("sha256", description="Hash algorithm")
    webhook_url: Optional[str] = Field(None, description="Webhook URL for completion notification")
    metadata: Optional[dict[str, Any]] = Field(None, description="Custom metadata")


class SigningJobResponse(BaseModel):
    job_id: str
    status: JobStatusEnum
    original_filename: str
    file_size: int
    file_hash: Optional[str] = None
    signature: Optional[str] = None
    certificate_fingerprint: Optional[str] = None
    algorithm: str
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SigningJobCreate(BaseModel):
    """Internal model for creating signing jobs."""

    original_filename: str
    file_size: int
    algorithm: str = "sha256"
    profile_id: Optional[str] = None
    webhook_url: Optional[str] = None


class SigningJobList(BaseModel):
    jobs: List[SigningJobResponse]
    total: int
    page: int
    per_page: int


# ============================================================================
# Verification Schemas
# ============================================================================


class VerifyRequest(BaseModel):
    """Request for verifying a signed macro."""

    signature: str = Field(..., description="Hex-encoded signature")
    algorithm: Optional[str] = Field("sha256", description="Hash algorithm used")


class VerifyResponse(BaseModel):
    is_valid: bool
    certificate_subject: Optional[str] = None
    certificate_issuer: Optional[str] = None
    certificate_expiry: Optional[datetime] = None
    message: str


# ============================================================================
# Signing Profile Schemas
# ============================================================================


class SigningProfileCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    certificate_name: str = Field(..., description="Certificate name in the cert store")
    algorithm: str = Field("sha256", description="Default signing algorithm")
    is_default: bool = False


class SigningProfileResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    team_id: str
    certificate_name: str
    algorithm: str
    is_active: bool
    is_default: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class SigningProfileUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    certificate_name: Optional[str] = None
    algorithm: Optional[str] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None


# ============================================================================
# Health & Status Schemas
# ============================================================================


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    timestamp: datetime
    checks: dict[str, str] = {}


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    status_code: int


# ============================================================================
# Audit Log Schemas
# ============================================================================


class AuditLogResponse(BaseModel):
    id: str
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    user_id: Optional[str] = None
    ip_address: Optional[str] = None
    details: Optional[str] = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditLogList(BaseModel):
    logs: List[AuditLogResponse]
    total: int
    page: int
    per_page: int


# ============================================================================
# Webhook Schemas
# ============================================================================


class WebhookCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    url: str = Field(..., max_length=2048)
    secret: Optional[str] = Field(None, max_length=255)
    events: str = Field("signing.completed", description="Comma-separated event types")


class WebhookResponse(BaseModel):
    id: str
    name: str
    url: str
    events: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class WebhookUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    events: Optional[str] = None
    is_active: Optional[bool] = None


# ============================================================================
# ServiceNow (SNOW) Integration Schemas
# ============================================================================


class SNOWSignResponse(BaseModel):
    """
    Response returned directly to the ServiceNow form after synchronous signing.
    Contains the signed content (base64), signature, and certificate details.
    """

    status: str  # "signed"
    original_filename: str
    file_size: int
    signed_content_b64: str  # base64-encoded original file content
    signature: str  # hex-encoded digital signature
    file_hash: str  # hex SHA-256/384/512 hash of the file
    certificate_fingerprint: str  # SHA-256 fingerprint of signing cert
    certificate_subject: str  # X.509 subject (CN=..., O=..., C=...)
    certificate_issuer: str  # X.509 issuer (CN=..., O=..., C=...)
    certificate_not_before: datetime  # certificate validity start
    certificate_not_after: datetime  # certificate validity end
    certificate_key_type: str  # e.g. "RSA-2048", "EC-secp256r1"
    certificate_serial: str  # certificate serial number
    certificate_pem: str  # PEM-encoded public cert for client-side verification
    algorithm: str  # hash algorithm used
    signed_at: datetime
    requester_id: Optional[str] = None  # ServiceNow sys_id of the requesting user
    domain: str  # certificate domain/name used for signing


class SNOWVerifyResponse(BaseModel):
    """Response from SNOW signature verification endpoint."""

    is_valid: bool
    certificate_subject: Optional[str] = None
    certificate_issuer: Optional[str] = None
    certificate_expiry: Optional[datetime] = None
    message: str
    domain: Optional[str] = None


# ============================================================================
# Analytics Schemas
# ============================================================================


class UsageStats(BaseModel):
    total_signing_jobs: int
    completed_jobs: int
    failed_jobs: int
    average_signing_time_ms: Optional[float] = None
    total_files_signed: int
    period: str


class DashboardStats(BaseModel):
    signing_stats: UsageStats
    active_users: int
    active_teams: int
    active_certificates: int
    recent_jobs: List[SigningJobResponse]
