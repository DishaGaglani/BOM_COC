import re

from app.parameters.schema import ExtractedField
from app.parsing.schema import ParsedElement

# Keyword presence checks for COC compliance elements that can't be pulled as
# a clean label:value pair — signatures/seals are visual marks, not table
# fields, and attached-document mentions are prose, not table cells. This is
# a text presence check, not real signature/seal image detection: a scanned
# COC with no OCR text on that page will never match here even if a real
# signature is physically on it.
PRESENCE_PATTERNS: dict[str, re.Pattern] = {
    "signature": re.compile(r"authoris?ed\s+signatory|signature|signed\s+by", re.IGNORECASE),
    "seal": re.compile(r"\b(company|official)\s+(seal|stamp)\b|\bseal\b", re.IGNORECASE),
    "test_certificate": re.compile(r"test\s+certificate|test\s+report|type\s+test|\btc\s*no\b", re.IGNORECASE),
    "import_documents": re.compile(r"bill\s+of\s+entry|import\s+licen[cs]e|customs\s+clearance|import\s+document", re.IGNORECASE),
    "authorization_letter": re.compile(r"authoris?ation\s+letter|letter\s+of\s+authoris?ation", re.IGNORECASE),
}


def extract_presence_fields(elements: list[ParsedElement]) -> list[ExtractedField]:
    """Flags compliance elements mentioned anywhere in the document's text."""
    fields: list[ExtractedField] = []
    found: set[str] = set()

    for el in elements:
        for field_name, pattern in PRESENCE_PATTERNS.items():
            if field_name in found:
                continue
            m = pattern.search(el.text)
            if not m:
                continue
            found.add(field_name)
            fields.append(
                ExtractedField(
                    field_name=field_name,
                    field_value=m.group(0).strip(),
                    page_number=el.page_number,
                    bbox=el.bbox,
                    extraction_method="presence",
                )
            )

    return fields
