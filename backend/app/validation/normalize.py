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


def normalize_identifier_loose(value: str | None) -> str:
    """Alphanumeric-only comparison for identifiers — strips ALL punctuation
    and whitespace, tolerating the formatting noise vendors introduce
    ('PO-45892' vs 'PO45892' vs 'PO 45892') that normalize_identifier()
    treats as a mismatch since it deliberately keeps separators significant.
    Used only as a fallback when the strict compare fails: dropping every
    separator could coincidentally make two genuinely different identifiers
    equal, so callers should treat a loose-only match as a lower-confidence
    signal, not as trustworthy as an exact one."""
    if not value:
        return ""
    return re.sub(r"[^A-Za-z0-9]", "", value).upper()


def parse_quantity(value: str) -> float | None:
    if value is None:
        return None
    match = re.search(r"-?\d+(\.\d+)?", str(value).replace(",", ""))
    return float(match.group()) if match else None


_ISO_LIKE_DATE_RE = re.compile(r"^(?P<year>\d{4})[-/](?P<month>\d{2})[-/](?P<day>\d{2})$")


def parse_date(value: str | None) -> date | None:
    """Best-effort date parsing for free-text extracted dates (e.g. 'Date
    of Issue: 12th August 2026', '12/08/2026'). `dayfirst=True` since these
    documents are in an Indian business context (DD/MM/YYYY convention);
    `fuzzy=True` tolerates surrounding words the regex-based extractors
    didn't strip out.

    A bare YYYY-MM-DD/YYYY/MM/DD string is parsed directly first: dateutil
    applies `dayfirst` to the first ambiguous field after the leading year,
    which for an ISO-ordered string means it can swap month and day (e.g.
    '2026-08-12' -> Dec 8 instead of Aug 12) even though the leading 4-digit
    year makes the field order unambiguous. Only reached for machine-shaped
    dates; DD/MM/YYYY and prose dates fall through to dayfirst/fuzzy as
    before.
    """
    if not value:
        return None
    text = value.strip()

    iso_match = _ISO_LIKE_DATE_RE.match(text)
    if iso_match:
        try:
            return date(int(iso_match["year"]), int(iso_match["month"]), int(iso_match["day"]))
        except ValueError:
            pass  # fall through to the general parser below

    try:
        return dateutil_parser.parse(text, dayfirst=True, fuzzy=True).date()
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
