import re

from app.parameters.schema import ExtractedField
from app.parameters.synonyms import normalize_label
from app.parsing.schema import ParsedElement

# Matches "<label>: <value>" or "<label> - <value>" on a single line, e.g.
# "PO Number: PO-45892", "Part No. ABC-123".
LABEL_VALUE_RE = re.compile(
    r"^\s*(?P<label>[A-Za-z][A-Za-z0-9 ./]{1,30}?)\s*[:\-]\s*(?P<value>.+?)\s*$"
)

# PO numbers frequently appear mid-sentence in certifying prose rather than
# on their own labeled line, e.g. "...against your Po no.06L035807/ANIL
# POOJARI..." or "...purchase Order PO.NO. 06L038682 / ANIL POOJARI...".
# \W{0,n} tolerates the '.', ' ' variations vendors use between P/O/No.
PO_NUMBER_RE = re.compile(r"P\W{0,2}O\W{0,2}No\W{0,3}([A-Za-z0-9]{5,})", re.IGNORECASE)


def extract_inline_fields(elements: list[ParsedElement]) -> list[ExtractedField]:
    """Deterministic label:value extraction for critical identifiers (PO,
    Part ID, Model, Serial, Quantity) that appear inline rather than in a
    table — e.g. a COC's letterhead prose."""
    fields: list[ExtractedField] = []

    for el in elements:
        for line in el.text.splitlines():
            m = LABEL_VALUE_RE.match(line)
            if not m:
                continue

            canonical = normalize_label(m.group("label"))
            if not canonical:
                continue

            value = m.group("value").strip()
            if not value:
                continue

            fields.append(
                ExtractedField(
                    field_name=canonical,
                    field_value=value,
                    page_number=el.page_number,
                    bbox=el.bbox,
                    extraction_method="inline",
                    raw_label=m.group("label").strip(),
                )
            )

    return fields


def extract_po_fallback(elements: list[ParsedElement]) -> list[ExtractedField]:
    """Pulls a PO number out of prose when it isn't on its own labeled line
    (see PO_NUMBER_RE). Supplements extract_inline_fields/extract_coc_table_fields,
    doesn't replace them."""
    fields: list[ExtractedField] = []

    for el in elements:
        m = PO_NUMBER_RE.search(el.text)
        if not m:
            continue

        fields.append(
            ExtractedField(
                field_name="po_numbers",
                field_value=m.group(1).strip(),
                page_number=el.page_number,
                bbox=el.bbox,
                extraction_method="inline",
                raw_label="PO No.",
            )
        )

    return fields
