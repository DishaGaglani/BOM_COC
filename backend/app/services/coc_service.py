import uuid
from pathlib import Path

from app.annotation.pdf_annotator import annotate_pdf
from app.config import settings
from app.parameters.extractor import extract_coc
from app.parameters.schema import BOM, COC, Validation
from app.parameters.storage import save_coc
from app.parsing.schema import ParsedDocument
from app.validation.engine import run_validation
from app.validation.matching import match_bom_item
from app.validation.rules import RuleResult

_NO_MATCH_RESULT = RuleResult(
    "bom_match", None, None, "WARNING",
    "No matching BOM item found for this COC — manual review required",
)


def ingest_and_validate_coc(bom: BOM, document: ParsedDocument, source_pdf_path: Path) -> COC:
    fields = extract_coc(document)
    matched_item = match_bom_item(bom.items, fields)

    results = run_validation(matched_item, fields)
    if matched_item is None:
        # The field-by-field checks above already ran with "nothing to
        # validate against" for every BOM-sourced expected value — this
        # just surfaces the match failure itself as its own result, rather
        # than the whole document collapsing into one unmatched-and-
        # nothing-else result.
        results = [{"rule_result": _NO_MATCH_RESULT, "source_field": None}] + results

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
        matched_item_id=matched_item.item_id if matched_item else None,
        fields=fields,
        validations=validations,
    )
    save_coc(coc)

    # Highlighted PDF — always produced, even with zero usable annotations
    # (no BOM match, or no extracted field carried a bbox): annotate_pdf
    # just copies the source through unchanged in that case, so the
    # highlighted-pdf endpoint doesn't 404 for every COC that didn't happen
    # to get annotations.
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
    annotate_pdf(str(source_pdf_path), str(out_path), annotations)

    return coc
