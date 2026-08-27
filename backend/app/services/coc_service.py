import logging
import uuid
from pathlib import Path

from app.annotation.pdf_annotator import annotate_pdf
from app.config import settings
from app.parameters.extractor import extract_coc
from app.parameters.schema import BOM, BOMItem, COC, Validation
from app.parameters.storage import list_cocs_for_bom, save_coc
from app.parsing.schema import ParsedDocument
from app.services.gemma_validator import semantic_validate
from app.validation.engine import run_validation
from app.validation.matching import match_bom_item
from app.validation.normalize import parse_quantity
from app.validation.rules import RuleResult

logger = logging.getLogger(__name__)

_UNMATCHED_RESULT = RuleResult(
    "bom_match", None, None, "WARNING",
    "No matching BOM item found for this COC — manual review required",
)


def _ambiguous_match_result(candidates: list[BOMItem]) -> RuleResult:
    labels = ", ".join(c.part_id or c.po_number or c.item_id for c in candidates)
    return RuleResult(
        "bom_match", None, labels, "WARNING",
        f"COC matches {len(candidates)} BOM lines with the same Part ID/PO Number and "
        f"the same quantity ({labels}) — manual review required to pick the right line",
    )


def _previously_delivered_quantity(bom_id: str, matched_item_id: str) -> float:
    """Sums the quantity already validated on other COCs matched to this
    same BOM line, so a split shipment (goods arriving in separate lots) can
    be checked lot-by-lot against the BOM's total ordered quantity instead
    of every COC after the first one being flagged as a mismatch. Reads
    back each prior COC's own recorded quantity validation rather than
    re-extracting its fields, since that's the exact figure it was already
    validated with."""
    total = 0.0
    for existing in list_cocs_for_bom(bom_id):
        if existing.matched_item_id != matched_item_id:
            continue
        qty_validation = next((v for v in existing.validations if v.parameter == "quantity"), None)
        if qty_validation and qty_validation.actual_value:
            qty = parse_quantity(qty_validation.actual_value)
            if qty is not None:
                total += qty
    return total


async def ingest_and_validate_coc(bom: BOM, document: ParsedDocument, source_pdf_path: Path) -> COC:
    fields = extract_coc(document)
    match = match_bom_item(bom.items, fields)

    previously_delivered = _previously_delivered_quantity(bom.bom_id, match.item.item_id) if match.item else 0.0

    # Tier 1: fast rule-based validation (identity, format, date checks, etc.)
    fast_results = run_validation(match.item, fields, contract_date=bom.contract_date, previously_delivered_quantity=previously_delivered)

    # Tier 2: semantic validation via Gemma (if configured and match succeeded)
    # Gemma is only called after a successful match, since there's nothing to
    # validate semantically against a non-existent BOM line.
    gemma_results: list[dict] = []
    if match.item is not None and match.status == "matched":
        gemma_results = await semantic_validate(match.item, fields, contract_date=bom.contract_date)

    # Combine fast + semantic results, with Gemma results appended so they're
    # visible at the end of the report.
    results = fast_results + gemma_results

    # The field-by-field checks above already ran with "nothing to validate
    # against" for every BOM-sourced expected value when there's no single
    # matched line — this just surfaces the match outcome itself as its own
    # result, rather than the whole document collapsing into one
    # unmatched-and-nothing-else result. Ambiguous is kept distinct from
    # unmatched: unmatched means no BOM line looks like this COC at all,
    # ambiguous means several equally plausible lines do and a human needs
    # to pick — very different problems for a reviewer to act on.
    if match.status == "unmatched":
        results = [{"rule_result": _UNMATCHED_RESULT, "source_field": None}] + results
    elif match.status == "ambiguous":
        results = [{"rule_result": _ambiguous_match_result(match.candidates), "source_field": None}] + results

    validations = [
        Validation(
            parameter=r["rule_result"].parameter,
            expected_value=r["rule_result"].expected_value,
            actual_value=r["rule_result"].actual_value,
            status=r["rule_result"].status,
            reason=r["rule_result"].reason,
        )
        for r in results
    ]

    coc = COC(
        coc_id=str(uuid.uuid4()),
        bom_id=bom.bom_id,
        parsed_document_id=document.document_id,
        filename=document.filename,
        matched_item_id=match.item.item_id if match.item else None,
        fields=fields,
        validations=validations,
    )
    save_coc(coc)

    # Highlighted PDF — always attempted, even with zero usable annotations
    # (no BOM match, or no extracted field carried a bbox): annotate_pdf
    # just copies the source through unchanged in that case, so the
    # highlighted-pdf endpoint doesn't 404 for every COC that didn't happen
    # to get annotations.
    #
    # The COC record above is already saved and is the actual compliance
    # result — the highlighted PDF is a presentation nicety on top of it.
    # If annotate_pdf throws (a malformed bbox, an encrypted/corrupt source
    # PDF, ...), that must not take down an otherwise-successful validation:
    # without this, one bad file in a batch upload (main.py's per-file loop
    # has no try/except around this call) would raise past every COC
    # already validated and saved in that same request, so the API caller
    # never even sees results it should have gotten back. Degrade instead —
    # log it and leave the highlighted-pdf endpoint to 404 for this one COC.
    annotations = [
        {
            "page": r["source_field"].page_number,
            "bbox": r["source_field"].bbox.model_dump(),
            "parameter": r["rule_result"].parameter,
            "status": r["rule_result"].status,
            "comment": r["rule_result"].reason,
        }
        for r in results
        if r["source_field"] is not None and r["source_field"].bbox is not None
    ]
    out_path = settings.highlighted_dir / f"{coc.coc_id}.pdf"
    try:
        annotate_pdf(str(source_pdf_path), str(out_path), annotations)
    except Exception:
        logger.exception(
            "Failed to build highlighted PDF for COC %s (%s) — validation result is unaffected",
            coc.coc_id, coc.filename,
        )

    return coc
