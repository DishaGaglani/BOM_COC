from app.validation import rules


def test_identity_field_presence_pass_and_fail():
    assert rules.check_identity_field_presence("PO-1", None).status == "PASS"
    assert rules.check_identity_field_presence(None, "SN-1").status == "PASS"
    assert rules.check_identity_field_presence(None, None).status == "FAIL"


def test_exact_match_pass_fail_warning():
    assert rules.check_exact_match("part_id", "ABC-123", "abc-123", required=False).status == "PASS"
    assert rules.check_exact_match("part_id", "ABC-123", "XYZ-999", required=False).status == "FAIL"
    # No BOM value to check against -> can't fail, just needs a human look.
    assert rules.check_exact_match("part_id", None, "XYZ-999", required=False).status == "WARNING"
    # Not required and missing from the COC -> warn, don't fail.
    assert rules.check_exact_match("part_id", "ABC-123", None, required=False).status == "WARNING"
    # Required and missing -> fail.
    assert rules.check_exact_match("part_id", "ABC-123", None, required=True).status == "FAIL"


def test_exact_match_passes_through_formatting_differences():
    # Same identifier, different punctuation -> PASS, but the reason still
    # names the formatting difference rather than reading identical to a
    # true exact match.
    result = rules.check_exact_match("po_numbers", "PO-45892", "PO45892", required=False)
    assert result.status == "PASS"
    assert "formatting differs" in result.reason

    result2 = rules.check_exact_match("po_numbers", "PO-45892", "PO 45892", required=False)
    assert result2.status == "PASS"


def test_exact_match_close_but_not_identical_is_warning_not_pass():
    # A one-character slip after stripping punctuation — plausibly a typo/
    # OCR error, not confidently the same value, so it should NOT silently
    # PASS, but shouldn't be a flat FAIL either.
    result = rules.check_exact_match("po_numbers", "PO-45892", "PO-45893", required=False)
    assert result.status == "WARNING"
    assert "similar" in result.reason.lower()


def test_exact_match_genuinely_different_still_fails():
    result = rules.check_exact_match("part_id", "ABC-123", "COMPLETELY-DIFFERENT-999", required=False)
    assert result.status == "FAIL"


def test_fuzzy_match_thresholds():
    result = rules.check_fuzzy_match("description", "MCB1", "Miniature Circuit Breaker MCB1 3P 50A")
    assert result.status in ("PASS", "WARNING")  # token-set ratio dependent, but must not crash
    assert rules.check_fuzzy_match("description", "MCB1", None).status == "WARNING"
    assert rules.check_fuzzy_match("description", None, "MCB1").status == "WARNING"
    assert rules.check_fuzzy_match("description", "Circuit Breaker", "Completely Unrelated Item").status == "WARNING"


def test_presence_pass_and_warning():
    assert rules.check_presence("signature", "Authorised Signatory").status == "PASS"
    assert rules.check_presence("signature", None).status == "WARNING"


def test_date_not_before_pass_fail_warning():
    assert rules.check_date_not_before("coc_issue_date", "2026-01-01", "2026-06-01").status == "PASS"
    assert rules.check_date_not_before("coc_issue_date", "2026-06-01", "2026-01-01").status == "FAIL"
    assert rules.check_date_not_before("coc_issue_date", "2026-01-01", None).status == "WARNING"
    assert rules.check_date_not_before("coc_issue_date", None, "2026-01-01").status == "WARNING"
    assert rules.check_date_not_before("coc_issue_date", "not a date", "2026-01-01").status == "WARNING"


def test_conditional_presence_import_documents():
    # Not imported -> not applicable, passes regardless of presence.
    assert rules.check_conditional_presence("import_documents", False, None).status == "PASS"
    # Imported and present -> pass.
    assert rules.check_conditional_presence("import_documents", True, "Bill of Entry").status == "PASS"
    # Imported and missing -> hard fail (compliance-required).
    assert rules.check_conditional_presence("import_documents", True, None).status == "FAIL"
    # Unknown import status and missing -> warn, don't fail outright.
    assert rules.check_conditional_presence("import_documents", None, None).status == "WARNING"
    # Unknown import status but present anyway -> pass.
    assert rules.check_conditional_presence("import_documents", None, "Bill of Entry").status == "PASS"


def test_quantity_pass_fail_warning():
    assert rules.check_quantity(10.0, "10").status == "PASS"
    assert rules.check_quantity(10.0, "12").status == "FAIL"
    assert rules.check_quantity(10.0, "not a number").status == "FAIL"
    assert rules.check_quantity(None, "10").status == "WARNING"


def test_quantity_partial_delivery_passes_when_within_bom_total():
    # A shipment split into lots: this COC alone is less than the BOM line's
    # full quantity, but that's a legitimate partial delivery, not a FAIL.
    result = rules.check_quantity(100.0, "40")
    assert result.status == "PASS"
    assert "Partial delivery" in result.reason


def test_quantity_cumulative_across_prior_cocs_completes_the_order():
    result = rules.check_quantity(100.0, "60", previously_delivered=40.0)
    assert result.status == "PASS"
    assert "Completes the order" in result.reason


def test_quantity_cumulative_still_partial_notes_prior_deliveries():
    result = rules.check_quantity(100.0, "30", previously_delivered=40.0)
    assert result.status == "PASS"
    assert "Partial delivery" in result.reason
    assert "already delivered" in result.reason


def test_quantity_cumulative_exceeding_bom_total_fails():
    result = rules.check_quantity(100.0, "30", previously_delivered=80.0)
    assert result.status == "FAIL"
    assert "exceeds BOM" in result.reason
