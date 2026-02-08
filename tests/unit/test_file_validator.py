"""
Unit tests for file validation utilities.
"""

import pytest

from src.utils.file_validator import FileValidationError, FileValidator


@pytest.fixture
def validator():
    """Create a file validator."""
    return FileValidator()


@pytest.fixture
def valid_content():
    """Valid VBA macro content."""
    return b"""
    Sub HelloWorld()
        MsgBox "Hello, World!"
    End Sub
    """


class TestFileValidator:
    """Tests for the FileValidator class."""

    def test_valid_file(self, validator, valid_content):
        # Should not raise
        validator.validate("test.vba", valid_content)

    def test_valid_extensions(self, validator, valid_content):
        for ext in [".vba", ".bas", ".cls", ".frm", ".vbs"]:
            validator.validate(f"test{ext}", valid_content)

    def test_invalid_extension(self, validator, valid_content):
        with pytest.raises(FileValidationError, match="not allowed"):
            validator.validate("test.exe", valid_content)

    def test_invalid_extension_py(self, validator, valid_content):
        with pytest.raises(FileValidationError, match="not allowed"):
            validator.validate("test.py", valid_content)

    def test_empty_filename(self, validator, valid_content):
        with pytest.raises(FileValidationError, match="Filename is required"):
            validator.validate("", valid_content)

    def test_path_traversal_dotdot(self, validator, valid_content):
        with pytest.raises(FileValidationError, match="path traversal"):
            validator.validate("../../../etc/passwd", valid_content)

    def test_path_traversal_slash(self, validator, valid_content):
        with pytest.raises(FileValidationError, match="path traversal"):
            validator.validate("/etc/test.vba", valid_content)

    def test_path_traversal_backslash(self, validator, valid_content):
        with pytest.raises(FileValidationError, match="path traversal"):
            validator.validate("..\\test.vba", valid_content)

    def test_null_byte_in_filename(self, validator, valid_content):
        with pytest.raises(FileValidationError, match="null bytes"):
            validator.validate("test\x00.vba", valid_content)

    def test_empty_file(self, validator):
        with pytest.raises(FileValidationError, match="empty"):
            validator.validate("test.vba", b"")

    def test_file_too_large(self, validator):
        # Create content larger than max (default 50MB)
        large_content = b"x" * (51 * 1024 * 1024)
        with pytest.raises(FileValidationError, match="too large"):
            validator.validate("test.vba", large_content)

    def test_scan_dangerous_patterns(self, validator):
        dangerous_content = b"""
        Sub Exploit()
            Shell("cmd.exe /c dir")
        End Sub
        """
        # Should still pass validation (warnings only, not blocking)
        validator.validate("test.vba", dangerous_content)

    def test_skip_content_scan(self, validator):
        dangerous_content = b'Shell("cmd.exe")'
        validator.validate("test.vba", dangerous_content, skip_content_scan=True)

    def test_get_file_info(self):
        info = FileValidator.get_file_info("test.vba", b"hello world")
        assert info["filename"] == "test.vba"
        assert info["extension"] == ".vba"
        assert info["size_bytes"] == 11
        assert "B" in info["size_human"]

    def test_get_file_info_larger(self):
        content = b"x" * 2048
        info = FileValidator.get_file_info("test.vba", content)
        assert info["size_bytes"] == 2048
        assert "KB" in info["size_human"]
