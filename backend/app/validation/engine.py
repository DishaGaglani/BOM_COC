from typing import TYPE_CHECKING

from app.schemas.canonical import ExtractedField
from app.validation import rules

if TYPE_CHECKING:
    from app.db.models import BOMItem


def _first_value(fields: list[ExtractedField], field_name: str) -> ExtractedField | None:
    matches = [f for f in fields if f.field_name == field_name]
    if not matches:
        return None
    return max(matches, key=lambda f: f.confidence)


FUZZY_TEXT_FIELDS = ["description"]
EXACT_TEXT_FIELDS = ["manufacturer", "manufacturing_year", "warranty_expiry", "coc_issue_date"]
PRESENCE_FIELDS = ["signature", "seal", "test_certificate", "import_documents", "authorization_letter"]


# Canonical field name -> BOMItem attribute, where they differ.
_ATTR_ALIASES = {"po_numbers": "po_number"}


def _bom_expected(bom_item: "BOMItem | None", field_name: str) -> str | None:
    """Dedicated BOMItem columns cover part_id/description/manufacturer/
    model/quantity/po_number; anything else (YOM, warranty, issue date...)
    only exists if that column was present on this particular BOM, captured
    in requirements (bom_service.ingest_bom stores every unmapped-to-a-
    dedicated-column field there). Returns None with no BOM match at all —
    every rule already treats a missing expected value as 'nothing to
    validate against' rather than crashing, so a COC can still be checked
    field-by-field even when no BOM line matched it."""
    if bom_item is None:
        return None
    attr = _ATTR_ALIASES.get(field_name, field_name)
    if hasattr(bom_item, attr):
        return getattr(bom_item, attr)
    return (getattr(bom_item, "requirements", None) or {}).get(field_name)


def run_validation(bom_item: "BOMItem | None", coc_fields: list[ExtractedField]) -> list[dict]:
    """Validates the full canonical field set against the matched BOM line:
    document type, identity-field presence, PO Number, Part ID, Model,
    Serial Number, Quantity, Description, Manufacturer, Manufacturing Year,
    Warranty Expiry, COC Issue Date, plus presence checks for Signature,
    Seal, Test Certificate, Import Documents, and Authorization Letter.
    Each result carries the source ExtractedField (when matched) so the
    caller can create the matching Annotation row for PDF highlighting.

    Returns a list of dicts: {rule_result, source_field}.
    """
    results: list[dict] = []

    doc_type_field = _first_value(coc_fields, "document_type")
    po_field = _first_value(coc_fields, "po_numbers")
    part_id_field = _first_value(coc_fields, "part_id")
    model_field = _first_value(coc_fields, "model")
    serial_field = _first_value(coc_fields, "serial_numbers")
    qty_field = _first_value(coc_fields, "quantity")

    results.append({"rule_result": rules.check_document_type(doc_type_field.field_value if doc_type_field else None), "source_field": doc_type_field})

    results.append({
        "rule_result": rules.check_identity_field_presence(
            po_field.field_value if po_field else None,
            serial_field.field_value if serial_field else None,
        ),
        "source_field": None,
    })

    results.append({
        "rule_result": rules.check_exact_match("po_numbers", _bom_expected(bom_item, "po_numbers"), po_field.field_value if po_field else None, required=False),
        "source_field": po_field,
    })

    results.append({
        "rule_result": rules.check_exact_match("part_id", _bom_expected(bom_item, "part_id"), part_id_field.field_value if part_id_field else None, required=False),
        "source_field": part_id_field,
    })

    results.append({
        "rule_result": rules.check_exact_match("model", _bom_expected(bom_item, "model"), model_field.field_value if model_field else None, required=False),
        "source_field": model_field,
    })

    results.append({
        "rule_result": rules.check_exact_match("serial_numbers", None, serial_field.field_value if serial_field else None, required=False),
        "source_field": serial_field,
    })

    results.append({
        "rule_result": rules.check_quantity(_bom_expected(bom_item, "quantity"), qty_field.field_value if qty_field else None),
        "source_field": qty_field,
    })

    for field_name in FUZZY_TEXT_FIELDS:
        field = _first_value(coc_fields, field_name)
        results.append({
            "rule_result": rules.check_fuzzy_match(field_name, _bom_expected(bom_item, field_name), field.field_value if field else None),
            "source_field": field,
        })

    for field_name in EXACT_TEXT_FIELDS:
        field = _first_value(coc_fields, field_name)
        results.append({
            "rule_result": rules.check_exact_match(field_name, _bom_expected(bom_item, field_name), field.field_value if field else None, required=False),
            "source_field": field,
        })

    for field_name in PRESENCE_FIELDS:
        field = _first_value(coc_fields, field_name)
        results.append({
            "rule_result": rules.check_presence(field_name, field.field_value if field else None),
            "source_field": field,
        })

    return results
