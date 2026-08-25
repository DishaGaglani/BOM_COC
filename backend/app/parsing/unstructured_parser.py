"""Document -> structured elements, via the local (open-source) unstructured library.

Runs fully offline once the layout-detection model has been cached on first
use: no documents leave this machine. Handles born-digital and scanned PDFs,
plain text, and Excel/Word/CSV files through unstructured's format-agnostic
`partition()` dispatcher.
"""

import uuid
from pathlib import Path

from unstructured.partition.auto import partition

from app.config import settings
from app.parsing.schema import BBox, ParsedDocument, ParsedElement, ParsedTable

# Strategies, in the order we fall back through when one fails (e.g. the
# hi_res layout model can't be downloaded on an offline VM). "fast" never
# OCRs, so it is only a last-resort fallback, not a first choice.
FALLBACK_STRATEGIES = {
    "auto": ["hi_res", "ocr_only", "fast"],
    "hi_res": ["ocr_only", "fast"],
    "ocr_only": ["fast"],
    "fast": [],
}

SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".txt",
    ".csv",
    ".tsv",
    ".xlsx",
    ".xls",
    ".docx",
    ".doc",
    ".rtf",
    ".html",
    ".htm",
    ".png",
    ".jpg",
    ".jpeg",
    ".tiff",
    ".eml",
    ".msg",
}


def _extract_bbox(metadata: dict) -> BBox | None:
    coords = metadata.get("coordinates")
    points = coords.get("points") if coords else None
    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return BBox(
        x0=min(xs),
        y0=min(ys),
        x1=max(xs),
        y1=max(ys),
        layout_width=coords.get("layout_width"),
        layout_height=coords.get("layout_height"),
    )


def _run_partition(file_path: Path, strategy: str, languages: list[str]) -> list:
    # `strategy`/`languages` only apply to formats that support them
    # (pdf/image); unstructured ignores them for e.g. xlsx/docx.
    # `skip_infer_table_types=[]` overrides unstructured's default of
    # skipping table-structure inference for pdf/image types.
    return partition(
        filename=str(file_path),
        strategy=strategy,
        languages=languages,
        skip_infer_table_types=[],
    )


def parse_document(
    file_path: Path,
    filename: str,
    strategy: str | None = None,
) -> ParsedDocument:
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file extension: {ext!r}")

    strategy = strategy or settings.default_strategy
    languages = [lang.strip() for lang in settings.ocr_languages.split(",") if lang.strip()]

    warnings: list[str] = []
    strategy_used = strategy
    elements = None
    last_error: Exception | None = None

    attempts = [strategy] + FALLBACK_STRATEGIES.get(strategy, [])
    for attempt in attempts:
        try:
            elements = _run_partition(file_path, attempt, languages)
            strategy_used = attempt
            if attempt != strategy:
                warnings.append(
                    f"Strategy '{strategy}' failed ({last_error}), fell back to '{attempt}'."
                )
            break
        except Exception as exc:  # noqa: BLE001 - broad on purpose, feeds fallback chain
            last_error = exc
            continue

    if elements is None:
        raise RuntimeError(
            f"All parsing strategies failed for {filename!r}: {last_error}"
        ) from last_error

    parsed_elements: list[ParsedElement] = []
    tables: list[ParsedTable] = []

    for el in elements:
        el_dict = el.to_dict()
        metadata = el_dict.get("metadata", {}) or {}
        page_number = metadata.get("page_number")
        html = metadata.get("text_as_html")
        bbox = _extract_bbox(metadata)
        confidence = metadata.get("detection_class_prob")

        parsed_elements.append(
            ParsedElement(
                element_id=el_dict.get("element_id", str(uuid.uuid4())),
                type=el_dict.get("type", "UncategorizedText"),
                text=el_dict.get("text", ""),
                html=html,
                page_number=page_number,
                bbox=bbox,
                confidence=confidence,
                metadata={
                    k: v
                    for k, v in metadata.items()
                    # The raw coordinates/points blob is only meaningful
                    # alongside the original page image; `bbox` above is
                    # the lean, directly-usable form of the same data.
                    if k not in {"coordinates", "points"}
                },
            )
        )

        if el_dict.get("type") == "Table":
            tables.append(
                ParsedTable(
                    element_id=el_dict.get("element_id", str(uuid.uuid4())),
                    page_number=page_number,
                    html=html,
                    text=el_dict.get("text", ""),
                    bbox=bbox,
                    confidence=confidence,
                )
            )

    full_text = "\n\n".join(pe.text for pe in parsed_elements if pe.text)

    return ParsedDocument(
        document_id=str(uuid.uuid4()),
        filename=filename,
        original_extension=ext,
        stored_path=str(file_path),
        strategy_used=strategy_used,
        element_count=len(parsed_elements),
        table_count=len(tables),
        elements=parsed_elements,
        tables=tables,
        full_text=full_text,
        warnings=warnings,
    )
