"""Input validation utilities."""

import re
import logging
from pathlib import Path
from typing import Tuple, List

logger = logging.getLogger(__name__)


class PDFValidator:
    """Validate PDF files for security and format."""

    SUSPICIOUS_PATTERNS = [
        b"/JavaScript",
        b"/JS",
        b"/Launch",
        b"/EmbeddedFile",
        b"/OpenAction",
    ]

    @classmethod
    def validate(
        cls, content: bytes, filename: str = None
    ) -> Tuple[bool, str, dict]:
        """
        Comprehensive PDF validation.
        Returns: (is_valid, message, metadata)
        """
        metadata = {
            "size_bytes": len(content),
            "has_suspicious_content": False,
            "is_encrypted": False,
            "pdf_version": None,
        }

        if len(content) < 100:
            return False, "File too small to be valid", metadata

        if len(content) > 50 * 1024 * 1024:
            return False, "File exceeds 50MB limit", metadata

        if not content.startswith(b"%PDF"):
            return False, "Not a valid PDF file", metadata

        # PDF version
        version_match = re.search(rb"%PDF-(\d\.\d)", content[:20])
        if version_match:
            metadata["pdf_version"] = version_match.group(1).decode()

        # Check for EOF marker
        if b"%%EOF" not in content[-1024:]:
            return False, "PDF appears truncated", metadata

        # Extension check
        if filename:
            ext = Path(filename).suffix.lower()
            if ext != ".pdf":
                return False, f"Invalid extension: {ext}", metadata

        # Suspicious content check
        for pattern in cls.SUSPICIOUS_PATTERNS:
            if pattern in content:
                metadata["has_suspicious_content"] = True
                logger.warning(f"Suspicious pattern: {pattern}")
                break

        if b"/Encrypt" in content:
            metadata["is_encrypted"] = True

        return True, "Valid PDF", metadata


class PINValidator:
    """Validate MPesa statement PINs."""

    VALID_PATTERNS = [
        r"^\d{4,12}$",
        r"^\+?254\d{9}$",
        r"^0[17]\d{8}$",
    ]

    @classmethod
    def validate(cls, pin: str) -> Tuple[bool, str]:
        if not pin:
            return False, "PIN is required"

        pin = pin.strip()
        if len(pin) < 4:
            return False, "PIN must be at least 4 characters"
        if len(pin) > 20:
            return False, "PIN too long"

        for pattern in cls.VALID_PATTERNS:
            if re.match(pattern, pin):
                return True, "Valid"

        if re.match(r"^[\w\d]+$", pin):
            return True, "Valid"

        return False, "Invalid PIN format"


class InputSanitizer:
    """Sanitize user inputs."""

    CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f]")
    DANGEROUS_CHARS = re.compile(r"[<>&'\"\\;`]")

    @classmethod
    def sanitize_string(cls, value: str, max_length: int = 1000) -> str:
        if not value:
            return ""
        result = cls.CONTROL_CHARS.sub("", value)
        result = cls.DANGEROUS_CHARS.sub("", result)
        return result.strip()[:max_length]

    @classmethod
    def sanitize_filename(cls, filename: str) -> str:
        if not filename:
            return "unnamed_file"
        name = Path(filename).name
        safe = re.sub(r"[^\w\-_\.]", "_", name).lstrip(".")
        return safe[:100] if safe else "unnamed_file"


def validate_request(
    session_id: str = None,
    pin: str = None,
) -> Tuple[bool, List[str]]:
    """Validate common request parameters."""
    errors = []

    if session_id is not None:
        if not re.match(r"^[A-Za-z0-9_\-]{20,64}$", session_id):
            errors.append("Invalid session ID")

    if pin is not None:
        valid, msg = PINValidator.validate(pin)
        if not valid:
            errors.append(f"PIN: {msg}")

    return len(errors) == 0, errors