from typing import TYPE_CHECKING

from app.validation import rules

if TYPE_CHECKING:
    from app.parameters.schema import BOMItem, ExtractedField

FUZZY_TEXT_FIELDS = ["description"]
EXACT_TEXT_FIELDS = ["manufacturer", "manufacturing_year", "warranty_expiry", "coc_issue_date"]
PRESENCE_FIELDS = ["signature", "seal", "test_certificate", "import_documents", "authorization_letter"]

# Canonical field name -> BOMItem attribute, where they differ.
_ATTR_ALIASES = {"po_numbers": "po_number"}


def _first_value(fields: "list[ExtractedField]", field_name: str) -> "ExtractedField | None":
    matches = [f for f in fields if f.field_name == field_name]
    return matches[0] if matches else None


def _bom_expected(bom_item: "BOMItem | None", field_name: str) -> str | None:
    """Dedicated BOMItem attributes cover part_id/description/manufacturer/
    model/quantity/po_number; anything else (YOM, warranty, issue date...)
    only exists if that column was present on this particular BOM, captured
    in `requirements`. Returns None with no BOM match at all — every rule
    already treats a missing expected value as 'nothing to validate
    against' rather than crashing, so a COC can still be checked
    field-by-field even when no BOM line matched it."""
    if bom_item is None:
        return None
    attr = _ATTR_ALIASES.get(field_name, field_name)
    if hasattr(bom_item, attr):
        value = getattr(bom_item, attr)
        return str(value) if value is not None else None
    return bom_item.requirements.get(field_name)


def run_validation(bom_item: "BOMItem | None", coc_fields: "list[ExtractedField]") -> list[dict]:
    """Validates the full canonical field set against the matched BOM line:
    identity-field presence, PO Number, Part ID, Model, Serial Number,
    Quantity, Description, Manufacturer, Manufacturing Year, Warranty
    Expiry, COC Issue Date, plus presence checks for Signature, Seal, Test
    Certificate, Import Documents, and Authorization Letter. Each result
    carries the source ExtractedField (when matched) so the caller can
    highlight it on the PDF.

    Returns a list of dicts: {rule_result, source_field}.
    """
    results: list[dict] = []

    po_field = _first_value(coc_fields, "po_numbers")
    part_id_field = _first_value(coc_fields, "part_id")
    model_field = _first_value(coc_fields, "model")
    serial_field = _first_value(coc_fields, "serial_numbers")
    qty_field = _first_value(coc_fields, "quantity")

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
        "rule_result": rules.check_quantity(_bom_expected_quantity(bom_item), qty_field.field_value if qty_field else None),
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


def _bom_expected_quantity(bom_item: "BOMItem | None") -> float | None:
    return bom_item.quantity if bom_item is not None else None
