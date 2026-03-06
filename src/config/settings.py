"""
Application settings using pydantic-settings for type-safe configuration.
All settings can be overridden via environment variables or .env file.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"


class CertStoreBackend(str, Enum):
    LOCAL = "local"
    HASHICORP_VAULT = "hashicorp_vault"
    AWS_KMS = "aws_kms"
    AZURE_KEYVAULT = "azure_keyvault"


class AppSettings(BaseSettings):
    """Core application settings."""

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    name: str = "macro-sign-service"
    env: Environment = Environment.DEVELOPMENT
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    secret_key: str = "change-me-to-a-random-secret-key-in-production"
    version: str = "1.0.0"

    @property
    def is_production(self) -> bool:
        return self.env == Environment.PRODUCTION

    @property
    def is_testing(self) -> bool:
        return self.env == Environment.TESTING


class DatabaseSettings(BaseSettings):
    """Database connection settings."""

    model_config = SettingsConfigDict(
        env_prefix="DATABASE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    url: str = "postgresql+asyncpg://macrosign:macrosign@localhost:5432/macrosign"
    pool_size: int = 20
    max_overflow: int = 10
    echo: bool = False

    @property
    def sync_url(self) -> str:
        """Return synchronous database URL for Alembic migrations."""
        return self.url.replace("+asyncpg", "")


class RedisSettings(BaseSettings):
    """Redis connection settings."""

    model_config = SettingsConfigDict(
        env_prefix="REDIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    url: str = "redis://localhost:6379/0"


class CelerySettings(BaseSettings):
    """Celery task queue settings."""

    model_config = SettingsConfigDict(
        env_prefix="CELERY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    broker_url: str = "redis://localhost:6379/1"
    result_backend: str = "redis://localhost:6379/2"
    task_serializer: str = "json"
    result_serializer: str = "json"
    accept_content: List[str] = ["json"]
    timezone: str = "UTC"
    enable_utc: bool = True
    task_track_started: bool = True
    task_time_limit: int = 300  # 5 minutes
    task_soft_time_limit: int = 240  # 4 minutes


class JWTSettings(BaseSettings):
    """JWT authentication settings."""

    model_config = SettingsConfigDict(
        env_prefix="JWT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    secret_key: str = "change-me-to-a-random-jwt-secret"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_minutes: int = 10080  # 7 days


class CertificateSettings(BaseSettings):
    """Certificate management settings."""

    model_config = SettingsConfigDict(
        env_prefix="CERT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    store_backend: CertStoreBackend = CertStoreBackend.LOCAL
    local_cert_path: str = "./certs/signing_cert.pem"
    local_key_path: str = "./certs/signing_key.pem"


class VaultSettings(BaseSettings):
    """HashiCorp Vault settings."""

    model_config = SettingsConfigDict(
        env_prefix="VAULT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    url: str = "http://localhost:8200"
    token: Optional[str] = None
    mount_point: str = "secret"
    cert_path: str = "macro-sign/cert"


class AWSSettings(BaseSettings):
    """AWS KMS settings."""

    model_config = SettingsConfigDict(
        env_prefix="AWS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    region: str = "us-east-1"
    kms_key_id: Optional[str] = None
    access_key_id: Optional[str] = None
    secret_access_key: Optional[str] = None


class AzureSettings(BaseSettings):
    """Azure Key Vault settings."""

    model_config = SettingsConfigDict(
        env_prefix="AZURE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    keyvault_url: Optional[str] = None
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None


class SigningSettings(BaseSettings):
    """Signing operation settings."""

    model_config = SettingsConfigDict(
        env_prefix="SIGNING_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    default_algorithm: str = "sha256"
    max_file_size_mb: int = 50
    allowed_extensions: str = ".vba,.bas,.cls,.frm,.vbs,.xlsm,.xlsb,.docm,.pptm,.xltm,.dotm,.potm"
    use_vba_signing: bool = True
    pfx_password: str = ""

    @property
    def allowed_extensions_list(self) -> List[str]:
        return [ext.strip() for ext in self.allowed_extensions.split(",")]

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


class RateLimitSettings(BaseSettings):
    """Rate limiting settings."""

    model_config = SettingsConfigDict(
        env_prefix="RATE_LIMIT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    enabled: bool = True
    requests_per_minute: int = 60
    burst: int = 10


class CORSSettings(BaseSettings):
    """CORS settings."""

    model_config = SettingsConfigDict(
        env_prefix="CORS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    origins: str = "http://localhost:3000,http://localhost:8000"
    allow_credentials: bool = True

    @property
    def origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.origins.split(",")]


class WebhookSettings(BaseSettings):
    """Webhook settings."""

    model_config = SettingsConfigDict(
        env_prefix="WEBHOOK_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    timeout_seconds: int = 30
    max_retries: int = 3


class Settings:
    """Aggregated settings container."""

    def __init__(self) -> None:
        self.app = AppSettings()
        self.database = DatabaseSettings()
        self.redis = RedisSettings()
        self.celery = CelerySettings()
        self.jwt = JWTSettings()
        self.certificate = CertificateSettings()
        self.vault = VaultSettings()
        self.aws = AWSSettings()
        self.azure = AzureSettings()
        self.signing = SigningSettings()
        self.rate_limit = RateLimitSettings()
        self.cors = CORSSettings()
        self.webhook = WebhookSettings()


@lru_cache()
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()
