import pymupdf as fitz

# RGB colors (0-1 range) per architecture doc section 13 highlighting rules.
STATUS_COLORS = {
    "PASS": (0.70, 0.93, 0.70),      # light green
    "FAIL": (0.98, 0.65, 0.65),      # light red
    "WARNING": (1.00, 0.87, 0.55),   # light amber
}


def annotate_pdf(source_path: str, output_path: str, annotations: list[dict]) -> str:
    """Highlights each annotation's bbox on the COC PDF, color-coded by
    validation status, with the parameter name + reason as a popup comment
    (architecture doc sections 12-13). `annotations` items look like:
    {"page": int, "bbox": {"x0","y0","x1","y1"}, "parameter": str,
     "status": "PASS"/"FAIL"/"WARNING", "comment": str}
    """
    doc = fitz.open(source_path)
    try:
        for ann in annotations:
            bbox = ann.get("bbox")
            page_num = ann.get("page")
            if not bbox or not page_num or page_num < 1 or page_num > doc.page_count:
                continue

            page = doc[page_num - 1]
            rect = fitz.Rect(bbox["x0"], bbox["y0"], bbox["x1"], bbox["y1"])
            color = STATUS_COLORS.get(ann.get("status", "WARNING"), STATUS_COLORS["WARNING"])

            highlight = page.add_highlight_annot(rect)
            highlight.set_colors(stroke=color)
            title = f"{ann.get('parameter', '')} — {ann.get('status', '')}"
            highlight.set_info(title=title, content=ann.get("comment", ""))
            highlight.update()

        doc.save(output_path)
    finally:
        doc.close()

    return output_path
