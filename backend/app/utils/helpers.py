"""General helper utilities."""

import re
import hashlib
import secrets
import logging
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


# ─── String Utilities ──────────────────────────────────────────

def truncate(text: str, max_length: int = 100, suffix: str = "...") -> str:
    if not text or len(text) <= max_length:
        return text or ""
    return text[: max_length - len(suffix)] + suffix


def mask_sensitive(value: str, visible_chars: int = 4) -> str:
    """Mask sensitive string, showing only last N characters."""
    if not value:
        return ""
    if len(value) <= visible_chars:
        return "*" * len(value)
    return "*" * (len(value) - visible_chars) + value[-visible_chars:]


def mask_phone_number(phone: str) -> str:
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 8:
        return mask_sensitive(phone)
    return f"{digits[:4]}****{digits[-4:]}"


def clean_whitespace(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


# ─── Amount Parsing ────────────────────────────────────────────

def parse_amount(amount_str: str) -> Optional[Decimal]:
    """Parse monetary amount from various formats."""
    if not amount_str:
        return None
    try:
        cleaned = re.sub(r"(?i)(ksh\.?|kes|ksh|/=)", "", str(amount_str))
        cleaned = cleaned.strip().replace(",", "")
        is_negative = cleaned.startswith("-") or cleaned.startswith("(")
        cleaned = cleaned.strip("-() ")
        if not cleaned:
            return None
        amount = Decimal(cleaned)
        return -amount if is_negative else amount
    except (InvalidOperation, ValueError):
        return None


def format_amount(amount: Optional[Decimal], currency: str = "KES") -> str:
    if amount is None:
        return ""
    return f"{currency} {amount:,.2f}"


# ─── Date Parsing ──────────────────────────────────────────────

DATE_FORMATS = [
    "%d/%m/%Y %I:%M %p",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%d-%m-%Y %H:%M:%S",
    "%d %B %Y %I:%M %p",
    "%d %b %Y",
]


def parse_date(date_str: str) -> Optional[datetime]:
    if not date_str:
        return None
    normalized = clean_whitespace(date_str)
    normalized = re.sub(
        r"(\d)([AP]M)", r"\1 \2", normalized, flags=re.IGNORECASE
    )
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue
    try:
        from dateutil import parser as dateutil_parser
        return dateutil_parser.parse(normalized, dayfirst=True)
    except Exception:
        return None


def format_date(dt: Optional[datetime], fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    return dt.strftime(fmt) if dt else ""


# ─── ID Generation ─────────────────────────────────────────────

def generate_session_id(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


def generate_download_token() -> str:
    return secrets.token_urlsafe(24)


# ─── Hashing ──────────────────────────────────────────────────

def hash_content(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def verify_hash(content: bytes, expected: str) -> bool:
    return secrets.compare_digest(hashlib.sha256(content).hexdigest(), expected)


# ─── Data Extraction ──────────────────────────────────────────

def extract_phone_number(text: str) -> Optional[str]:
    patterns = [r"\+254(\d{9})", r"254(\d{9})", r"0([17]\d{8})"]
    for p in patterns:
        m = re.search(p, text)
        if m:
            return f"+254{m.group(1)}"
    return None


def extract_receipt_number(text: str) -> Optional[str]:
    m = re.search(r"\b([A-Z]{2,3}\d{7,10})\b", text.upper())
    return m.group(1) if m else None


def extract_all_amounts(text: str) -> List[Decimal]:
    pattern = r"(?:Ksh\.?|KES)?\s*([\d,]+\.?\d{0,2})"
    matches = re.findall(pattern, text, re.IGNORECASE)
    results = []
    for m in matches:
        parsed = parse_amount(m)
        if parsed is not None and parsed > 0:
            results.append(parsed)
    return results


# ─── Statistics ────────────────────────────────────────────────

def calculate_statistics(amounts: List[Decimal]) -> Dict[str, Any]:
    if not amounts:
        return {
            "count": 0,
            "sum": Decimal("0"),
            "mean": Decimal("0"),
            "min": Decimal("0"),
            "max": Decimal("0"),
        }
    total = sum(amounts)
    return {
        "count": len(amounts),
        "sum": total,
        "mean": total / len(amounts),
        "min": min(amounts),
        "max": max(amounts),
    }