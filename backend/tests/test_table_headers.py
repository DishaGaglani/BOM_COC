from app.parameters.table_headers import map_table_headers


def test_maps_known_headers_to_canonical_fields():
    col_map = map_table_headers(["Part No.", "Description", "Qty"])
    assert col_map == {0: "part_id", 1: "description", 2: "quantity"}


def test_unknown_header_column_is_ignored():
    col_map = map_table_headers(["Part No.", "Some Random Column"])
    assert col_map == {0: "part_id"}


def test_no_recognizable_headers_returns_empty_map():
    assert map_table_headers(["Foo", "Bar", None]) == {}


def test_item_no_outranks_part_no_for_part_id():
    # Both columns map to part_id; "Item No." (the customer's own catalog
    # number) should win over the manufacturer's "Part No." — see
    # table_headers.FIELD_LABEL_PRIORITY.
    col_map = map_table_headers(["Part No.", "Item No."])
    assert col_map == {1: "part_id"}


def test_total_outranks_qty_per_unit_for_quantity():
    col_map = map_table_headers(["Qty per Unit", "Total"])
    assert col_map == {1: "quantity"}
