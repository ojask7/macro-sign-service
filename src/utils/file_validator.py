"""
File validation utilities for macro files.
Ensures uploaded files are safe and within allowed parameters.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from src.config.logging import get_logger
from src.config.settings import get_settings

logger = get_logger(__name__)


class FileValidationError(Exception):
    """Raised when file validation fails."""

    pass


class FileValidator:
    """Validates uploaded macro files before signing."""

    # Known dangerous patterns that should not be in macros
    DANGEROUS_PATTERNS = [
        b"Shell(",
        b"WScript.Shell",
        b"PowerShell",
        b"cmd.exe",
        b"CreateObject(\"Scripting.FileSystemObject\")",
    ]

    def __init__(self) -> None:
        settings = get_settings()
        self.max_file_size = settings.signing.max_file_size_bytes
        self.allowed_extensions = settings.signing.allowed_extensions_list

    def validate(
        self,
        filename: str,
        content: bytes,
        skip_content_scan: bool = False,
    ) -> None:
        """
        Validate a macro file for signing.

        Args:
            filename: Original filename
            content: File content bytes
            skip_content_scan: Skip dangerous pattern scanning

        Raises:
            FileValidationError: If validation fails
        """
        self._validate_filename(filename)
        self._validate_extension(filename)
        self._validate_size(content)
        self._validate_not_empty(content)
        if not skip_content_scan:
            self._scan_content(content)

        logger.info("File validation passed", filename=filename, size=len(content))

    def _validate_filename(self, filename: str) -> None:
        """Check for path traversal and invalid characters."""
        if not filename:
            raise FileValidationError("Filename is required")

        # Check for path traversal
        if ".." in filename or "/" in filename or "\\" in filename:
            raise FileValidationError("Invalid filename: path traversal detected")

        # Check for null bytes
        if "\x00" in filename:
            raise FileValidationError("Invalid filename: null bytes detected")

    def _validate_extension(self, filename: str) -> None:
        """Check that the file has an allowed extension."""
        ext = Path(filename).suffix.lower()
        if ext not in self.allowed_extensions:
            raise FileValidationError(
                f"File extension '{ext}' not allowed. "
                f"Allowed extensions: {', '.join(self.allowed_extensions)}"
            )

    def _validate_size(self, content: bytes) -> None:
        """Check that the file is within size limits."""
        if len(content) > self.max_file_size:
            max_mb = self.max_file_size / (1024 * 1024)
            actual_mb = len(content) / (1024 * 1024)
            raise FileValidationError(
                f"File too large: {actual_mb:.1f}MB (max: {max_mb:.0f}MB)"
            )

    def _validate_not_empty(self, content: bytes) -> None:
        """Check that the file is not empty."""
        if len(content) == 0:
            raise FileValidationError("File is empty")

    def _scan_content(self, content: bytes) -> list[str]:
        """
        Scan file content for potentially dangerous patterns.
        Returns list of warnings (does not block signing).
        """
        warnings = []
        for pattern in self.DANGEROUS_PATTERNS:
            if pattern in content:
                warnings.append(
                    f"Potentially dangerous pattern detected: {pattern.decode(errors='replace')}"
                )

        if warnings:
            logger.warning(
                "Dangerous patterns detected in macro file",
                warning_count=len(warnings),
                warnings=warnings,
            )

        return warnings

    @staticmethod
    def get_file_info(filename: str, content: bytes) -> dict:
        """Get basic information about a file."""
        return {
            "filename": filename,
            "extension": Path(filename).suffix.lower(),
            "size_bytes": len(content),
            "size_human": _format_size(len(content)),
        }


def _format_size(size_bytes: int) -> str:
    """Format byte size to human-readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"
