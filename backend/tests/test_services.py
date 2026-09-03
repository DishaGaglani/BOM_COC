"""End-to-end coverage through the real ingest_bom / ingest_and_validate_coc
services (not just the matching unit in isolation), so the #1 fix is proven
all the way from a parsed document down to the persisted COC's validations —
including that an ambiguous match surfaces as its own WARNING row rather
than silently validating against the wrong BOM line.

Extraction itself (mapping a raw document to BOMItem/ExtractedField) is the
semantic agent's job now (app/services/semantic_extractor.py) — these tests
aren't about extraction quality, so bom_service.extract_bom /
coc_service.extract_coc are monkeypatched to return fixture-built items
directly (see tests/factories.py), keeping this suite fast and offline like
the rest of tests/.
"""

import pytest
from pathlib import Path

from app.services import bom_service, coc_service
from app.services.bom_service import ingest_bom
from app.services.coc_service import ingest_and_validate_coc
from app.parameters.storage import load_coc
from tests.factories import make_bom_item, make_field, make_parsed_document

# Any real PDF works here — ingest_and_validate_coc's annotation step just
# needs a file fitz can open; none of our test fields carry a bbox, so zero
# highlights actually get drawn.
_SAMPLE_PDF = Path(__file__).resolve().parents[2] / "review" / "49COC.pdf"


def _patch_bom_extraction(monkeypatch, items, contract_date=None):
    async def fake_extract_bom(document):
        return items, contract_date

    monkeypatch.setattr(bom_service, "extract_bom", fake_extract_bom)


def _patch_coc_extraction(monkeypatch, fields):
    async def fake_extract_coc(document):
        return fields

    monkeypatch.setattr(coc_service, "extract_coc", fake_extract_coc)


async def _ingest_bom(monkeypatch, project_id, items, contract_date="2026-01-01"):
    _patch_bom_extraction(monkeypatch, items)
    return await ingest_bom(project_id, make_parsed_document(filename="bom.xlsx"), contract_date=contract_date)


async def _ingest_coc(monkeypatch, bom, fields):
    _patch_coc_extraction(monkeypatch, fields)
    return await ingest_and_validate_coc(bom, make_parsed_document(filename="coc.pdf"), _SAMPLE_PDF)


@pytest.mark.asyncio
async def test_coc_matches_unique_bom_line_and_passes(monkeypatch):
    bom = await _ingest_bom(
        monkeypatch, "proj-1",
        [make_bom_item(part_id="ABC-123", description="Circuit Breaker", quantity=10, po_number="PO-1")],
    )

    coc = await _ingest_coc(monkeypatch, bom, [
        make_field("part_id", "ABC-123"),
        make_field("po_numbers", "PO-1"),
        make_field("quantity", "10"),
    ])

    assert coc.matched_item_id == bom.items[0].item_id
    quantity_result = next(v for v in coc.validations if v.parameter == "quantity")
    assert quantity_result.status == "PASS"
    assert not any(v.parameter == "bom_match" for v in coc.validations)


@pytest.mark.asyncio
async def test_coc_ambiguous_match_is_flagged_not_silently_matched_to_wrong_line(monkeypatch):
    bom = await _ingest_bom(
        monkeypatch, "proj-2",
        [
            make_bom_item(part_id="ABC-123", description="Circuit Breaker", quantity=10, po_number="PO-1"),
            make_bom_item(part_id="ABC-123", description="Circuit Breaker", quantity=10, po_number="PO-1"),
        ],
    )

    coc = await _ingest_coc(monkeypatch, bom, [
        make_field("part_id", "ABC-123"),
        make_field("po_numbers", "PO-1"),
        make_field("quantity", "10"),
    ])

    assert coc.matched_item_id is None
    bom_match = next(v for v in coc.validations if v.parameter == "bom_match")
    assert bom_match.status == "WARNING"
    assert "2 BOM lines" in bom_match.reason


@pytest.mark.asyncio
async def test_coc_no_match_is_flagged_distinctly_from_ambiguous(monkeypatch):
    bom = await _ingest_bom(
        monkeypatch, "proj-3",
        [make_bom_item(part_id="ABC-123", description="Circuit Breaker", quantity=10)],
    )

    coc = await _ingest_coc(monkeypatch, bom, [
        make_field("part_id", "DOES-NOT-EXIST"),
        make_field("quantity", "10"),
    ])

    assert coc.matched_item_id is None
    bom_match = next(v for v in coc.validations if v.parameter == "bom_match")
    assert bom_match.status == "WARNING"
    assert "No matching BOM item" in bom_match.reason


@pytest.mark.asyncio
async def test_partial_shipment_passes_and_completes_across_two_cocs(monkeypatch):
    bom = await _ingest_bom(
        monkeypatch, "proj-5",
        [make_bom_item(part_id="ABC-123", description="Circuit Breaker", quantity=100)],
    )

    first = await _ingest_coc(monkeypatch, bom, [
        make_field("part_id", "ABC-123"),
        make_field("quantity", "40"),
    ])
    first_qty = next(v for v in first.validations if v.parameter == "quantity")
    assert first_qty.status == "PASS"
    assert "Partial delivery" in first_qty.reason

    second = await _ingest_coc(monkeypatch, bom, [
        make_field("part_id", "ABC-123"),
        make_field("quantity", "60"),
    ])
    second_qty = next(v for v in second.validations if v.parameter == "quantity")
    assert second_qty.status == "PASS"
    assert "Completes the order" in second_qty.reason


@pytest.mark.asyncio
async def test_third_coc_exceeding_bom_total_fails(monkeypatch):
    bom = await _ingest_bom(
        monkeypatch, "proj-6",
        [make_bom_item(part_id="ABC-123", description="Circuit Breaker", quantity=100)],
    )

    await _ingest_coc(monkeypatch, bom, [make_field("part_id", "ABC-123"), make_field("quantity", "60")])
    await _ingest_coc(monkeypatch, bom, [make_field("part_id", "ABC-123"), make_field("quantity", "30")])
    third = await _ingest_coc(monkeypatch, bom, [make_field("part_id", "ABC-123"), make_field("quantity", "20")])

    third_qty = next(v for v in third.validations if v.parameter == "quantity")
    assert third_qty.status == "FAIL"
    assert "exceeds BOM" in third_qty.reason


@pytest.mark.asyncio
async def test_annotation_failure_does_not_prevent_coc_from_being_saved(monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("simulated PyMuPDF failure (e.g. malformed bbox / corrupt PDF)")

    monkeypatch.setattr(coc_service, "annotate_pdf", _boom)

    bom = await _ingest_bom(
        monkeypatch, "proj-7",
        [make_bom_item(part_id="ABC-123", description="Circuit Breaker", quantity=10)],
    )

    # Must not raise, even though annotate_pdf always throws.
    coc = await _ingest_coc(monkeypatch, bom, [make_field("part_id", "ABC-123"), make_field("quantity", "10")])

    assert coc.matched_item_id == bom.items[0].item_id
    # And the validation result itself made it to disk despite the failure.
    assert load_coc(coc.coc_id) is not None


@pytest.mark.asyncio
async def test_quantity_tiebreaker_resolves_duplicate_part_across_two_lots(monkeypatch):
    bom = await _ingest_bom(
        monkeypatch, "proj-4",
        [
            make_bom_item(part_id="ABC-123", description="Circuit Breaker", quantity=10, po_number="PO-1"),
            make_bom_item(part_id="ABC-123", description="Circuit Breaker", quantity=25, po_number="PO-1"),
        ],
    )

    coc = await _ingest_coc(monkeypatch, bom, [
        make_field("part_id", "ABC-123"),
        make_field("po_numbers", "PO-1"),
        make_field("quantity", "25"),
    ])

    assert coc.matched_item_id == bom.items[1].item_id
    quantity_result = next(v for v in coc.validations if v.parameter == "quantity")
    assert quantity_result.status == "PASS"
