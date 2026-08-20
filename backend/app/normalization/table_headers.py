from app.normalization.synonyms import normalize_label

# When a table has more than one column that maps to the same canonical
# field (e.g. a BOM with both an internal "L&T Cat No." and the
# manufacturer's own "Part No."), the columns don't agree on priority order.
# Verified against real L&T BOM/COC samples: suppliers echo the customer's
# own catalog number back as "Item No." or "CPN" (Customer Part Number),
# which is what should be matched against the BOM — not the manufacturer's
# own "Part No.", which varies supplier to supplier for the same component.
FIELD_LABEL_PRIORITY = [
    "l&t cat no", "l&t cat no.",
    "item no", "item no.",
    "cpn",
    "part no", "part no.", "part number", "p/n",
    "component id", "component no", "component no.", "item code",

    # A BOM's "Total" (e.g. qty-per-unit x units ordered) is what a
    # shipment's COC quantity is actually checked against; "Qty per unit"
    # describes a single assembly, not what should arrive on one COC.
    "total",
    "qty per unit", "qty (nos.)", "qty(nos.)", "qty", "quantity",
]


def map_table_headers(header_row: list[str | None]) -> dict[int, str]:
    """Maps each table column index to a canonical field name, preferring
    the higher-priority label (per FIELD_LABEL_PRIORITY) when multiple
    columns would otherwise map to the same canonical field."""
    col_map: dict[int, str] = {}
    field_rank: dict[str, int] = {}

    for idx, cell in enumerate(header_row):
        if not cell:
            continue
        label = cell.strip().lower().rstrip(":")
        canonical = normalize_label(cell)
        if not canonical:
            continue

        rank = FIELD_LABEL_PRIORITY.index(label) if label in FIELD_LABEL_PRIORITY else len(FIELD_LABEL_PRIORITY)

        current_idx = next((i for i, f in col_map.items() if f == canonical), None)
        if current_idx is None:
            col_map[idx] = canonical
            field_rank[canonical] = rank
        elif rank < field_rank[canonical]:
            del col_map[current_idx]
            col_map[idx] = canonical
            field_rank[canonical] = rank

    return col_map
