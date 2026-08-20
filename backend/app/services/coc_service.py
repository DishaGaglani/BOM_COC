from sqlalchemy.orm import Session

from app.db.models import BOM, BOMItem, COC, COCEntity, Validation, Annotation, ValidationStatus
from app.extraction.pipeline import run_extraction
from app.normalization.field_mapper import extract_rule_based_fields, extract_po_fallback
from app.normalization.table_field_extractor import extract_table_fields
from app.normalization.presence_fields import extract_presence_fields
from app.normalization.merge import merge_fields
from app.llm.field_extractor import extract_fields_with_llm
from app.llm.ollama_client import OllamaClient
from app.services.storage import save_upload, path_for
from app.validation.engine import run_validation
from app.validation.normalize import normalize_identifier
from app.annotation.pdf_annotator import annotate_pdf


def _match_bom_item(bom: BOM, coc_fields) -> BOMItem | None:
    """Matches this COC to a BOM line item by Part ID first, then PO
    Number, using normalized exact match."""
    part_id_values = [f.field_value for f in coc_fields if f.field_name == "part_id"]
    po_values = [f.field_value for f in coc_fields if f.field_name == "po_numbers"]

    for item in bom.items:
        if item.part_id and any(normalize_identifier(item.part_id) == normalize_identifier(v) for v in part_id_values):
            return item
    for item in bom.items:
        if item.po_number and any(normalize_identifier(item.po_number) == normalize_identifier(v) for v in po_values):
            return item
    return None


def ingest_and_validate_coc(db: Session, bom_id: str, filename: str, file_obj) -> COC:
    bom = db.query(BOM).filter(BOM.bom_id == bom_id).one()

    path = save_upload("coc", filename, file_obj)
    coc = COC(bom_id=bom.bom_id, filename=filename, status="pending")
    db.add(coc)
    db.flush()

    # --- Extraction (architecture doc section 8) ---
    extraction = run_extraction(path, filename)
    rule_fields = extract_rule_based_fields(extraction.raw_blocks)
    rule_fields += extract_table_fields(path)
    if not any(f.field_name == "po_numbers" for f in rule_fields):
        rule_fields += extract_po_fallback(extraction.raw_blocks)
    rule_fields += extract_presence_fields(extraction.raw_blocks)

    llm_fields = []
    client = OllamaClient()
    if client.health_check():
        try:
            llm_fields = extract_fields_with_llm(extraction, doc_kind="COC", client=client)
        except (ValueError, Exception):
            llm_fields = []  # LLM unavailable/bad output — proceed on rule-based fields only

    fields = merge_fields(rule_fields, llm_fields)
    coc.document_type = "coc"  # refined below if a document_type field was extracted
    coc.status = "extracted"

    for f in fields:
        db.add(
            COCEntity(
                coc_id=coc.coc_id,
                field_name=f.field_name,
                field_value=f.field_value,
                confidence=f.confidence,
                page=f.page,
                bbox=f.bbox.model_dump() if f.bbox else None,
                extraction_method=f.extraction_method,
            )
        )

    # --- Matching + validation (architecture doc sections 10-11) ---
    # Runs the full field-by-field check regardless of whether a BOM line
    # matched: with no match, every field just has nothing to validate
    # against (see engine._bom_expected), but whatever WAS found on the COC
    # itself — description, manufacturer, signature, etc. — still gets
    # reported and still gets highlighted, instead of the entire document
    # collapsing into one unmatched-and-nothing-else result.
    matched_item = _match_bom_item(bom, fields)
    results = run_validation(matched_item, fields)

    if matched_item is None:
        results = [{
            "rule_result": type("R", (), {
                "parameter": "bom_match", "expected_value": None, "actual_value": None,
                "status": "WARNING", "reason": "No matching BOM item found for this COC — manual review required",
            })(),
            "source_field": None,
        }] + results

    for r in results:
        rr = r["rule_result"]
        src = r["source_field"]

        db.add(
            Validation(
                coc_id=coc.coc_id,
                item_id=matched_item.item_id if matched_item else None,
                parameter=rr.parameter,
                expected_value=rr.expected_value,
                actual_value=rr.actual_value,
                status=ValidationStatus(rr.status),
                reason=rr.reason,
            )
        )

        if src and src.bbox:
            db.add(
                Annotation(
                    coc_id=coc.coc_id,
                    page=src.page,
                    bbox=src.bbox.model_dump(),
                    parameter=rr.parameter,
                    status=ValidationStatus(rr.status),
                    comment=rr.reason,
                )
            )

    coc.status = "validated"
    db.commit()
    db.refresh(coc)

    # --- Highlighted PDF (architecture doc sections 12-13) ---
    # Always produce a file at this path, even with zero annotations (e.g. no
    # BOM match, or no extracted field carried a bbox) — annotate_pdf() just
    # copies the source through unchanged in that case. Otherwise the
    # highlighted-pdf endpoint 404s forever for any COC that didn't happen to
    # get annotations, which reads as a broken download link.
    ann_payload = [
        {"page": a.page, "bbox": a.bbox, "parameter": a.parameter, "status": a.status.value, "comment": a.comment}
        for a in coc.annotations
    ]
    out_path = path_for("highlighted", f"{coc.coc_id}.pdf")
    annotate_pdf(path, out_path, ann_payload)

    return coc
