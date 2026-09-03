from typing import TYPE_CHECKING

from app.validation import rules
from app.validation.normalize import parse_bool_flag

if TYPE_CHECKING:
    from app.parameters.schema import BOMItem, ExtractedField

FUZZY_TEXT_FIELDS = ["description"]
EXACT_TEXT_FIELDS = ["manufacturer", "manufacturing_year", "warranty_expiry"]
# coc_issue_date (checked against contract_date) and import_documents
# (gated on is_imported) get dedicated handling below instead of the
# generic exact-match/presence loops — see check_date_not_before and
# check_conditional_presence.
PRESENCE_FIELDS = ["signature", "seal", "test_certificate", "authorization_letter"]

# Canonical field name -> BOMItem attribute, where they differ.
_ATTR_ALIASES = {"po_numbers": "po_number"}


def _best_value(fields: "list[ExtractedField]", field_name: str) -> "ExtractedField | None":
    """When multiple extractions disagree on the same canonical field (e.g.
    a PO number found both in a table cell and in letterhead prose), the
    higher-confidence one wins — see parameters/confidence.py."""
    matches = [f for f in fields if f.field_name == field_name]
    if not matches:
        return None
    return max(matches, key=lambda f: f.confidence)


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


def run_validation(
    bom_item: "BOMItem | None",
    coc_fields: "list[ExtractedField]",
    contract_date: str | None = None,
    previously_delivered_quantity: float = 0.0,
) -> list[dict]:
    """Validates the full canonical field set against the matched BOM line:
    identity-field presence, PO Number, Part ID, Model, Serial Number,
    Quantity, Description, Manufacturer, Manufacturing Year, Warranty
    Expiry, COC Issue Date (vs. the BOM's contract_date), plus presence
    checks for Signature, Seal, Test Certificate, Import Documents (gated
    on the BOM's is_imported), and Authorization Letter. Each result
    carries the source ExtractedField (when matched) so the caller can
    highlight it on the PDF.

    `contract_date` is BOM/project-level (see parameters.schema.BOM), not
    per-item, so it's passed separately rather than read off bom_item.
    `previously_delivered_quantity` is the sum already validated on other
    COCs matched to the same BOM line, for partial-shipment quantity checks
    (see rules.check_quantity).

    A field-comparison check (PO Number, Part ID, Model, Serial Number,
    Quantity, COC Issue Date, Description, Manufacturer, Manufacturing
    Year, Warranty Expiry) is skipped entirely — no row at all, not even a
    WARNING — when the BOM side has nothing to compare against (no matched
    line, or the matched line never captured that field). Reporting "no
    BOM value to validate against" for every such field on an unmatched
    COC used to bury the one row that actually matters (bom_match) under a
    wall of noise; this way the report only ever shows a comparison that
    could meaningfully pass, fail, or need review. Checks that don't
    depend on a BOM value at all — identity-field presence, and the
    presence-only compliance markers (signature, seal, test certificate,
    authorization letter) — always run regardless, since they're purely
    about what the COC itself contains.

    Returns a list of dicts: {rule_result, source_field}.
    """
    results: list[dict] = []

    po_field = _best_value(coc_fields, "po_numbers")
    part_id_field = _best_value(coc_fields, "part_id")
    model_field = _best_value(coc_fields, "model")
    serial_field = _best_value(coc_fields, "serial_numbers")
    qty_field = _best_value(coc_fields, "quantity")

    results.append({
        "rule_result": rules.check_identity_field_presence(
            po_field.field_value if po_field else None,
            serial_field.field_value if serial_field else None,
        ),
        "source_field": None,
    })

    for field_name, field in (("po_numbers", po_field), ("part_id", part_id_field), ("model", model_field), ("serial_numbers", serial_field)):
        expected = _bom_expected(bom_item, field_name)
        if not expected:
            # BOM doesn't have this field (missing, or captured as an empty
            # string) — nothing to compare, so nothing to report. Matches
            # check_exact_match's own `if not expected` treatment of "".
            continue
        results.append({
            "rule_result": rules.check_exact_match(field_name, expected, field.field_value if field else None, required=False),
            "source_field": field,
        })

    expected_qty = _bom_expected_quantity(bom_item)
    if expected_qty is not None:
        results.append({
            "rule_result": rules.check_quantity(expected_qty, qty_field.field_value if qty_field else None, previously_delivered_quantity),
            "source_field": qty_field,
        })

    if contract_date:
        coc_date_field = _best_value(coc_fields, "coc_issue_date")
        results.append({
            "rule_result": rules.check_date_not_before(
                "coc_issue_date", contract_date, coc_date_field.field_value if coc_date_field else None
            ),
            "source_field": coc_date_field,
        })

    import_docs_field = _best_value(coc_fields, "import_documents")
    is_imported = parse_bool_flag(_bom_expected(bom_item, "is_imported"))
    # Skip only when there's genuinely nothing to say (BOM doesn't specify
    # is_imported AND the COC has no import-document evidence either) —
    # real evidence on the COC is still worth surfacing regardless of
    # whether the BOM's is_imported flag exists.
    if is_imported is not None or import_docs_field is not None:
        results.append({
            "rule_result": rules.check_conditional_presence(
                "import_documents", is_imported, import_docs_field.field_value if import_docs_field else None
            ),
            "source_field": import_docs_field,
        })

    for field_name in FUZZY_TEXT_FIELDS:
        expected = _bom_expected(bom_item, field_name)
        if not expected:
            continue
        field = _best_value(coc_fields, field_name)
        results.append({
            "rule_result": rules.check_fuzzy_match(field_name, expected, field.field_value if field else None),
            "source_field": field,
        })

    for field_name in EXACT_TEXT_FIELDS:
        expected = _bom_expected(bom_item, field_name)
        if not expected:
            continue
        field = _best_value(coc_fields, field_name)
        results.append({
            "rule_result": rules.check_exact_match(field_name, expected, field.field_value if field else None, required=False),
            "source_field": field,
        })

    for field_name in PRESENCE_FIELDS:
        field = _best_value(coc_fields, field_name)
        results.append({
            "rule_result": rules.check_presence(field_name, field.field_value if field else None),
            "source_field": field,
        })

    return results


def _bom_expected_quantity(bom_item: "BOMItem | None") -> float | None:
    return bom_item.quantity if bom_item is not None else None
