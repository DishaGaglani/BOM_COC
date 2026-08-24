from typing import TYPE_CHECKING

from app.validation.normalize import normalize_identifier

if TYPE_CHECKING:
    from app.parameters.schema import BOMItem, ExtractedField


def match_bom_item(items: "list[BOMItem]", coc_fields: "list[ExtractedField]") -> "BOMItem | None":
    """Matches a COC to a BOM line item by Part ID first, then PO Number,
    using normalized exact match."""
    part_id_values = [f.field_value for f in coc_fields if f.field_name == "part_id"]
    po_values = [f.field_value for f in coc_fields if f.field_name == "po_numbers"]

    for item in items:
        if item.part_id and any(normalize_identifier(item.part_id) == normalize_identifier(v) for v in part_id_values):
            return item
    for item in items:
        if item.po_number and any(normalize_identifier(item.po_number) == normalize_identifier(v) for v in po_values):
            return item
    return None


def overall_status(statuses: list[str]) -> str:
    if "FAIL" in statuses:
        return "FAIL"
    if "WARNING" in statuses:
        return "WARNING"
    return "PASS"
