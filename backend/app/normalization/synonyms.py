# Document-term -> canonical field map (architecture doc section 9).
# Used as a deterministic fallback/cross-check alongside LLM extraction,
# and to pre-label raw blocks before they're sent to the model.

FIELD_SYNONYMS: dict[str, str] = {
    "part no": "part_id",
    "part number": "part_id",
    "part no.": "part_id",
    "p/n": "part_id",
    "component id": "part_id",
    "component no": "part_id",
    "component no.": "part_id",
    "item code": "part_id",

    # Customer's own catalog number. Verified against real L&T BOM/COC
    # samples: suppliers echo this back as "Item No." or "CPN" (Customer
    # Part Number) far more reliably than the manufacturer's own "Part No.",
    # so these outrank the part_id synonyms above — see
    # table_headers.FIELD_LABEL_PRIORITY.
    "l&t cat no": "part_id",
    "l&t cat no.": "part_id",
    "item no": "part_id",
    "item no.": "part_id",
    "cpn": "part_id",

    "oem": "manufacturer",
    "manufacturer": "manufacturer",
    "manufactured by": "manufacturer",
    "supplier": "manufacturer",
    "make": "manufacturer",

    "model": "model",
    "model no": "model",
    "model no.": "model",
    "model number": "model",

    "serial no": "serial_numbers",
    "serial no.": "serial_numbers",
    "serial number": "serial_numbers",
    "s/n": "serial_numbers",

    "po number": "po_numbers",
    "po no": "po_numbers",
    "po no.": "po_numbers",
    "po.no.": "po_numbers",
    "purchase order": "po_numbers",
    "purchase order no": "po_numbers",

    "qty": "quantity",
    "quantity": "quantity",
    "qty per unit": "quantity",
    "qty (nos.)": "quantity",
    "qty(nos.)": "quantity",
    "total": "quantity",

    "manufactured": "manufacturing_year",
    "year of manufacture": "manufacturing_year",
    "yom": "manufacturing_year",

    "warranty": "warranty_expiry",
    "warranty expiry": "warranty_expiry",
    "warranty period": "warranty_expiry",

    "coc date": "coc_issue_date",
    "coc issue date": "coc_issue_date",
    "date of issue": "coc_issue_date",
    "issued on": "coc_issue_date",

    "description": "description",
    "item description": "description",
}


def normalize_label(raw_label: str) -> str | None:
    if not raw_label:
        return None
    key = raw_label.strip().lower().rstrip(":")
    return FIELD_SYNONYMS.get(key)
