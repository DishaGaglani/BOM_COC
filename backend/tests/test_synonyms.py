from app.parameters.synonyms import normalize_label


def test_exact_match_still_resolves_directly():
    assert normalize_label("Part No.") == "part_id"
    assert normalize_label("PO Number") == "po_numbers"


def test_unknown_label_with_no_similarity_returns_none():
    assert normalize_label("Notes") is None
    assert normalize_label("Remarks") is None
    assert normalize_label("") is None


def test_fuzzy_fallback_resolves_common_typos():
    assert normalize_label("Pat No.") == "part_id"
    assert normalize_label("Part Numbr") == "part_id"
    assert normalize_label("PO Numbr") == "po_numbers"
    assert normalize_label("Qy") == "quantity"
    assert normalize_label("Modle") == "model"
    assert normalize_label("CocDate") == "coc_issue_date"
    assert normalize_label("PO Dat") == "contract_date"


def test_fuzzy_fallback_does_not_confuse_similar_but_different_fields():
    # "Part Number" (part_id) and "PO Number" (po_numbers) are textually
    # close (80% by plain char-ratio) but mean completely different things —
    # a typo'd/short header must not accidentally cross that boundary.
    assert normalize_label("Part Numbr") == "part_id"
    assert normalize_label("PO Numbr") == "po_numbers"


def test_fuzzy_fallback_declines_genuinely_ambiguous_truncations():
    # "Manufactur..." is a near-exact tie between "manufacturer" and
    # "manufactured" (-> manufacturing_year) — must decline rather than
    # silently guess one, since guessing wrong would mismap the field.
    assert normalize_label("Manufactur") is None
    assert normalize_label("Manufacturre") is None
    assert normalize_label("Manufactu") is None


def test_fuzzy_fallback_is_conservative_near_the_ambiguous_boundary():
    # A near-miss ('manufacured', one letter short of 'manufactured') still
    # scores close enough to BOTH manufacturing_year and manufacturer that
    # the margin check declines it — left unmapped rather than guessed,
    # same as today's behavior for an unrecognized header.
    assert normalize_label("Manufacured") is None
