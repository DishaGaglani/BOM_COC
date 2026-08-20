from dataclasses import dataclass

from rapidfuzz import fuzz

from app.validation.normalize import normalize_identifier, parse_quantity


@dataclass
class RuleResult:
    parameter: str
    expected_value: str | None
    actual_value: str | None
    status: str  # PASS / FAIL / WARNING
    reason: str


def check_document_type(coc_field_value: str | None) -> RuleResult:
    """Requirement #1: determine whether the uploaded document is a COC at all."""
    if coc_field_value and "coc" in coc_field_value.lower():
        return RuleResult("document_type", "COC", coc_field_value, "PASS", "Document classified as COC")
    if coc_field_value:
        return RuleResult(
            "document_type", "COC", coc_field_value, "FAIL",
            f"Document classified as '{coc_field_value}', not a COC",
        )
    return RuleResult(
        "document_type", "COC", None, "WARNING",
        "Could not confidently classify document type — manual review required",
    )


def check_exact_match(parameter: str, expected: str | None, actual: str | None, required: bool) -> RuleResult:
    """Generic exact/normalized-match rule for PO Number, Part ID, Model, Serial Number."""
    if not actual:
        status = "FAIL" if required else "WARNING"
        reason = f"{parameter.replace('_', ' ').title()} not found on COC"
        return RuleResult(parameter, expected, actual, status, reason)

    if not expected:
        return RuleResult(parameter, expected, actual, "WARNING", "No BOM value to validate against")

    if normalize_identifier(expected) == normalize_identifier(actual):
        return RuleResult(parameter, expected, actual, "PASS", "Match")

    return RuleResult(parameter, expected, actual, "FAIL", f"{parameter.replace('_', ' ').title()} mismatch")


def check_fuzzy_match(parameter: str, expected: str | None, actual: str | None, threshold: int = 55) -> RuleResult:
    """Free-text fields (e.g. description) rarely match a BOM verbatim — a
    BOM line reads 'MCB1', a COC reads 'Miniature Circuit Breaker - 3P - C -
    50A'. Token-set similarity tolerates reordering/extra words instead of
    demanding exact equality."""
    if not actual:
        return RuleResult(parameter, expected, actual, "WARNING", f"{parameter.replace('_', ' ').title()} not found on COC")
    if not expected:
        return RuleResult(parameter, expected, actual, "WARNING", "No BOM value to validate against")

    score = fuzz.token_set_ratio(expected.lower(), actual.lower())
    if score >= threshold:
        return RuleResult(parameter, expected, actual, "PASS", f"Similar enough ({score:.0f}% token match)")
    return RuleResult(parameter, expected, actual, "WARNING", f"Low similarity ({score:.0f}% token match) — manual review required")


def check_presence(parameter: str, found_value: str | None) -> RuleResult:
    """For compliance elements that aren't a clean label:value pair
    (signature, seal, attached-document mentions) — confirms the term is
    referenced somewhere in the document's text. Not a substitute for
    visually verifying an actual signature or seal mark is present, so
    absence is a WARNING (flag for manual review) rather than a FAIL."""
    if found_value:
        return RuleResult(parameter, "Present", found_value, "PASS", f"'{found_value}' found on document")
    return RuleResult(
        parameter, "Present", None, "WARNING",
        f"{parameter.replace('_', ' ').title()} not mentioned anywhere in the document text — manual review required",
    )


def check_identity_field_presence(po: str | None, serial: str | None) -> RuleResult:
    """Requirements #2/#5: 'one of PO Number or Serial Number should be present.'"""
    if po or serial:
        return RuleResult(
            "identity_field_presence", "PO Number or Serial Number", po or serial, "PASS",
            "At least one identity field present",
        )
    return RuleResult(
        "identity_field_presence", "PO Number or Serial Number", None, "FAIL",
        "Neither PO Number nor Serial Number found on COC",
    )


def check_quantity(expected_qty: float | None, actual_value: str | None) -> RuleResult:
    """Requirement #6: verify COC quantity against PO/project quantity."""
    actual_qty = parse_quantity(actual_value) if actual_value else None

    if actual_qty is None:
        return RuleResult("quantity", str(expected_qty) if expected_qty is not None else None, actual_value, "FAIL", "Quantity not found on COC")
    if expected_qty is None:
        return RuleResult("quantity", None, str(actual_qty), "WARNING", "No BOM/PO quantity to validate against")
    if actual_qty == expected_qty:
        return RuleResult("quantity", str(expected_qty), str(actual_qty), "PASS", "Quantity matches BOM/PO")
    return RuleResult(
        "quantity", str(expected_qty), str(actual_qty), "FAIL",
        f"Quantity mismatch: expected {expected_qty}, found {actual_qty}",
    )
