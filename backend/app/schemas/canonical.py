from typing import Optional, Literal
from pydantic import BaseModel

# Canonical fields shared by BOM items and COC extraction (architecture doc section 7)
CANONICAL_FIELDS = [
    "document_type",
    "po_numbers",
    "part_id",
    "description",
    "manufacturer",
    "model",
    "serial_numbers",
    "quantity",
    "manufacturing_year",
    "warranty_expiry",
    "coc_issue_date",
    "signature",
    "seal",
    "test_certificate",
    "import_documents",
    "authorization_letter",
]

ExtractionMethod = Literal["table", "ocr", "llm", "rule"]


class BBox(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float


class RawTextBlock(BaseModel):
    """One unit of extracted text before semantic mapping: a table cell,
    an OCR word/line, or a paragraph, with its location on the page."""

    page: int
    text: str
    bbox: Optional[BBox] = None
    source: ExtractionMethod
    confidence: float = 1.0


class ExtractedField(BaseModel):
    """A single canonical field extracted from a document, ready for
    normalization and validation. Mirrors the COC_ENTITIES table shape."""

    field_name: str  # one of CANONICAL_FIELDS
    field_value: str
    confidence: float = 1.0
    page: Optional[int] = None
    bbox: Optional[BBox] = None
    extraction_method: ExtractionMethod = "rule"
    raw_label: Optional[str] = None  # original document term, e.g. "P/N"


class DocumentExtractionResult(BaseModel):
    filename: str
    is_scanned: bool
    page_count: int
    raw_blocks: list[RawTextBlock]
    fields: list[ExtractedField] = []
