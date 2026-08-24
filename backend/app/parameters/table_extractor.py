import uuid

from app.parameters.html_table import parse_html_table
from app.parameters.schema import BOMItem, ExtractedField
from app.parameters.table_headers import map_table_headers
from app.parsing.schema import ParsedDocument
from app.validation.normalize import parse_quantity

# BOMItem's dedicated columns; anything else a table column mapped to lands
# in BOMItem.requirements instead.
_DEDICATED_BOM_FIELDS = {"part_id", "description", "manufacturer", "model", "quantity", "po_numbers"}


def extract_bom_line_items(document: ParsedDocument) -> list[BOMItem]:
    """One BOMItem per BOM table row. Real BOM line items live in genuine
    tables — a header row naming the column, and a separate data row per
    part — so only unstructured's table elements (from hi_res/xlsx/docx)
    are consulted here."""
    items: list[BOMItem] = []

    for table in document.tables:
        if not table.html:
            continue
        rows = parse_html_table(table.html)
        if len(rows) < 2:
            continue

        col_map = map_table_headers(rows[0])
        if not col_map:
            continue  # not a BOM-shaped table (e.g. a formatting/layout table)

        for raw_row in rows[1:]:
            row: dict[str, str] = {}
            for idx, field in col_map.items():
                if idx < len(raw_row) and raw_row[idx]:
                    row[field] = raw_row[idx].strip()

            if not (row.get("part_id") or row.get("description")):
                continue

            items.append(
                BOMItem(
                    item_id=str(uuid.uuid4()),
                    part_id=row.get("part_id"),
                    description=row.get("description"),
                    manufacturer=row.get("manufacturer"),
                    model=row.get("model"),
                    quantity=parse_quantity(row["quantity"]) if row.get("quantity") else None,
                    po_number=row.get("po_numbers"),
                    requirements={k: v for k, v in row.items() if k not in _DEDICATED_BOM_FIELDS},
                    page_number=table.page_number,
                )
            )

    return items


def extract_coc_table_fields(document: ParsedDocument) -> list[ExtractedField]:
    """Flattens COC table cells into individual fields (unlike BOM rows, a
    COC's table usually certifies one shipment/part, so cell-level fields
    matter more than row grouping). bbox is the whole table's bounding box
    — unstructured doesn't give per-cell coordinates, so highlighting a
    table-sourced field highlights the table region it came from."""
    fields: list[ExtractedField] = []

    for table in document.tables:
        if not table.html:
            continue
        rows = parse_html_table(table.html)
        if len(rows) < 2:
            continue

        col_map = map_table_headers(rows[0])
        if not col_map:
            continue

        header_row = rows[0]
        for raw_row in rows[1:]:
            for idx, field in col_map.items():
                if idx >= len(raw_row) or not raw_row[idx]:
                    continue
                value = raw_row[idx].strip()
                if not value:
                    continue

                fields.append(
                    ExtractedField(
                        field_name=field,
                        field_value=value,
                        page_number=table.page_number,
                        bbox=table.bbox,
                        extraction_method="table",
                        raw_label=header_row[idx].strip() if idx < len(header_row) and header_row[idx] else None,
                    )
                )

    return fields
