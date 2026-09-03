from app.parameters.schema import BOMItem, ExtractedField
from app.parsing.schema import ParsedDocument
from app.services.semantic_extractor import extract_bom as _extract_bom_semantic
from app.services.semantic_extractor import extract_coc as _extract_coc_semantic


async def extract_bom(document: ParsedDocument) -> tuple[list[BOMItem], str | None]:
    """BOM parameter extraction assumes a native table (per the confirmed
    input format) — a BOM without one isn't usable as a line-item ground
    truth, so this raises rather than returning an empty/guessed result.
    Returns (items, contract_date) — see services.semantic_extractor."""
    items, contract_date = await _extract_bom_semantic(document)
    if not items:
        raise ValueError(
            "No BOM-shaped table found in parsed document "
            f"(strategy_used={document.strategy_used!r}, table_count={document.table_count})"
        )
    return items, contract_date


async def extract_coc(document: ParsedDocument) -> list[ExtractedField]:
    """COC parameter extraction: every canonical field the semantic
    extraction agent can find in the document — table cells, inline text,
    compliance-element mentions — resolved to one value per field rather
    than the old rule-based pipeline's unarbitrated pile of candidates.
    See services.semantic_extractor for the extraction contract."""
    return await _extract_coc_semantic(document)
