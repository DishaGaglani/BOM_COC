import pdfplumber

from app.normalization.table_headers import map_table_headers
from app.schemas.canonical import BBox, ExtractedField


def extract_table_fields(path: str) -> list[ExtractedField]:
    """Rule-based extraction from table headers + data rows.

    Complements extract_rule_based_fields (field_mapper.py), which only
    catches inline "label: value" text on a single line. Real COC line
    items live in genuine tables — a header row naming the column, and a
    separate data row holding the value — which a single-line regex can't
    see at all. Verified against real sample COCs, all of which put every
    identifying field (Part No./Item No./CPN/Make/Qty) in a table."""
    fields: list[ExtractedField] = []

    with pdfplumber.open(path) as pdf:
        for page_index, page in enumerate(pdf.pages, start=1):
            for table in page.find_tables():
                data = table.extract()
                if not data or len(data) < 2:
                    continue

                col_map = map_table_headers(data[0])
                if not col_map:
                    continue

                for row_idx in range(1, len(data)):
                    raw_row = data[row_idx]
                    row_cells = table.rows[row_idx].cells if row_idx < len(table.rows) else []

                    for col_idx, field in col_map.items():
                        if col_idx >= len(raw_row) or not raw_row[col_idx]:
                            continue
                        value = raw_row[col_idx].strip()
                        if not value:
                            continue

                        bbox = None
                        if col_idx < len(row_cells) and row_cells[col_idx]:
                            x0, top, x1, bottom = row_cells[col_idx]
                            bbox = BBox(x0=x0, y0=top, x1=x1, y1=bottom)

                        fields.append(
                            ExtractedField(
                                field_name=field,
                                field_value=value,
                                confidence=1.0,
                                page=page_index,
                                bbox=bbox,
                                extraction_method="rule",
                                raw_label=(data[0][col_idx] or "").strip() if col_idx < len(data[0]) else None,
                            )
                        )

    return fields
