from app.parameters.table_extractor import extract_bom_line_items, extract_coc_table_fields
from tests.factories import make_multi_table_document, make_parsed_document


def test_extract_bom_line_items_maps_columns_to_bom_items():
    doc = make_parsed_document(
        table_rows=[
            ["Part No.", "Description", "Manufacturer", "Qty", "PO No."],
            ["ABC-123", "Circuit Breaker", "Acme Co", "10", "PO-1"],
            ["XYZ-999", "Relay", "Acme Co", "5", "PO-1"],
        ]
    )

    items = extract_bom_line_items(doc)

    assert len(items) == 2
    assert items[0].part_id == "ABC-123"
    assert items[0].description == "Circuit Breaker"
    assert items[0].quantity == 10.0
    assert items[0].po_number == "PO-1"


def test_extract_bom_line_items_skips_rows_with_no_identifying_field():
    doc = make_parsed_document(
        table_rows=[
            ["Part No.", "Manufacturer"],
            ["", "Acme Co"],  # no part_id and no description -> not a real line item
        ]
    )

    assert extract_bom_line_items(doc) == []


def test_extract_bom_line_items_ignores_non_bom_shaped_tables():
    doc = make_parsed_document(table_rows=[["Foo", "Bar"], ["1", "2"]])
    assert extract_bom_line_items(doc) == []


def test_bom_table_split_across_a_page_break_is_reassembled():
    # unstructured emits one ParsedTable per page for a table that spans a
    # page break — the second page's fragment has no header row of its own.
    doc = make_multi_table_document(
        [
            [
                ["Part No.", "Description", "Qty"],
                ["ABC-123", "Circuit Breaker", "10"],
            ],
            [
                # Continuation: same column count, no header — used to be
                # silently dropped entirely.
                ["XYZ-999", "Relay", "5"],
                ["QRS-1", "Fuse", "2"],
            ],
        ]
    )

    items = extract_bom_line_items(doc)

    assert [i.part_id for i in items] == ["ABC-123", "XYZ-999", "QRS-1"]
    assert items[1].quantity == 5.0


def test_continuation_only_carries_forward_one_table():
    # A third, unrelated header-less table (same shape) two entries after
    # the real header must NOT also be swept in — carry-forward is consumed
    # by the continuation fragment right after the header.
    doc = make_multi_table_document(
        [
            [["Part No.", "Description", "Qty"], ["ABC-123", "Circuit Breaker", "10"]],
            [["XYZ-999", "Relay", "5"]],  # legitimate continuation, consumes the carry
            [["NOT-A-PART", "Unrelated", "1"]],  # e.g. a coincidentally same-shaped table
        ]
    )

    items = extract_bom_line_items(doc)

    assert [i.part_id for i in items] == ["ABC-123", "XYZ-999"]


def test_continuation_fragment_with_fewer_columns_is_not_misread():
    doc = make_multi_table_document(
        [
            [["Part No.", "Description", "Qty"], ["ABC-123", "Circuit Breaker", "10"]],
            [["Just one cell"]],  # doesn't fit the 3-column map -> not a continuation
        ]
    )

    items = extract_bom_line_items(doc)

    assert [i.part_id for i in items] == ["ABC-123"]


def test_coc_table_continuation_keeps_original_header_as_raw_label():
    doc = make_multi_table_document(
        [
            [["Part No.", "Serial No."], ["ABC-123", "SN-1"]],
            [["XYZ-999", "SN-2"]],
        ]
    )

    fields = extract_coc_table_fields(doc)

    part_id_fields = [f for f in fields if f.field_name == "part_id"]
    assert {f.field_value for f in part_id_fields} == {"ABC-123", "XYZ-999"}
    assert all(f.raw_label == "Part No." for f in part_id_fields)


def test_extract_coc_table_fields_flattens_cells_with_confidence():
    doc = make_parsed_document(
        table_rows=[
            ["Part No.", "Serial No."],
            ["ABC-123", "SN-1"],
        ]
    )

    fields = extract_coc_table_fields(doc)

    names = {f.field_name for f in fields}
    assert names == {"part_id", "serial_numbers"}
    for f in fields:
        assert f.extraction_method == "table"
        assert 0.0 < f.confidence <= 1.0
