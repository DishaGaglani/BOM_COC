import uuid
from typing import Iterator

from app.parameters.confidence import HI_RES_TABLE_DEFAULT_CONFIDENCE, NATIVE_TABLE_CONFIDENCE
from app.parameters.html_table import parse_html_table
from app.parameters.schema import BOMItem, ExtractedField
from app.parameters.table_headers import map_table_headers
from app.parsing.schema import ParsedDocument, ParsedTable
from app.validation.normalize import parse_quantity


def _table_confidence(document: ParsedDocument, table: ParsedTable) -> float:
    if table.confidence is not None:
        return table.confidence  # real detection_class_prob from the hi_res layout model
    if document.strategy_used in ("hi_res", "ocr_only"):
        return HI_RES_TABLE_DEFAULT_CONFIDENCE
    return NATIVE_TABLE_CONFIDENCE  # native xlsx/docx/csv — no layout model involved

# BOMItem's dedicated columns; anything else a table column mapped to lands
# in BOMItem.requirements instead.
_DEDICATED_BOM_FIELDS = {"part_id", "description", "manufacturer", "model", "quantity", "po_numbers"}


def _fits_column_map(row: list[str], col_map: dict[int, str]) -> bool:
    return len(row) > max(col_map)


def _iter_data_rows(
    document: ParsedDocument,
) -> "Iterator[tuple[ParsedTable, list[list[str]], list[str], dict[int, str]]]":
    """Yields (table, data_rows, header_row, col_map) for every table
    element that has — or inherits — a recognizable header row.

    `unstructured` sometimes splits one logical table across a page break
    into separate table elements; a continuation fragment has no header row
    of its own (its first row is already data), so map_table_headers()
    would normally find nothing and the whole fragment gets silently
    dropped. Here, a header-less fragment whose row width still fits the
    immediately preceding table's column map is treated as a continuation
    of it — every one of its rows counts as data, including row 0.

    Carry-forward only reaches one table ahead, not indefinitely: it's
    consumed as soon as it's used, so an unrelated small header-less table
    later in the document (e.g. a signature block laid out as a table)
    doesn't also get misread as more BOM/COC rows.
    """
    carried: tuple[list[str], dict[int, str]] | None = None

    for table in document.tables:
        if not table.html:
            carried = None
            continue
        rows = parse_html_table(table.html)
        if not rows:
            carried = None
            continue

        header_col_map = map_table_headers(rows[0])
        if header_col_map:
            if len(rows) >= 2:
                yield table, rows[1:], rows[0], header_col_map
            carried = (rows[0], header_col_map)
            continue

        if carried is not None and _fits_column_map(rows[0], carried[1]):
            yield table, rows, carried[0], carried[1]
            carried = None
            continue

        carried = None


def extract_bom_line_items(document: ParsedDocument) -> list[BOMItem]:
    """One BOMItem per BOM table row. Real BOM line items live in genuine
    tables — a header row naming the column, and a separate data row per
    part — so only unstructured's table elements (from hi_res/xlsx/docx)
    are consulted here."""
    items: list[BOMItem] = []

    for table, data_rows, _header_row, col_map in _iter_data_rows(document):
        for raw_row in data_rows:
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

    for table, data_rows, header_row, col_map in _iter_data_rows(document):
        confidence = _table_confidence(document, table)
        for raw_row in data_rows:
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
                        confidence=confidence,
                    )
                )

    return fields
