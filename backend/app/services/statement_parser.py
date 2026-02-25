"""Parse MPesa PDF statement text into structured transaction data."""

import re
import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import List, Optional, Dict
from enum import Enum

logger = logging.getLogger(__name__)


class TransactionType(str, Enum):
    SENT = "Money Sent"
    RECEIVED = "Money Received"
    PAYBILL = "Paybill Payment"
    TILL = "Buy Goods (Till)"
    AIRTIME = "Airtime Purchase"
    WITHDRAWAL = "Withdrawal"
    DEPOSIT = "Deposit"
    REVERSAL = "Reversal"
    FULIZA = "Fuliza"
    LOAN = "Loan"
    CHARGES = "Transaction Charges"
    OTHER = "Other"


@dataclass
class MPesaTransaction:
    receipt_no: str = ""
    completion_time: Optional[datetime] = None
    description: str = ""
    paid_in: Optional[Decimal] = None
    withdrawn: Optional[Decimal] = None
    balance: Optional[Decimal] = None
    transaction_type: TransactionType = TransactionType.OTHER
    counterparty: str = ""
    reference: str = ""

    def to_dict(self) -> dict:
        return {
            "Receipt No.": self.receipt_no,
            "Date": (
                self.completion_time.strftime("%Y-%m-%d")
                if self.completion_time
                else ""
            ),
            "Time": (
                self.completion_time.strftime("%H:%M:%S")
                if self.completion_time
                else ""
            ),
            "Description": self.description,
            "Transaction Type": self.transaction_type.value,
            "Counterparty": self.counterparty,
            "Reference": self.reference,
            "Paid In (KES)": float(self.paid_in) if self.paid_in else 0.0,
            "Withdrawn (KES)": float(self.withdrawn) if self.withdrawn else 0.0,
            "Balance (KES)": float(self.balance) if self.balance else 0.0,
        }


@dataclass
class StatementMetadata:
    account_name: str = ""
    phone_number: str = ""
    statement_period_start: Optional[datetime] = None
    statement_period_end: Optional[datetime] = None
    opening_balance: Optional[Decimal] = None
    closing_balance: Optional[Decimal] = None
    total_paid_in: Optional[Decimal] = None
    total_withdrawn: Optional[Decimal] = None
    transaction_count: int = 0


@dataclass
class ParsedStatement:
    metadata: StatementMetadata = field(default_factory=StatementMetadata)
    transactions: List[MPesaTransaction] = field(default_factory=list)
    parsing_warnings: List[str] = field(default_factory=list)
    raw_lines_processed: int = 0


class MPesaStatementParser:
    """Parse MPesa statement text into structured data."""

    RECEIPT_PATTERN = re.compile(r"\b([A-Z]{2,3}\d{7,12})\b")
    AMOUNT_PATTERN = re.compile(
        r"(?:Ksh\.?|KES)\s*([\d,]+\.?\d{0,2})", re.IGNORECASE
    )
    PLAIN_AMOUNT_PATTERN = re.compile(r"\b([\d,]{1,12}\.\d{2})\b")
    PHONE_PATTERN = re.compile(r"(?:\+254|0)([17]\d{8})")

    DATE_PATTERNS = [
        re.compile(r"(\d{1,2}/\d{1,2}/\d{4})\s+(\d{1,2}:\d{2}\s*[AP]M)"),
        re.compile(r"(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})"),
        re.compile(r"(\d{1,2}/\d{1,2}/\d{4})\s+(\d{2}:\d{2}:\d{2})"),
    ]

    DATE_FORMATS = [
        "%d/%m/%Y %I:%M %p",
        "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    ]

    TYPE_KEYWORDS: Dict[TransactionType, List[str]] = {
        TransactionType.SENT: ["sent to", "transfer to", "send money"],
        TransactionType.RECEIVED: ["received from", "you have received"],
        TransactionType.PAYBILL: ["paybill", "pay bill", "utility"],
        TransactionType.TILL: ["buy goods", "till number", "merchant"],
        TransactionType.AIRTIME: ["airtime", "top up", "topup"],
        TransactionType.WITHDRAWAL: ["withdraw", "cash out", "agent"],
        TransactionType.DEPOSIT: ["deposit", "cash in"],
        TransactionType.REVERSAL: ["reversal", "reversed"],
        TransactionType.FULIZA: ["fuliza"],
        TransactionType.LOAN: ["mshwari", "kcb mpesa", "loan"],
        TransactionType.CHARGES: ["charge", "fee", "service fee"],
    }

    def parse(self, text_content: str) -> ParsedStatement:
        """Main parsing entry point."""
        statement = ParsedStatement()

        if not text_content:
            statement.parsing_warnings.append("Empty content")
            return statement

        lines = [l.strip() for l in text_content.split("\n") if l.strip()]
        statement.raw_lines_processed = len(lines)

        # Extract metadata
        statement.metadata = self._extract_metadata(text_content)

        # Parse transactions
        if self._is_tabular(text_content):
            statement.transactions = self._parse_tabular(
                lines, statement.parsing_warnings
            )
        else:
            statement.transactions = self._parse_text(
                lines, statement.parsing_warnings
            )

        # Post-process
        statement.transactions = self._deduplicate(
            statement.transactions, statement.parsing_warnings
        )
        statement.transactions.sort(
            key=lambda t: t.completion_time or datetime.min
        )

        statement.metadata.transaction_count = len(statement.transactions)
        self._calculate_totals(statement)

        logger.info(
            f"Parsed {len(statement.transactions)} transactions, "
            f"{len(statement.parsing_warnings)} warnings"
        )

        return statement

    def _extract_metadata(self, text: str) -> StatementMetadata:
        meta = StatementMetadata()

        name_match = re.search(
            r"(?:Customer Name|Account Name|Name)\s*:?\s*"
            r"([A-Z][A-Z\s]+[A-Z])",
            text,
            re.IGNORECASE,
        )
        if name_match:
            meta.account_name = name_match.group(1).strip().title()

        phone_match = self.PHONE_PATTERN.search(text)
        if phone_match:
            meta.phone_number = f"+254{phone_match.group(1)}"

        period_match = re.search(
            r"(?:Statement Period|Period)\s*:?\s*"
            r"(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})\s*(?:to|-)?\s*"
            r"(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})",
            text,
            re.IGNORECASE,
        )
        if period_match:
            try:
                meta.statement_period_start = self._parse_date(
                    period_match.group(1)
                )
                meta.statement_period_end = self._parse_date(
                    period_match.group(2)
                )
            except Exception:
                pass

        return meta

    def _is_tabular(self, text: str) -> bool:
        tab_lines = sum(1 for line in text.split("\n") if "\t" in line)
        return tab_lines > 5

    def _parse_tabular(
        self, lines: List[str], warnings: List[str]
    ) -> List[MPesaTransaction]:
        transactions = []
        header_found = False
        col_map: Dict[str, int] = {}

        for line_num, line in enumerate(lines):
            if "\t" not in line:
                continue

            cols = [c.strip() for c in line.split("\t")]

            if not header_found:
                col_map = self._detect_columns(cols)
                if col_map:
                    header_found = True
                    continue

            if not header_found or len(cols) < 3:
                continue

            try:
                txn = self._parse_table_row(cols, col_map)
                if txn and txn.receipt_no:
                    transactions.append(txn)
            except Exception as e:
                warnings.append(f"Row {line_num}: {str(e)[:50]}")

        return transactions

    def _detect_columns(self, headers: List[str]) -> Dict[str, int]:
        mapping: Dict[str, int] = {}
        column_keywords = {
            "receipt_no": ["receipt", "transaction id", "ref"],
            "completion_time": ["completion time", "date", "time"],
            "description": ["description", "details", "narration"],
            "paid_in": ["paid in", "credit", "money in"],
            "withdrawn": ["withdrawn", "debit", "money out"],
            "balance": ["balance", "running balance"],
        }

        for idx, header in enumerate(headers):
            h_lower = header.lower().strip()
            for field_name, keywords in column_keywords.items():
                if any(kw in h_lower for kw in keywords):
                    if field_name not in mapping:
                        mapping[field_name] = idx

        has_required = "receipt_no" in mapping or "completion_time" in mapping
        return mapping if has_required else {}

    def _parse_table_row(
        self, cols: List[str], col_map: Dict[str, int]
    ) -> Optional[MPesaTransaction]:
        def get_col(name: str) -> str:
            idx = col_map.get(name)
            if idx is not None and idx < len(cols):
                return cols[idx].strip()
            return ""

        receipt = get_col("receipt_no")
        if receipt and not self.RECEIPT_PATTERN.match(receipt):
            row_text = " ".join(cols)
            m = self.RECEIPT_PATTERN.search(row_text)
            receipt = m.group(1) if m else receipt

        if not receipt:
            return None

        txn = MPesaTransaction(receipt_no=receipt)
        txn.description = get_col("description")
        txn.paid_in = self._parse_amount(get_col("paid_in"))
        txn.withdrawn = self._parse_amount(get_col("withdrawn"))
        txn.balance = self._parse_amount(get_col("balance"))
        txn.transaction_type = self._classify(txn.description)
        txn.counterparty = self._extract_counterparty(txn.description)

        time_str = get_col("completion_time")
        if time_str:
            txn.completion_time = self._parse_date(time_str)

        return txn

    def _parse_text(
        self, lines: List[str], warnings: List[str]
    ) -> List[MPesaTransaction]:
        transactions = []
        i = 0

        while i < len(lines):
            receipt_match = self.RECEIPT_PATTERN.search(lines[i])

            if receipt_match:
                context = [lines[i]]
                for j in range(1, 4):
                    if i + j < len(lines):
                        nl = lines[i + j]
                        if self.RECEIPT_PATTERN.search(nl):
                            break
                        context.append(nl)

                try:
                    txn = self._parse_text_transaction(
                        receipt_match.group(1), context
                    )
                    if txn:
                        transactions.append(txn)
                except Exception as e:
                    warnings.append(f"Line {i}: {str(e)[:50]}")

            i += 1

        return transactions

    def _parse_text_transaction(
        self, receipt_no: str, lines: List[str]
    ) -> Optional[MPesaTransaction]:
        combined = " ".join(lines)
        txn = MPesaTransaction(
            receipt_no=receipt_no, description=combined[:200]
        )

        # Extract datetime
        for pattern in self.DATE_PATTERNS:
            m = pattern.search(combined)
            if m:
                txn.completion_time = self._parse_date(
                    f"{m.group(1)} {m.group(2)}"
                )
                if txn.completion_time:
                    break

        # Extract amounts
        amounts = self.AMOUNT_PATTERN.findall(combined)
        if not amounts:
            amounts = self.PLAIN_AMOUNT_PATTERN.findall(combined)

        parsed_amts = [
            self._parse_amount(a) for a in amounts if self._parse_amount(a)
        ]

        if "received" in combined.lower() or "paid in" in combined.lower():
            if parsed_amts:
                txn.paid_in = parsed_amts[0]
            if len(parsed_amts) > 1:
                txn.balance = parsed_amts[-1]
        else:
            if parsed_amts:
                txn.withdrawn = parsed_amts[0]
            if len(parsed_amts) > 1:
                txn.balance = parsed_amts[-1]

        txn.transaction_type = self._classify(combined)
        txn.counterparty = self._extract_counterparty(combined)

        return txn

    def _classify(self, description: str) -> TransactionType:
        desc_lower = description.lower()
        for txn_type, keywords in self.TYPE_KEYWORDS.items():
            if any(kw in desc_lower for kw in keywords):
                return txn_type
        return TransactionType.OTHER

    def _extract_counterparty(self, description: str) -> str:
        patterns = [
            r"(?:to|from)\s+([A-Z][A-Z\s]+?)(?:\s+on|\s+via|$)",
            r"(?:to|from)\s+(\+?254\d{9})",
            r"(?:to|from)\s+(0[17]\d{8})",
        ]
        for pattern in patterns:
            m = re.search(pattern, description, re.IGNORECASE)
            if m:
                return m.group(1).strip()[:50]
        return ""

    def _parse_amount(self, amount_str: str) -> Optional[Decimal]:
        if not amount_str:
            return None
        try:
            cleaned = re.sub(r"[Ksh\s]", "", str(amount_str))
            cleaned = cleaned.replace(",", "")
            if not cleaned or cleaned == "-":
                return None
            value = Decimal(cleaned)
            return value if value >= 0 else None
        except (InvalidOperation, ValueError):
            return None

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        if not date_str:
            return None

        normalized = re.sub(r"\s+", " ", date_str.strip())
        normalized = re.sub(
            r"(\d)([AP]M)", r"\1 \2", normalized, flags=re.IGNORECASE
        )

        for fmt in self.DATE_FORMATS:
            try:
                return datetime.strptime(normalized, fmt)
            except ValueError:
                continue

        try:
            from dateutil import parser as dateutil_parser
            return dateutil_parser.parse(normalized, dayfirst=True)
        except Exception:
            return None

    def _deduplicate(
        self, transactions: List[MPesaTransaction], warnings: List[str]
    ) -> List[MPesaTransaction]:
        seen: set = set()
        unique: List[MPesaTransaction] = []
        for txn in transactions:
            if txn.receipt_no in seen:
                warnings.append(f"Duplicate {txn.receipt_no} removed")
                continue
            seen.add(txn.receipt_no)
            unique.append(txn)
        return unique

    def _calculate_totals(self, statement: ParsedStatement) -> None:
        total_in = Decimal("0")
        total_out = Decimal("0")
        for txn in statement.transactions:
            if txn.paid_in:
                total_in += txn.paid_in
            if txn.withdrawn:
                total_out += txn.withdrawn
        statement.metadata.total_paid_in = total_in
        statement.metadata.total_withdrawn = total_out