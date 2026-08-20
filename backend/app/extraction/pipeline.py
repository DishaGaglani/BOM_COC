from app.extraction.doc_type import is_scanned_pdf, page_count
from app.extraction.native_extractor import extract_native
from app.extraction.ocr_extractor import extract_ocr
from app.schemas.canonical import DocumentExtractionResult


def run_extraction(path: str, filename: str) -> DocumentExtractionResult:
    """Entry point for the extraction layer (architecture doc section 8).
    Detects whether the PDF has a usable text layer and routes it to native
    table/text extraction or OCR; both paths converge into RawTextBlocks
    with the same page/bbox/confidence shape."""
    scanned = is_scanned_pdf(path)
    blocks = extract_ocr(path) if scanned else extract_native(path)

    # A native PDF can still have scanned pages mixed in (e.g. a signed
    # cover page); if native extraction found almost nothing, retry with OCR.
    if not scanned and len("".join(b.text for b in blocks)) < 20:
        blocks = extract_ocr(path)
        scanned = True

    return DocumentExtractionResult(
        filename=filename,
        is_scanned=scanned,
        page_count=page_count(path),
        raw_blocks=blocks,
    )
