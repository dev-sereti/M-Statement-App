"""Secure PDF decryption and text extraction."""

import io
import re
import logging
from typing import Optional, Tuple
from dataclasses import dataclass

import pikepdf
import pdfplumber

logger = logging.getLogger(__name__)


@dataclass
class PDFProcessingResult:
    success: bool
    text_content: Optional[str] = None
    page_count: int = 0
    error: Optional[str] = None
    is_encrypted: bool = False


class SecurePDFProcessor:
    """Handle encrypted PDF decryption and text extraction."""

    def validate_pdf(self, file_content: bytes) -> Tuple[bool, str, bool]:
        """
        Validate PDF file and check encryption status.
        Returns: (is_valid, message, is_encrypted)
        """
        if not file_content.startswith(b"%PDF"):
            return False, "File is not a valid PDF", False

        try:
            pdf_stream = io.BytesIO(file_content)
            try:
                with pikepdf.open(pdf_stream) as pdf:
                    page_count = len(pdf.pages)
                    return True, f"Valid PDF with {page_count} pages", False
            except pikepdf.PasswordError:
                return True, "PDF is password-protected", True
            except pikepdf.PdfError as e:
                return False, f"Invalid PDF: {str(e)[:100]}", False
        except Exception as e:
            logger.error(f"PDF validation error: {e}")
            return False, "Could not validate PDF file", False

    def decrypt_and_extract(
        self, file_content: bytes, pin: str
    ) -> PDFProcessingResult:
        """Decrypt PDF with PIN and extract text. PIN is never logged."""
        # Handle unencrypted PDFs
        if not self._is_encrypted(file_content):
            return self._extract_without_password(file_content)

        if not pin or not pin.strip():
            return PDFProcessingResult(
                success=False,
                error="PIN cannot be empty",
                is_encrypted=True,
            )

        # Validate PIN format
        if not self._validate_pin_format(pin):
            return PDFProcessingResult(
                success=False,
                error="Invalid PIN format",
                is_encrypted=True,
            )

        try:
            pdf_stream = io.BytesIO(file_content)
            try:
                with pikepdf.open(pdf_stream, password=pin) as pdf:
                    logger.info(f"PDF decrypted OK, {len(pdf.pages)} pages")
                    decrypted_buffer = io.BytesIO()
                    pdf.save(decrypted_buffer)
                    decrypted_buffer.seek(0)

                    text_content = self._extract_text(decrypted_buffer)

                    if not text_content:
                        return PDFProcessingResult(
                            success=False,
                            error="No text found in PDF. May be scanned images.",
                            is_encrypted=True,
                        )

                    return PDFProcessingResult(
                        success=True,
                        text_content=text_content,
                        page_count=len(pdf.pages),
                        is_encrypted=True,
                    )

            except pikepdf.PasswordError:
                return PDFProcessingResult(
                    success=False,
                    error="Incorrect PIN. Please check and try again.",
                    is_encrypted=True,
                )

        except Exception as e:
            logger.error(f"PDF processing error: {type(e).__name__}: {e}")
            return PDFProcessingResult(
                success=False,
                error="An error occurred while processing the PDF.",
                is_encrypted=True,
            )

    def _extract_without_password(
        self, file_content: bytes
    ) -> PDFProcessingResult:
        """Extract text from unencrypted PDF."""
        try:
            pdf_stream = io.BytesIO(file_content)
            with pikepdf.open(pdf_stream) as pdf:
                decrypted_buffer = io.BytesIO()
                pdf.save(decrypted_buffer)
                decrypted_buffer.seek(0)

                text_content = self._extract_text(decrypted_buffer)

                if not text_content:
                    return PDFProcessingResult(
                        success=False,
                        error="No text found in PDF.",
                        is_encrypted=False,
                    )

                return PDFProcessingResult(
                    success=True,
                    text_content=text_content,
                    page_count=len(pdf.pages),
                    is_encrypted=False,
                )
        except Exception as e:
            logger.error(f"Extraction error: {e}")
            return PDFProcessingResult(
                success=False,
                error="Could not extract text from PDF.",
                is_encrypted=False,
            )

    def _extract_text(self, pdf_buffer: io.BytesIO) -> Optional[str]:
        """Extract text from decrypted PDF buffer."""
        try:
            all_text = []
            with pdfplumber.open(pdf_buffer) as pdf:
                for page in pdf.pages:
                    # Try table extraction first (better for MPesa)
                    tables = page.extract_tables()
                    if tables:
                        for table in tables:
                            for row in table:
                                if row:
                                    cleaned = [
                                        str(cell).strip() if cell else ""
                                        for cell in row
                                    ]
                                    all_text.append("\t".join(cleaned))
                    else:
                        text = page.extract_text()
                        if text:
                            all_text.append(text)

            return "\n".join(all_text) if all_text else None

        except Exception as e:
            logger.error(f"Text extraction error: {e}")
            return None

    def _is_encrypted(self, content: bytes) -> bool:
        """Check if PDF has encryption markers."""
        try:
            pdf_stream = io.BytesIO(content)
            with pikepdf.open(pdf_stream):
                return False
        except pikepdf.PasswordError:
            return True
        except Exception:
            return False

    def _validate_pin_format(self, pin: str) -> bool:
        """Validate PIN format without logging actual PIN."""
        pin = pin.strip()
        if not (4 <= len(pin) <= 20):
            return False
        if re.match(r"^\d+$", pin):
            return True
        if re.match(r"^\+?[\d\s\-]{8,15}$", pin):
            return True
        return False