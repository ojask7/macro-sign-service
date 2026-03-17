"""Application configuration via environment variables."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All configuration loaded from environment variables or .env file."""

    model_config = {"env_prefix": "MACRO_SIGN_", "env_file": ".env", "extra": "ignore"}

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Certificates
    certs_dir: Path = Path("certs")
    default_cert_name: str = "default"
    pfx_password: str = ""

    # Database
    db_path: Path = Path("audit.db")

    # Auth (optional — leave blank to disable)
    api_key: str = ""

    # Limits
    max_file_size_mb: int = 50

    # Allowed extensions
    allowed_extensions: str = ".xlsm,.docm,.pptm,.xlam,.dotm,.ppam,.vba,.bas,.cls,.frm"

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    @property
    def allowed_extensions_list(self) -> list[str]:
        return [e.strip() for e in self.allowed_extensions.split(",") if e.strip()]

    @property
    def office_extensions(self) -> list[str]:
        return [".xlsm", ".docm", ".pptm", ".xlam", ".dotm", ".ppam"]

    @property
    def text_macro_extensions(self) -> list[str]:
        return [".vba", ".bas", ".cls", ".frm"]


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
