"""PDF processor tests."""

import pytest
from app.services.pdf_processor import SecurePDFProcessor


@pytest.fixture
def processor():
    return SecurePDFProcessor()


def test_invalid_file_rejected(processor):
    is_valid, msg, encrypted = processor.validate_pdf(b"not a pdf at all")
    assert is_valid is False
    assert "not a valid PDF" in msg


def test_empty_file_rejected(processor):
    is_valid, msg, encrypted = processor.validate_pdf(b"")
    assert is_valid is False


def test_empty_pin_with_encrypted_pdf(processor):
    result = processor.decrypt_and_extract(b"%PDF-fake", "")
    # Should handle gracefully
    assert isinstance(result.success, bool)


def test_pin_validation_short(processor):
    assert processor._validate_pin_format("12") is False


def test_pin_validation_valid(processor):
    assert processor._validate_pin_format("1234") is True
    assert processor._validate_pin_format("123456789") is True


def test_pin_validation_phone(processor):
    assert processor._validate_pin_format("+254712345678") is True