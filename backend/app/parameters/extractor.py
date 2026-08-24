from app.parameters.field_mapper import extract_inline_fields, extract_po_fallback
from app.parameters.presence_fields import extract_presence_fields
from app.parameters.schema import BOMItem, ExtractedField
from app.parameters.table_extractor import extract_bom_line_items, extract_coc_table_fields
from app.parsing.schema import ParsedDocument


def extract_bom(document: ParsedDocument) -> list[BOMItem]:
    """BOM parameter extraction assumes a native table (per the confirmed
    input format) — a BOM without one isn't usable as a line-item ground
    truth, so this raises rather than returning an empty/guessed result."""
    items = extract_bom_line_items(document)
    if not items:
        raise ValueError(
            "No BOM-shaped table found in parsed document "
            f"(strategy_used={document.strategy_used!r}, table_count={document.table_count})"
        )
    return items


def extract_coc(document: ParsedDocument) -> list[ExtractedField]:
    """COC parameter extraction combines every rule-based signal available:
    table cells, inline label:value text, a PO-number prose fallback, and
    presence-only compliance markers. All are kept (no LLM to arbitrate
    conflicts yet) so a human/validation-engine reviewer sees full
    provenance rather than one arbitrarily-chosen value per field."""
    return [
        *extract_coc_table_fields(document),
        *extract_inline_fields(document.elements),
        *extract_po_fallback(document.elements),
        *extract_presence_fields(document.elements),
    ]
