"""Regression suite for the BOM-line matching tiers (Part ID + PO Number ->
Part ID alone -> PO Number alone, with quantity as a tiebreaker and an
explicit "ambiguous" outcome instead of silently picking the first
candidate). This is the fix for the "wrong BOM line silently matched"
production risk: a real BOM commonly has more than one line for the same
part (separate lots/deliveries), and picking the wrong one produces a wrong
PASS/FAIL rather than just a missing one.
"""

from app.validation.matching import match_bom_item
from tests.factories import make_bom_item, make_field


def test_unique_part_id_match():
    items = [make_bom_item(part_id="ABC-123", quantity=10)]
    fields = [make_field("part_id", "ABC-123")]

    result = match_bom_item(items, fields)

    assert result.status == "matched"
    assert result.item is items[0]


def test_unique_po_number_match_when_no_part_id():
    items = [make_bom_item(po_number="PO-999", quantity=5)]
    fields = [make_field("po_numbers", "PO-999")]

    result = match_bom_item(items, fields)

    assert result.status == "matched"
    assert result.item is items[0]


def test_part_id_and_po_number_together_narrows_a_duplicate_part():
    # Same part ordered under two different POs — Part ID alone is
    # ambiguous, but Part ID + PO Number together isn't.
    item_a = make_bom_item(part_id="ABC-123", po_number="PO-1", quantity=10)
    item_b = make_bom_item(part_id="ABC-123", po_number="PO-2", quantity=20)
    fields = [make_field("part_id", "ABC-123"), make_field("po_numbers", "PO-2")]

    result = match_bom_item([item_a, item_b], fields)

    assert result.status == "matched"
    assert result.item is item_b


def test_quantity_disambiguates_duplicate_part_and_po():
    # Same part, same PO, split across two lots of different sizes — this
    # is the exact scenario that used to silently match "the first row".
    item_a = make_bom_item(part_id="ABC-123", po_number="PO-1", quantity=10)
    item_b = make_bom_item(part_id="ABC-123", po_number="PO-1", quantity=25)
    fields = [
        make_field("part_id", "ABC-123"),
        make_field("po_numbers", "PO-1"),
        make_field("quantity", "25"),
    ]

    result = match_bom_item([item_a, item_b], fields)

    assert result.status == "matched"
    assert result.item is item_b


def test_true_duplicate_is_reported_ambiguous_not_silently_picked():
    # Same part, same PO, same quantity on two lines — genuinely can't be
    # told apart from the COC alone. Must NOT silently resolve to one.
    item_a = make_bom_item(part_id="ABC-123", po_number="PO-1", quantity=10)
    item_b = make_bom_item(part_id="ABC-123", po_number="PO-1", quantity=10)
    fields = [
        make_field("part_id", "ABC-123"),
        make_field("po_numbers", "PO-1"),
        make_field("quantity", "10"),
    ]

    result = match_bom_item([item_a, item_b], fields)

    assert result.status == "ambiguous"
    assert result.item is None
    # BOMItem is a plain (unhashable) pydantic model — compare by identity,
    # order-independent, instead of via a set.
    assert len(result.candidates) == 2
    assert item_a in result.candidates and item_b in result.candidates


def test_ambiguous_with_no_quantity_on_coc():
    item_a = make_bom_item(part_id="ABC-123", quantity=10)
    item_b = make_bom_item(part_id="ABC-123", quantity=20)
    fields = [make_field("part_id", "ABC-123")]  # no quantity extracted at all

    result = match_bom_item([item_a, item_b], fields)

    assert result.status == "ambiguous"
    assert len(result.candidates) == 2


def test_no_match_at_all_is_unmatched_not_ambiguous():
    items = [make_bom_item(part_id="ABC-123", quantity=10)]
    fields = [make_field("part_id", "ZZZ-999")]

    result = match_bom_item(items, fields)

    assert result.status == "unmatched"
    assert result.item is None
    assert result.candidates == []


def test_no_identifiers_extracted_from_coc_is_unmatched():
    items = [make_bom_item(part_id="ABC-123", quantity=10)]
    fields: list = []

    result = match_bom_item(items, fields)

    assert result.status == "unmatched"


def test_matching_tolerates_punctuation_formatting_noise():
    # BOM stores 'PO-45892'; COC's PO-fallback regex or a vendor's own
    # table cell often drops the punctuation entirely.
    items = [make_bom_item(po_number="PO-45892", quantity=10)]
    fields = [make_field("po_numbers", "PO45892")]

    result = match_bom_item(items, fields)

    assert result.status == "matched"
    assert result.item is items[0]


def test_matching_tolerates_whitespace_variant_of_part_id():
    items = [make_bom_item(part_id="ABC-123", quantity=10)]
    fields = [make_field("part_id", "ABC 123")]

    result = match_bom_item(items, fields)

    assert result.status == "matched"
    assert result.item is items[0]


def test_matching_is_case_and_whitespace_insensitive():
    items = [make_bom_item(part_id="ABC-123", quantity=10)]
    fields = [make_field("part_id", "  abc-123  ")]

    result = match_bom_item(items, fields)

    assert result.status == "matched"
    assert result.item is items[0]


def test_falls_back_to_po_number_when_part_id_matches_nothing():
    items = [make_bom_item(part_id="OTHER-1", po_number="PO-5", quantity=10)]
    fields = [make_field("part_id", "DOES-NOT-EXIST"), make_field("po_numbers", "PO-5")]

    result = match_bom_item(items, fields)

    assert result.status == "matched"
    assert result.item is items[0]
