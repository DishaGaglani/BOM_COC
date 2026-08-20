from rapidfuzz import fuzz

from app.llm.ollama_client import OllamaClient
from app.llm.prompts import build_field_extraction_prompt
from app.schemas.canonical import DocumentExtractionResult, ExtractedField, RawTextBlock, BBox


def _blocks_text(blocks: list[RawTextBlock], max_chars: int = 12000) -> str:
    lines = [f"[p{b.page}] {b.text}" for b in blocks]
    text = "\n".join(lines)
    return text[:max_chars]


def _locate_bbox(value: str, page_hint: int | None, blocks: list[RawTextBlock]) -> tuple[int | None, BBox | None]:
    """The LLM returns field values as text, not coordinates. Find the
    RawTextBlock that best matches the value (preferring the LLM's page
    hint) so the value can still be highlighted on the original PDF."""
    if not value:
        return page_hint, None

    candidates = [b for b in blocks if page_hint is None or b.page == page_hint] or blocks
    best_block, best_score = None, 0.0
    for b in candidates:
        score = fuzz.partial_ratio(value.lower(), b.text.lower())
        if score > best_score:
            best_block, best_score = b, score

    if best_block and best_score >= 60:
        return best_block.page, best_block.bbox
    return page_hint, None


def extract_fields_with_llm(
    extraction: DocumentExtractionResult, doc_kind: str = "COC", client: OllamaClient | None = None
) -> list[ExtractedField]:
    """Runs the local Ollama model over the raw extracted text to produce
    canonical fields (architecture doc sections 4.4 / 9), then re-attaches
    page/bbox by matching each value back to its source RawTextBlock."""
    client = client or OllamaClient()
    prompt = build_field_extraction_prompt(_blocks_text(extraction.raw_blocks), doc_kind=doc_kind)

    result = client.generate_json(prompt)
    raw_fields = result.get("fields", [])

    fields: list[ExtractedField] = []
    for rf in raw_fields:
        name = rf.get("field_name")
        value = str(rf.get("field_value", "")).strip()
        if not name or not value:
            continue

        page_hint = rf.get("page")
        page, bbox = _locate_bbox(value, page_hint, extraction.raw_blocks)

        fields.append(
            ExtractedField(
                field_name=name,
                field_value=value,
                confidence=float(rf.get("confidence", 0.7)),
                page=page,
                bbox=bbox,
                extraction_method="llm",
                raw_label=rf.get("raw_label"),
            )
        )

    return fields
