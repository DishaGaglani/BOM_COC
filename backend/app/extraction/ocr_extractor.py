import pymupdf as fitz
import pytesseract
from PIL import Image

from app.schemas.canonical import RawTextBlock, BBox


def extract_ocr(path: str, dpi: int = 300) -> list[RawTextBlock]:
    """OCR fallback for scanned/image-based COCs and BOMs. Uses Tesseract's
    word-level output so each recognized word retains a bounding box and a
    per-word confidence score, which is required for highlighting later.

    Rasterizes pages via PyMuPDF (already a dependency for doc-type
    detection) instead of pdf2image, so no Poppler system package is
    needed for OCR."""
    blocks: list[RawTextBlock] = []
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)

    doc = fitz.open(path)
    try:
        pages = [doc[i].get_pixmap(matrix=matrix) for i in range(doc.page_count)]
    finally:
        doc.close()

    for page_index, pix in enumerate(pages, start=1):
        image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        n = len(data["text"])

        # Group words into lines using (block_num, par_num, line_num).
        lines: dict[tuple, list[int]] = {}
        for i in range(n):
            text = data["text"][i].strip()
            if not text:
                continue
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            lines.setdefault(key, []).append(i)

        # PDF points, not pixels, so downstream annotation aligns with pdfplumber output.
        scale = 72.0 / dpi

        for idxs in lines.values():
            words = [data["text"][i] for i in idxs]
            confs = [float(data["conf"][i]) for i in idxs if data["conf"][i] != "-1"]
            xs0 = [data["left"][i] for i in idxs]
            ys0 = [data["top"][i] for i in idxs]
            xs1 = [data["left"][i] + data["width"][i] for i in idxs]
            ys1 = [data["top"][i] + data["height"][i] for i in idxs]

            text = " ".join(words).strip()
            if not text:
                continue

            blocks.append(
                RawTextBlock(
                    page=page_index,
                    text=text,
                    bbox=BBox(
                        x0=min(xs0) * scale,
                        y0=min(ys0) * scale,
                        x1=max(xs1) * scale,
                        y1=max(ys1) * scale,
                    ),
                    source="ocr",
                    confidence=(sum(confs) / len(confs) / 100.0) if confs else 0.5,
                )
            )

    return blocks
