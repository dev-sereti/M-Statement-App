"""Validator tests."""

import pytest
from app.utils.validators import PDFValidator, PINValidator, InputSanitizer


class TestPDFValidator:
    def test_valid_pdf_header(self):
        content = b"%PDF-1.4\n" + b"x" * 200 + b"%%EOF"
        is_valid, msg, meta = PDFValidator.validate(content)
        assert is_valid is True
        assert meta["pdf_version"] == "1.4"

    def test_invalid_header(self):
        is_valid, msg, meta = PDFValidator.validate(b"NOT A PDF")
        assert is_valid is False

    def test_too_small(self):
        is_valid, msg, meta = PDFValidator.validate(b"%PDF-1.4")
        assert is_valid is False

    def test_wrong_extension(self):
        content = b"%PDF-1.4\n" + b"x" * 200 + b"%%EOF"
        is_valid, msg, meta = PDFValidator.validate(content, "file.txt")
        assert is_valid is False

    def test_missing_eof(self):
        content = b"%PDF-1.4\n" + b"x" * 200
        is_valid, msg, meta = PDFValidator.validate(content)
        assert is_valid is False


class TestPINValidator:
    def test_valid_numeric(self):
        assert PINValidator.validate("1234")[0] is True
        assert PINValidator.validate("123456")[0] is True

    def test_valid_phone(self):
        assert PINValidator.validate("+254712345678")[0] is True

    def test_too_short(self):
        assert PINValidator.validate("12")[0] is False

    def test_too_long(self):
        assert PINValidator.validate("1" * 25)[0] is False

    def test_empty(self):
        assert PINValidator.validate("")[0] is False


class TestInputSanitizer:
    def test_remove_control_chars(self):
        result = InputSanitizer.sanitize_string("hello\x00world")
        assert "\x00" not in result

    def test_remove_dangerous_chars(self):
        result = InputSanitizer.sanitize_string("<script>alert('xss')</script>")
        assert "<" not in result
        assert ">" not in result

    def test_filename_sanitize(self):
        result = InputSanitizer.sanitize_filename("../../../etc/passwd")
        assert ".." not in result
        assert "/" not in result

    def test_empty_filename(self):
        assert InputSanitizer.sanitize_filename("") == "unnamed_file"

    def test_max_length(self):
        result = InputSanitizer.sanitize_string("x" * 2000, max_length=100)
        assert len(result) <= 100 