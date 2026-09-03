from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from app.parsing.schema import BBox

# Canonical fields shared by BOM items and COC extraction (architecture doc
# section 7). Document type itself isn't extracted — it's implicit in which
# endpoint (/api/boms vs /api/boms/{bom_id}/cocs) a file went through.
CANONICAL_FIELDS = [
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
    # BOM/project-level context fields (not compliance-highlight fields
    # themselves): contract_date gates the coc_issue_date check,
    # is_imported gates whether import_documents is actually required.
    "contract_date",
    "is_imported",
]

ExtractionMethod = Literal["semantic"]
BOMStatus = Literal["active", "superseded"]
ValidationStatus = Literal["PASS", "FAIL", "WARNING"]


class ExtractedField(BaseModel):
    field_name: str  # one of CANONICAL_FIELDS
    field_value: str
    page_number: int | None = None
    bbox: BBox | None = None
    extraction_method: ExtractionMethod
    raw_label: str | None = None  # original document term, e.g. "P/N"
    # How much this specific extraction should be trusted, 0-1 — set by the
    # semantic extraction agent (see services/semantic_extractor.py). Used
    # to pick a winner when multiple extractions disagree on the same field.
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


# --- BOM: fixed-column line items, matching the frontend's BOMItem shape ---


class BOMItem(BaseModel):
    item_id: str
    part_id: str | None = None
    description: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    quantity: float | None = None
    po_number: str | None = None
    # Anything else a table column mapped to (YOM, warranty, coc_issue_date,
    # ...) that doesn't have its own dedicated column above.
    requirements: dict[str, str] = Field(default_factory=dict)
    page_number: int | None = None


class BOM(BaseModel):
    bom_id: str
    project_id: str
    parsed_document_id: str
    filename: str
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    version: int
    status: BOMStatus
    items: list[BOMItem]
    # The contract/effective date a COC's issue date gets checked against
    # (requirement #10) — a BOM/project-level fact, not a per-item one.
    # Either supplied explicitly on upload or extracted from the BOM
    # document's own text; None if neither found it.
    contract_date: str | None = None


# --- COC: flat extracted fields + validation results against a matched BOM item ---


class Validation(BaseModel):
    parameter: str
    expected_value: str | None
    actual_value: str | None
    status: ValidationStatus
    reason: str | None


class COC(BaseModel):
    coc_id: str
    bom_id: str
    parsed_document_id: str
    filename: str
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    document_type: str = "coc"
    status: str = "validated"
    matched_item_id: str | None = None
    fields: list[ExtractedField]
    validations: list[Validation]


class ReportRow(BaseModel):
    parameter: str
    expected: str | None
    actual: str | None
    status: ValidationStatus
    reason: str | None


class Report(BaseModel):
    coc_id: str
    filename: str
    overall_status: ValidationStatus
    rows: list[ReportRow]
