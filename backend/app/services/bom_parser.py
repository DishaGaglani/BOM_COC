import pdfplumber

from app.normalization.table_headers import map_table_headers
from app.extraction.doc_type import is_scanned_pdf

REQUIRED_ROW_FIELDS = {"part_id", "description", "manufacturer", "model", "quantity", "po_numbers"}


def parse_bom_tables(path: str) -> list[dict]:
    """Parses BOM/Traceability Matrix tables into row dicts keyed by
    canonical field name (architecture doc sections 5-6). Assumes the BOM
    is a native (non-scanned) document with an embedded table, per the
    confirmed input format. Raises ValueError if no usable table is found
    so the caller can fall back to OCR + LLM extraction."""
    if is_scanned_pdf(path):
        raise ValueError("BOM appears to be a scanned document — table extraction requires OCR fallback")

    rows: list[dict] = []

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for table in page.find_tables():
                data = table.extract()
                if not data or len(data) < 2:
                    continue

                col_map = map_table_headers(data[0])
                if not col_map:
                    continue  # not a BOM-shaped table (e.g. a formatting table)

                for raw_row in data[1:]:
                    row: dict = {}
                    for idx, field in col_map.items():
                        if idx < len(raw_row) and raw_row[idx]:
                            row[field] = raw_row[idx].strip()
                    if row.get("part_id") or row.get("description"):
                        rows.append(row)

    if not rows:
        raise ValueError("No BOM-shaped table found in document")

    return rows
