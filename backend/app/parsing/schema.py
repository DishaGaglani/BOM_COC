from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class BBox(BaseModel):
    """Axis-aligned box in unstructured's layout-image pixel space, plus the
    image dimensions it was measured against. Not yet in PDF point space —
    the annotator converts using the real page size at highlight time, since
    layout images are rendered at whatever DPI unstructured chose."""

    x0: float
    y0: float
    x1: float
    y1: float
    layout_width: float | None = None
    layout_height: float | None = None


class ParsedElement(BaseModel):
    element_id: str
    type: str
    text: str
    html: str | None = None
    page_number: int | None = None
    bbox: BBox | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ParsedTable(BaseModel):
    element_id: str
    page_number: int | None = None
    html: str | None = None
    text: str
    bbox: BBox | None = None


class ParsedDocument(BaseModel):
    document_id: str
    filename: str
    original_extension: str
    stored_path: str
    strategy_used: str
    element_count: int
    table_count: int
    elements: list[ParsedElement]
    tables: list[ParsedTable]
    full_text: str
    warnings: list[str] = Field(default_factory=list)
    parsed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ParsedDocumentSummary(BaseModel):
    document_id: str
    filename: str
    element_count: int
    table_count: int
    strategy_used: str
    parsed_at: datetime
