from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from app.validation.normalize import normalize_identifier_loose, parse_quantity

if TYPE_CHECKING:
    from app.parameters.schema import BOMItem, ExtractedField

MatchStatus = Literal["matched", "ambiguous", "unmatched"]


@dataclass
class MatchResult:
    item: "BOMItem | None"
    status: MatchStatus
    # Populated only when status == "ambiguous" — the BOM lines that all
    # matched and couldn't be told apart, so the caller can surface them for
    # manual resolution instead of silently picking one.
    candidates: "list[BOMItem]" = field(default_factory=list)


def _values(coc_fields: "list[ExtractedField]", field_name: str) -> list[str]:
    return [f.field_value for f in coc_fields if f.field_name == field_name]


def _matches(item_value: "str | None", candidates: list[str]) -> bool:
    """Alphanumeric-only comparison — a BOM's stored 'PO-45892' should still
    match a COC's 'PO45892' or 'PO 45892' pulled from prose. Matching (which
    BOM line is this COC even about) is deliberately more forgiving of
    formatting than the field-by-field validation checks later (see
    rules.check_exact_match): missing a real match entirely — leaving the
    COC "unmatched" and every field check reduced to "nothing to validate
    against" — hides more than a validation check flagging a cosmetic
    difference for review does."""
    return bool(item_value) and any(normalize_identifier_loose(item_value) == normalize_identifier_loose(v) for v in candidates)


def _resolve(candidates: "list[BOMItem]", coc_quantity: float | None) -> MatchResult:
    if not candidates:
        return MatchResult(item=None, status="unmatched")
    if len(candidates) == 1:
        return MatchResult(item=candidates[0], status="matched")

    # Multiple BOM lines share this identifier — real BOMs commonly order
    # the same part across several lines (separate lots/deliveries), which
    # differ by quantity. Use it as a tiebreaker before giving up.
    if coc_quantity is not None:
        qty_matches = [c for c in candidates if c.quantity == coc_quantity]
        if len(qty_matches) == 1:
            return MatchResult(item=qty_matches[0], status="matched")

    return MatchResult(item=None, status="ambiguous", candidates=candidates)


def match_bom_item(items: "list[BOMItem]", coc_fields: "list[ExtractedField]") -> MatchResult:
    """Matches a COC to a BOM line item, most specific signal first:
    Part ID + PO Number together, then Part ID alone, then PO Number alone
    — each tier using normalized exact match, with quantity as a tiebreaker
    when a tier matches more than one BOM line. Returns "ambiguous" (rather
    than silently picking the first candidate) when a tier still can't be
    narrowed to one line, since validating against the wrong duplicate line
    would produce a wrong PASS/FAIL rather than just a missing one."""
    part_id_values = _values(coc_fields, "part_id")
    po_values = _values(coc_fields, "po_numbers")
    qty_field = next((f for f in coc_fields if f.field_name == "quantity"), None)
    coc_quantity = parse_quantity(qty_field.field_value) if qty_field else None

    if part_id_values and po_values:
        both = [item for item in items if _matches(item.part_id, part_id_values) and _matches(item.po_number, po_values)]
        result = _resolve(both, coc_quantity)
        if result.status != "unmatched":
            return result

    if part_id_values:
        by_part = [item for item in items if _matches(item.part_id, part_id_values)]
        result = _resolve(by_part, coc_quantity)
        if result.status != "unmatched":
            return result

    if po_values:
        by_po = [item for item in items if _matches(item.po_number, po_values)]
        result = _resolve(by_po, coc_quantity)
        if result.status != "unmatched":
            return result

    return MatchResult(item=None, status="unmatched")


def overall_status(statuses: list[str]) -> str:
    if "FAIL" in statuses:
        return "FAIL"
    if "WARNING" in statuses:
        return "WARNING"
    return "PASS"
