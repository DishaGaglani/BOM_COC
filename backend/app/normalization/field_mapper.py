import re

from app.normalization.synonyms import FIELD_SYNONYMS
from app.schemas.canonical import RawTextBlock, ExtractedField

# Matches "<label>: <value>" or "<label> - <value>" within a single line,
# e.g. "PO Number: PO-45892", "Part No. ABC-123".
LABEL_VALUE_RE = re.compile(
    r"^\s*(?P<label>[A-Za-z][A-Za-z0-9 ./]{1,30}?)\s*[:\-]\s*(?P<value>.+?)\s*$"
)

# PO numbers frequently appear mid-sentence in certifying prose rather than
# on their own labeled line, e.g. "...against your Po no.06L035807/ANIL
# POOJARI..." or "...purchase Order PO.NO. 06L038682 / ANIL POOJARI...".
# \W{0,n} tolerates the '.', ' ' variations vendors use between P/O/No.
PO_NUMBER_RE = re.compile(r"P\W{0,2}O\W{0,2}No\W{0,3}([A-Za-z0-9]{5,})", re.IGNORECASE)


def extract_rule_based_fields(blocks: list[RawTextBlock]) -> list[ExtractedField]:
    """Deterministic label:value extraction for critical identifiers (PO,
    Part ID, Model, Serial, Quantity). Runs alongside the LLM extractor;
    the validation engine prefers this for exact-match fields per the
    hybrid validation strategy (architecture doc section 10)."""
    fields: list[ExtractedField] = []

    for block in blocks:
        m = LABEL_VALUE_RE.match(block.text)
        if not m:
            continue

        label = m.group("label").strip().lower().rstrip(":")
        canonical = FIELD_SYNONYMS.get(label)
        if not canonical:
            continue

        value = m.group("value").strip()
        if not value:
            continue

        fields.append(
            ExtractedField(
                field_name=canonical,
                field_value=value,
                confidence=block.confidence,
                page=block.page,
                bbox=block.bbox,
                extraction_method="rule",
                raw_label=m.group("label").strip(),
            )
        )

    return fields


def extract_po_fallback(blocks: list[RawTextBlock]) -> list[ExtractedField]:
    """Pulls a PO number out of prose when it isn't on its own labeled
    line (see PO_NUMBER_RE). Only meant to supplement extract_rule_based_
    fields and extract_table_fields, not replace them."""
    fields: list[ExtractedField] = []

    for block in blocks:
        m = PO_NUMBER_RE.search(block.text)
        if not m:
            continue

        fields.append(
            ExtractedField(
                field_name="po_numbers",
                field_value=m.group(1).strip(),
                confidence=block.confidence,
                page=block.page,
                bbox=block.bbox,
                extraction_method="rule",
                raw_label="PO No.",
            )
        )

    return fields
