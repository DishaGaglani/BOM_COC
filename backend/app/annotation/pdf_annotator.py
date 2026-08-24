import pymupdf as fitz

STATUS_COLORS = {
    "PASS": (0.70, 0.93, 0.70),      # light green
    "FAIL": (0.98, 0.65, 0.65),      # light red
    "WARNING": (1.00, 0.87, 0.55),   # light amber
}


def annotate_pdf(source_path: str, output_path: str, annotations: list[dict]) -> str:
    """Highlights each annotation's bbox on the COC PDF, color-coded by
    validation status, with the parameter name + reason as a popup comment.
    `annotations` items look like:
    {"page": int, "bbox": {"x0","y0","x1","y1","layout_width","layout_height"},
     "parameter": str, "status": "PASS"/"FAIL"/"WARNING", "comment": str}

    bbox coordinates are in unstructured's layout-image pixel space (see
    parsing.schema.BBox) — this scales them into the PDF's actual page
    point space using the real page size, since the layout image unstructured
    measured against is rendered at whatever DPI it chose, not necessarily
    the PDF's native 72 DPI point space.
    """
    doc = fitz.open(source_path)
    try:
        for ann in annotations:
            bbox = ann.get("bbox")
            page_num = ann.get("page")
            if not bbox or not page_num or page_num < 1 or page_num > doc.page_count:
                continue

            page = doc[page_num - 1]
            layout_width = bbox.get("layout_width") or page.rect.width
            layout_height = bbox.get("layout_height") or page.rect.height
            scale_x = (page.rect.width / layout_width) if layout_width else 1.0
            scale_y = (page.rect.height / layout_height) if layout_height else 1.0

            rect = fitz.Rect(
                bbox["x0"] * scale_x,
                bbox["y0"] * scale_y,
                bbox["x1"] * scale_x,
                bbox["y1"] * scale_y,
            )
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
