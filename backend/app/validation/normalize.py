import re


def normalize_identifier(value: str) -> str:
    """Light normalization for exact-match identifiers (PO, Part ID, Model,
    Serial): trims, uppercases, and collapses internal whitespace, but does
    NOT strip separators like '-' since those are often significant in
    part/PO numbering schemes."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", value.strip()).upper()


def parse_quantity(value: str) -> float | None:
    if value is None:
        return None
    match = re.search(r"-?\d+(\.\d+)?", str(value).replace(",", ""))
    return float(match.group()) if match else None
