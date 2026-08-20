import pdfplumber

from app.schemas.canonical import RawTextBlock, BBox


def extract_native(path: str) -> list[RawTextBlock]:
    """Extract text lines and table cells from a native (non-scanned) PDF,
    keeping page + bounding box for downstream highlighting."""
    blocks: list[RawTextBlock] = []

    with pdfplumber.open(path) as pdf:
        for page_index, page in enumerate(pdf.pages, start=1):
            # Table cells first — BOM/COC line items usually live in tables.
            tables = page.find_tables()
            table_cell_bboxes = set()
            for table in tables:
                for row in table.extract():
                    for cell_text in row:
                        if cell_text:
                            pass  # cell-level bbox handled via table.cells below
                for cell in table.cells:
                    x0, top, x1, bottom = cell
                    cell_text = page.crop((x0, top, x1, bottom)).extract_text()
                    if cell_text:
                        table_cell_bboxes.add((round(x0), round(top), round(x1), round(bottom)))
                        blocks.append(
                            RawTextBlock(
                                page=page_index,
                                text=cell_text.strip(),
                                bbox=BBox(x0=x0, y0=top, x1=x1, y1=bottom),
                                source="table",
                                confidence=1.0,
                            )
                        )

            # Free-text lines (for headers, signature blocks, dates, etc.)
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            lines: dict[int, list] = {}
            for w in words:
                # Skip words that fall inside an already-captured table cell.
                if any(
                    bx0 <= w["x0"] and w["x1"] <= bx1 and by0 <= w["top"] and w["bottom"] <= by1
                    for bx0, by0, bx1, by1 in table_cell_bboxes
                ):
                    continue
                key = round(w["top"])
                lines.setdefault(key, []).append(w)

            for _, ws in sorted(lines.items()):
                ws_sorted = sorted(ws, key=lambda w: w["x0"])
                text = " ".join(w["text"] for w in ws_sorted).strip()
                if not text:
                    continue
                x0 = min(w["x0"] for w in ws_sorted)
                x1 = max(w["x1"] for w in ws_sorted)
                y0 = min(w["top"] for w in ws_sorted)
                y1 = max(w["bottom"] for w in ws_sorted)
                blocks.append(
                    RawTextBlock(
                        page=page_index,
                        text=text,
                        bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1),
                        source="table",
                        confidence=1.0,
                    )
                )

    return blocks
