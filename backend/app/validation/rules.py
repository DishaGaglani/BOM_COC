from dataclasses import dataclass

from rapidfuzz import fuzz

from app.validation.normalize import normalize_identifier, normalize_identifier_loose, parse_date, parse_quantity


@dataclass
class RuleResult:
    parameter: str
    expected_value: str | None
    actual_value: str | None
    status: str  # PASS / FAIL / WARNING
    reason: str


def check_identity_field_presence(po: str | None, serial: str | None) -> RuleResult:
    """'One of PO Number or Serial Number should be present.'"""
    if po or serial:
        return RuleResult(
            "identity_field_presence", "PO Number or Serial Number", po or serial, "PASS",
            "At least one identity field present",
        )
    return RuleResult(
        "identity_field_presence", "PO Number or Serial Number", None, "FAIL",
        "Neither PO Number nor Serial Number found on COC",
    )


_LOOSE_MATCH_SIMILARITY_THRESHOLD = 85


def check_exact_match(parameter: str, expected: str | None, actual: str | None, required: bool) -> RuleResult:
    """Generic exact/normalized-match rule for PO Number, Part ID, Model,
    Serial Number. Falls back through two more tolerant comparisons before
    declaring a mismatch, since vendors are inconsistent about punctuation
    in identifiers that are otherwise the same value:
      1. strict normalize_identifier() equality -> PASS, no caveat.
      2. equal after stripping ALL punctuation/whitespace (normalize_identifier_loose)
         -> PASS, but the reason notes the formatting difference so it's still
         visible on the report, not silently indistinguishable from an exact match.
      3. merely similar after that same stripping (rapidfuzz ratio) -> WARNING,
         not PASS — this could be a genuine typo/OCR error rather than the same
         value, so it's flagged for a human rather than waved through.
    """
    if not actual:
        status = "FAIL" if required else "WARNING"
        reason = f"{parameter.replace('_', ' ').title()} not found on COC"
        return RuleResult(parameter, expected, actual, status, reason)

    if not expected:
        return RuleResult(parameter, expected, actual, "WARNING", "No BOM value to validate against")

    if normalize_identifier(expected) == normalize_identifier(actual):
        return RuleResult(parameter, expected, actual, "PASS", "Match")

    loose_expected, loose_actual = normalize_identifier_loose(expected), normalize_identifier_loose(actual)
    if loose_expected and loose_expected == loose_actual:
        return RuleResult(
            parameter, expected, actual, "PASS",
            f"Match — formatting differs ('{expected}' vs '{actual}')",
        )

    similarity = fuzz.ratio(loose_expected, loose_actual) if loose_expected and loose_actual else 0
    if similarity >= _LOOSE_MATCH_SIMILARITY_THRESHOLD:
        return RuleResult(
            parameter, expected, actual, "WARNING",
            f"Close but not identical ({similarity:.0f}% similar after removing punctuation) — "
            "possible formatting/typo difference, manual review recommended",
        )

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


def check_date_not_before(parameter: str, expected: str | None, actual: str | None) -> RuleResult:
    """COC issue date vs. the BOM's contract/effective date (requirement
    #10): a certificate can't attest compliance before the contract that
    ordered the goods existed, so the COC's issue date must be on or after
    it."""
    if not actual:
        return RuleResult(parameter, expected, actual, "WARNING", f"{parameter.replace('_', ' ').title()} not found on COC")
    if not expected:
        return RuleResult(parameter, expected, actual, "WARNING", "No BOM contract/effective date to validate against")

    actual_date = parse_date(actual)
    expected_date = parse_date(expected)
    if actual_date is None or expected_date is None:
        return RuleResult(parameter, expected, actual, "WARNING", "Could not parse date(s) for comparison — manual review required")

    if actual_date >= expected_date:
        return RuleResult(
            parameter, expected, actual, "PASS",
            f"COC issued {actual_date.isoformat()}, on/after contract date {expected_date.isoformat()}",
        )
    return RuleResult(
        parameter, expected, actual, "FAIL",
        f"COC issued {actual_date.isoformat()}, before contract/effective date {expected_date.isoformat()}",
    )


def check_conditional_presence(parameter: str, is_required: bool | None, found_value: str | None) -> RuleResult:
    """Like check_presence, but for requirements that only apply
    conditionally (requirement #7: import documents are only required 'if
    item is imported'). `is_required` comes from a BOM column (e.g.
    'Imported: Yes/No') via normalize.parse_bool_flag — None means the BOM
    didn't say either way, not that the answer is 'no'."""
    if is_required is False:
        return RuleResult(parameter, None, found_value, "PASS", "Not applicable — item is not marked as imported on the BOM")

    if found_value:
        return RuleResult(parameter, "Present", found_value, "PASS", f"'{found_value}' found on document")

    if is_required is True:
        return RuleResult(
            parameter, "Present", None, "FAIL",
            f"{parameter.replace('_', ' ').title()} required — item is marked as imported on the BOM, but none were found on the COC",
        )

    return RuleResult(
        parameter, "Present", None, "WARNING",
        f"{parameter.replace('_', ' ').title()} not mentioned, and import status isn't specified on the BOM — manual review required",
    )


def check_quantity(expected_qty: float | None, actual_value: str | None, previously_delivered: float = 0.0) -> RuleResult:
    """Verify COC quantity against BOM quantity, allowing for a shipment
    that's split across multiple COCs against the same BOM line (a common
    real pattern — goods arrive in lots, not all at once). `previously_delivered`
    is the sum of quantities already validated on *other* COCs matched to
    this same BOM line (see coc_service._previously_delivered_quantity); a
    single COC no longer has to equal the BOM's full line quantity to PASS —
    it just can't push the running total past it."""
    actual_qty = parse_quantity(actual_value) if actual_value else None

    if actual_qty is None:
        return RuleResult("quantity", str(expected_qty) if expected_qty is not None else None, actual_value, "FAIL", "Quantity not found on COC")
    if expected_qty is None:
        return RuleResult("quantity", None, str(actual_qty), "WARNING", "No BOM quantity to validate against")

    cumulative = previously_delivered + actual_qty
    prior_note = f" ({previously_delivered:g} already delivered on earlier COCs)" if previously_delivered else ""

    if cumulative > expected_qty:
        return RuleResult(
            "quantity", str(expected_qty), str(actual_qty), "FAIL",
            f"Quantity exceeds BOM: {cumulative:g} delivered against {expected_qty:g} ordered{prior_note}",
        )
    if cumulative == expected_qty:
        reason = "Quantity matches BOM" if not previously_delivered else f"Completes the order: {cumulative:g} of {expected_qty:g} delivered across COCs"
        return RuleResult("quantity", str(expected_qty), str(actual_qty), "PASS", reason)

    remaining = expected_qty - cumulative
    return RuleResult(
        "quantity", str(expected_qty), str(actual_qty), "PASS",
        f"Partial delivery: {cumulative:g} of {expected_qty:g} delivered so far ({remaining:g} remaining){prior_note}",
    )
