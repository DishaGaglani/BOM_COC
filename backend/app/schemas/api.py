from datetime import datetime
from pydantic import BaseModel


class BOMItemOut(BaseModel):
    item_id: str
    part_id: str | None
    description: str | None
    manufacturer: str | None
    model: str | None
    quantity: float | None
    po_number: str | None

    class Config:
        from_attributes = True


class BOMOut(BaseModel):
    bom_id: str
    project_id: str
    filename: str
    uploaded_at: datetime
    version: int
    status: str
    items: list[BOMItemOut] = []

    class Config:
        from_attributes = True


class ValidationOut(BaseModel):
    parameter: str
    expected_value: str | None
    actual_value: str | None
    status: str
    reason: str | None

    class Config:
        from_attributes = True


class COCOut(BaseModel):
    coc_id: str
    bom_id: str
    filename: str
    uploaded_at: datetime
    document_type: str
    status: str
    validations: list[ValidationOut] = []

    class Config:
        from_attributes = True


class ReportRow(BaseModel):
    parameter: str
    expected: str | None
    actual: str | None
    status: str
    reason: str | None


class ReportOut(BaseModel):
    coc_id: str
    filename: str
    overall_status: str
    rows: list[ReportRow]
