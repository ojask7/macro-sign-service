"""Unit tests for file validation."""

from __future__ import annotations

import pytest

from app.validator import FileValidationError, validate_file


class TestValidateFile:
    def test_valid_xlsm(self, minimal_xlsm):
        warnings = validate_file("report.xlsm", minimal_xlsm)
        assert isinstance(warnings, list)

    def test_valid_docm(self, minimal_docm):
        warnings = validate_file("doc.docm", minimal_docm)
        assert isinstance(warnings, list)

    def test_valid_vba(self, sample_vba_content):
        warnings = validate_file("module.vba", sample_vba_content)
        assert isinstance(warnings, list)

    def test_valid_bas(self, sample_vba_content):
        validate_file("module.bas", sample_vba_content)

    def test_valid_cls(self, sample_vba_content):
        validate_file("class.cls", sample_vba_content)

    def test_empty_filename(self, minimal_xlsm):
        with pytest.raises(FileValidationError, match="Filename is required"):
            validate_file("", minimal_xlsm)

    def test_path_traversal(self, minimal_xlsm):
        with pytest.raises(FileValidationError, match="path traversal"):
            validate_file("../etc/passwd.xlsm", minimal_xlsm)

    def test_null_bytes(self, minimal_xlsm):
        with pytest.raises(FileValidationError, match="null bytes"):
            validate_file("file\x00.xlsm", minimal_xlsm)

    def test_disallowed_extension(self, minimal_xlsm):
        with pytest.raises(FileValidationError, match="not allowed"):
            validate_file("file.exe", minimal_xlsm)

    def test_empty_content(self):
        with pytest.raises(FileValidationError, match="empty"):
            validate_file("file.xlsm", b"")

    def test_oversized_file(self):
        # Default limit is 50MB — create content just over
        big = b"x" * (51 * 1024 * 1024)
        with pytest.raises(FileValidationError, match="too large"):
            validate_file("big.xlsm", big)

    def test_dangerous_pattern_returns_warning(self):
        content = b"Shell(cmd.exe /c dir)"
        warnings = validate_file("macro.vba", content)
        assert any("Shell(" in w for w in warnings)

    def test_skip_content_scan(self):
        content = b"Shell(dangerous)"
        warnings = validate_file("macro.vba", content, skip_content_scan=True)
        assert warnings == []
