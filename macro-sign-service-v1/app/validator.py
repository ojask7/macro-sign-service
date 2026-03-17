"""File validation for macro files before signing."""

from __future__ import annotations

import logging
from pathlib import Path

from app.config import get_settings

log = logging.getLogger(__name__)


class FileValidationError(Exception):
    """Raised when file validation fails."""


DANGEROUS_PATTERNS = [
    b"Shell(",
    b"WScript.Shell",
    b"PowerShell",
    b"cmd.exe",
    b'CreateObject("Scripting.FileSystemObject")',
]


def validate_file(
    filename: str,
    content: bytes,
    skip_content_scan: bool = False,
) -> list[str]:
    """
    Validate a macro file for signing.

    Returns list of warnings (non-blocking).
    Raises FileValidationError if hard validation fails.
    """
    settings = get_settings()

    # Filename checks
    if not filename:
        raise FileValidationError("Filename is required")
    if ".." in filename or "/" in filename or "\\" in filename:
        raise FileValidationError("Invalid filename: path traversal detected")
    if "\x00" in filename:
        raise FileValidationError("Invalid filename: null bytes detected")

    # Extension check
    ext = Path(filename).suffix.lower()
    if ext not in settings.allowed_extensions_list:
        raise FileValidationError(
            f"File extension '{ext}' not allowed. "
            f"Allowed: {', '.join(settings.allowed_extensions_list)}"
        )

    # Size check
    if len(content) == 0:
        raise FileValidationError("File is empty")
    if len(content) > settings.max_file_size_bytes:
        max_mb = settings.max_file_size_bytes / (1024 * 1024)
        actual_mb = len(content) / (1024 * 1024)
        raise FileValidationError(
            f"File too large: {actual_mb:.1f}MB (max: {max_mb:.0f}MB)"
        )

    # Content scan (warnings only)
    warnings: list[str] = []
    if not skip_content_scan:
        for pattern in DANGEROUS_PATTERNS:
            if pattern in content:
                warnings.append(
                    f"Potentially dangerous pattern: {pattern.decode(errors='replace')}"
                )
        if warnings:
            log.warning("Dangerous patterns in %s: %s", filename, warnings)

    log.info("Validation passed: %s (%d bytes)", filename, len(content))
    return warnings
