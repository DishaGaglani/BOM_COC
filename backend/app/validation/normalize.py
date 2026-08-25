import re
from datetime import date

from dateutil import parser as dateutil_parser


def normalize_identifier(value: str) -> str:
    """Light normalization for exact-match identifiers (PO, Part ID, Model,
    Serial): trims, uppercases, and collapses internal whitespace, but does
    NOT strip separators like '-' since those are often significant in
    part/PO numbering schemes."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", value.strip()).upper()


def parse_quantity(value: str) -> float | None:
    if value is None:
        return None
    match = re.search(r"-?\d+(\.\d+)?", str(value).replace(",", ""))
    return float(match.group()) if match else None


def parse_date(value: str | None) -> date | None:
    """Best-effort date parsing for free-text extracted dates (e.g. 'Date
    of Issue: 12th August 2026', '12/08/2026'). `dayfirst=True` since these
    documents are in an Indian business context (DD/MM/YYYY convention);
    `fuzzy=True` tolerates surrounding words the regex-based extractors
    didn't strip out."""
    if not value:
        return None
    try:
        return dateutil_parser.parse(value, dayfirst=True, fuzzy=True).date()
    except (ValueError, OverflowError, TypeError):
        return None


_TRUTHY = {"yes", "y", "true", "1", "imported"}
_FALSY = {"no", "n", "false", "0", "domestic", "not imported", "n/a", "na"}


def parse_bool_flag(value: str | None) -> bool | None:
    """Interprets a free-text yes/no-ish BOM column value (e.g. an
    'Imported' column). Returns None — not False — when the value doesn't
    match a known pattern, so the caller can distinguish 'confirmed not
    imported' from 'couldn't tell'."""
    if not value:
        return None
    key = value.strip().lower()
    if key in _TRUTHY:
        return True
    if key in _FALSY:
        return False
    return None
