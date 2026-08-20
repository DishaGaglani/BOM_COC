import pymupdf as fitz


def is_scanned_pdf(path: str, text_threshold: int = 20) -> bool:
    """A page is treated as 'scanned' if it has no meaningful embedded text
    layer, so extraction should fall back to OCR instead of text/table parsing."""
    doc = fitz.open(path)
    try:
        total_chars = 0
        for page in doc:
            total_chars += len(page.get_text("text").strip())
            if total_chars >= text_threshold:
                return False
        return True
    finally:
        doc.close()


def page_count(path: str) -> int:
    doc = fitz.open(path)
    try:
        return doc.page_count
    finally:
        doc.close()
