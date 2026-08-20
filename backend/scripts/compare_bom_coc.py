#!/usr/bin/env python3
"""Standalone BOM/COC comparison script — no DB, no FastAPI, no LLM required.

    python scripts/compare_bom_coc.py <bom.pdf> <coc.pdf>

Extracts canonical fields from both PDFs using the same rule-based
extraction the app uses (table parsing + inline label:value regex + PO
fallback regex), falling back to OCR for scanned documents. Matches the
COC to a BOM line item by Part ID (falling back to PO Number), then runs
the same validation rules as the web app, and prints a plain-text report.
"""
import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.extraction.pipeline import run_extraction
from app.normalization.field_mapper import extract_rule_based_fields, extract_po_fallback
from app.normalization.table_field_extractor import extract_table_fields
from app.normalization.presence_fields import extract_presence_fields
from app.services.bom_parser import parse_bom_tables
from app.validation.engine import run_validation
from app.validation.normalize import normalize_identifier, parse_quantity


CORE_FIELDS = {"part_id", "description", "manufacturer", "model", "quantity", "po_numbers"}


def build_bom_items(bom_path: str) -> list[SimpleNamespace]:
    """Mirrors bom_service.ingest_bom's row -> BOMItem mapping, minus the DB."""
    rows = parse_bom_tables(bom_path)
    items = []
    for row in rows:
        items.append(
            SimpleNamespace(
                part_id=row.get("part_id"),
                description=row.get("description"),
                manufacturer=row.get("manufacturer"),
                model=row.get("model"),
                quantity=parse_quantity(row.get("quantity")) if row.get("quantity") else None,
                po_number=row.get("po_numbers"),
                requirements={k: v for k, v in row.items() if k not in CORE_FIELDS},
            )
        )
    return items


def extract_coc_fields(coc_path: str, filename: str) -> list:
    """Rule-based-only extraction (no LLM): table cells, inline label:value
    lines, and a PO-in-prose fallback. Falls back to OCR automatically for
    scanned documents via run_extraction."""
    extraction = run_extraction(coc_path, filename)
    fields = extract_rule_based_fields(extraction.raw_blocks)
    fields += extract_table_fields(coc_path)
    if not any(f.field_name == "po_numbers" for f in fields):
        fields += extract_po_fallback(extraction.raw_blocks)
    fields += extract_presence_fields(extraction.raw_blocks)
    return fields, extraction.is_scanned


def match_bom_item(bom_items: list[SimpleNamespace], coc_fields: list) -> SimpleNamespace | None:
    """Mirrors coc_service._match_bom_item: Part ID first, then PO Number."""
    part_id_values = [f.field_value for f in coc_fields if f.field_name == "part_id"]
    po_values = [f.field_value for f in coc_fields if f.field_name == "po_numbers"]

    for item in bom_items:
        if item.part_id and any(normalize_identifier(item.part_id) == normalize_identifier(v) for v in part_id_values):
            return item
    for item in bom_items:
        if item.po_number and any(normalize_identifier(item.po_number) == normalize_identifier(v) for v in po_values):
            return item
    return None


def print_report(coc_filename: str, is_scanned: bool, matched_item, results: list[dict]) -> None:
    print(f"\n{'=' * 60}")
    print(f"COC: {coc_filename}  ({'scanned/OCR' if is_scanned else 'native text layer'})")
    print(f"{'=' * 60}")

    if matched_item is None:
        print("  NO MATCHING BOM ITEM FOUND — showing whatever was extracted from the COC itself\n")
    else:
        print(f"  Matched BOM item: part_id={matched_item.part_id}  po={matched_item.po_number}  qty={matched_item.quantity}")
    print(f"  {'-' * 56}")
    for r in results:
        rr = r["rule_result"]
        marker = {"PASS": "PASS", "FAIL": "FAIL", "WARNING": "WARN"}[rr.status]
        print(f"  [{marker}] {rr.parameter:<22} expected={str(rr.expected_value):<20} actual={str(rr.actual_value):<20} {rr.reason}")
    print()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("bom_pdf")
    parser.add_argument("coc_pdf")
    args = parser.parse_args()

    print(f"Parsing BOM: {args.bom_pdf}")
    bom_items = build_bom_items(args.bom_pdf)
    print(f"  {len(bom_items)} BOM line item(s) found")

    coc_filename = Path(args.coc_pdf).name
    print(f"Extracting COC: {coc_filename}")
    coc_fields, is_scanned = extract_coc_fields(args.coc_pdf, coc_filename)
    print(f"  {len(coc_fields)} field(s) extracted ({'OCR' if is_scanned else 'native'} path)")

    matched_item = match_bom_item(bom_items, coc_fields)
    results = run_validation(matched_item, coc_fields)

    print_report(coc_filename, is_scanned, matched_item, results)


if __name__ == "__main__":
    main()
