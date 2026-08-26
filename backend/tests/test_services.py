"""End-to-end coverage through the real ingest_bom / ingest_and_validate_coc
services (not just the matching unit in isolation), so the #1 fix is proven
all the way from a parsed document down to the persisted COC's validations —
including that an ambiguous match surfaces as its own WARNING row rather
than silently validating against the wrong BOM line.
"""

from pathlib import Path

from app.parameters.storage import load_coc
from app.services import coc_service
from app.services.bom_service import ingest_bom
from app.services.coc_service import ingest_and_validate_coc
from tests.factories import make_parsed_document

# Any real PDF works here — ingest_and_validate_coc's annotation step just
# needs a file fitz can open; none of our test fields carry a bbox, so zero
# highlights actually get drawn.
_SAMPLE_PDF = Path(__file__).resolve().parents[2] / "review" / "49COC.pdf"


def _bom_document(rows: list[list[str]]) -> "object":
    return make_parsed_document(table_rows=rows, filename="bom.xlsx")


def _coc_document(rows: list[list[str]] | None = None, text_lines: list[str] | None = None):
    return make_parsed_document(table_rows=rows, text_elements=text_lines, filename="coc.pdf")


def test_coc_matches_unique_bom_line_and_passes():
    bom = ingest_bom(
        "proj-1",
        _bom_document(
            [
                ["Part No.", "Description", "Qty", "PO No."],
                ["ABC-123", "Circuit Breaker", "10", "PO-1"],
            ]
        ),
        contract_date="2026-01-01",
    )

    coc = ingest_and_validate_coc(
        bom,
        _coc_document([["Part No.", "PO No.", "Qty"], ["ABC-123", "PO-1", "10"]]),
        _SAMPLE_PDF,
    )

    assert coc.matched_item_id == bom.items[0].item_id
    quantity_result = next(v for v in coc.validations if v.parameter == "quantity")
    assert quantity_result.status == "PASS"
    assert not any(v.parameter == "bom_match" for v in coc.validations)


def test_coc_ambiguous_match_is_flagged_not_silently_matched_to_wrong_line():
    bom = ingest_bom(
        "proj-2",
        _bom_document(
            [
                ["Part No.", "Description", "Qty", "PO No."],
                ["ABC-123", "Circuit Breaker", "10", "PO-1"],
                ["ABC-123", "Circuit Breaker", "10", "PO-1"],
            ]
        ),
        contract_date="2026-01-01",
    )

    coc = ingest_and_validate_coc(
        bom,
        _coc_document([["Part No.", "PO No.", "Qty"], ["ABC-123", "PO-1", "10"]]),
        _SAMPLE_PDF,
    )

    assert coc.matched_item_id is None
    bom_match = next(v for v in coc.validations if v.parameter == "bom_match")
    assert bom_match.status == "WARNING"
    assert "2 BOM lines" in bom_match.reason


def test_coc_no_match_is_flagged_distinctly_from_ambiguous():
    bom = ingest_bom(
        "proj-3",
        _bom_document([["Part No.", "Description", "Qty"], ["ABC-123", "Circuit Breaker", "10"]]),
        contract_date="2026-01-01",
    )

    coc = ingest_and_validate_coc(
        bom,
        _coc_document([["Part No.", "Qty"], ["DOES-NOT-EXIST", "10"]]),
        _SAMPLE_PDF,
    )

    assert coc.matched_item_id is None
    bom_match = next(v for v in coc.validations if v.parameter == "bom_match")
    assert bom_match.status == "WARNING"
    assert "No matching BOM item" in bom_match.reason


def test_partial_shipment_passes_and_completes_across_two_cocs():
    bom = ingest_bom(
        "proj-5",
        _bom_document([["Part No.", "Description", "Qty"], ["ABC-123", "Circuit Breaker", "100"]]),
        contract_date="2026-01-01",
    )

    first = ingest_and_validate_coc(
        bom, _coc_document([["Part No.", "Qty"], ["ABC-123", "40"]]), _SAMPLE_PDF
    )
    first_qty = next(v for v in first.validations if v.parameter == "quantity")
    assert first_qty.status == "PASS"
    assert "Partial delivery" in first_qty.reason

    second = ingest_and_validate_coc(
        bom, _coc_document([["Part No.", "Qty"], ["ABC-123", "60"]]), _SAMPLE_PDF
    )
    second_qty = next(v for v in second.validations if v.parameter == "quantity")
    assert second_qty.status == "PASS"
    assert "Completes the order" in second_qty.reason


def test_third_coc_exceeding_bom_total_fails():
    bom = ingest_bom(
        "proj-6",
        _bom_document([["Part No.", "Description", "Qty"], ["ABC-123", "Circuit Breaker", "100"]]),
        contract_date="2026-01-01",
    )

    ingest_and_validate_coc(bom, _coc_document([["Part No.", "Qty"], ["ABC-123", "60"]]), _SAMPLE_PDF)
    ingest_and_validate_coc(bom, _coc_document([["Part No.", "Qty"], ["ABC-123", "30"]]), _SAMPLE_PDF)
    third = ingest_and_validate_coc(bom, _coc_document([["Part No.", "Qty"], ["ABC-123", "20"]]), _SAMPLE_PDF)

    third_qty = next(v for v in third.validations if v.parameter == "quantity")
    assert third_qty.status == "FAIL"
    assert "exceeds BOM" in third_qty.reason


def test_annotation_failure_does_not_prevent_coc_from_being_saved(monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("simulated PyMuPDF failure (e.g. malformed bbox / corrupt PDF)")

    monkeypatch.setattr(coc_service, "annotate_pdf", _boom)

    bom = ingest_bom(
        "proj-7",
        _bom_document([["Part No.", "Description", "Qty"], ["ABC-123", "Circuit Breaker", "10"]]),
        contract_date="2026-01-01",
    )

    # Must not raise, even though annotate_pdf always throws.
    coc = ingest_and_validate_coc(
        bom, _coc_document([["Part No.", "Qty"], ["ABC-123", "10"]]), _SAMPLE_PDF
    )

    assert coc.matched_item_id == bom.items[0].item_id
    # And the validation result itself made it to disk despite the failure.
    assert load_coc(coc.coc_id) is not None


def test_quantity_tiebreaker_resolves_duplicate_part_across_two_lots():
    bom = ingest_bom(
        "proj-4",
        _bom_document(
            [
                ["Part No.", "Description", "Qty", "PO No."],
                ["ABC-123", "Circuit Breaker", "10", "PO-1"],
                ["ABC-123", "Circuit Breaker", "25", "PO-1"],
            ]
        ),
        contract_date="2026-01-01",
    )

    coc = ingest_and_validate_coc(
        bom,
        _coc_document([["Part No.", "PO No.", "Qty"], ["ABC-123", "PO-1", "25"]]),
        _SAMPLE_PDF,
    )

    assert coc.matched_item_id == bom.items[1].item_id
    quantity_result = next(v for v in coc.validations if v.parameter == "quantity")
    assert quantity_result.status == "PASS"
