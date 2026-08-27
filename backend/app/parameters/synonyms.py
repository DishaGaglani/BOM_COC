# Document-term -> canonical field map (architecture doc section 9).
# Verified against real L&T BOM/COC samples during the original Phase 1
# build; carried forward unchanged into the unstructured.io-based rewrite.

from rapidfuzz import fuzz

FIELD_SYNONYMS: dict[str, str] = {
    "part no": "part_id",
    "part number": "part_id",
    "part no.": "part_id",
    "p/n": "part_id",
    "component id": "part_id",
    "component no": "part_id",
    "component no.": "part_id",
    "item code": "part_id",

    # Customer's own catalog number. Suppliers echo this back as "Item No."
    # or "CPN" (Customer Part Number) far more reliably than the
    # manufacturer's own "Part No.", so these outrank the part_id synonyms
    # above — see table_headers.FIELD_LABEL_PRIORITY.
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

    # BOM/project-level, not a per-item field — what a COC's issue date
    # gets checked against (requirement #10). "PO date" is treated as a
    # stand-in for the contract's effective date when no separate
    # "Contract Date" is stated.
    "contract date": "contract_date",
    "contract effective date": "contract_date",
    "effective date": "contract_date",
    "po date": "contract_date",
    "date of po": "contract_date",

    # Whether a BOM line item is an imported part — gates whether import
    # documents (requirement #7) are actually required for it, rather than
    # always being expected.
    "imported": "is_imported",
    "import required": "is_imported",
    "is imported": "is_imported",

    "description": "description",
    "item description": "description",
}


def normalize_label(raw_label: str) -> str | None:
    if not raw_label:
        return None
    key = raw_label.strip().lower().rstrip(":")
    return FIELD_SYNONYMS.get(key) or _fuzzy_match(key)


# A typo'd/unseen header ("Pat No.", "Qnty") shouldn't just fall through and
# silently drop the whole column (or, for a BOM, the whole table) — but
# character-level fuzzy matching alone is NOT safe here. FIELD_SYNONYMS
# deliberately contains near-duplicate strings for genuinely DIFFERENT
# fields: "manufactured" (-> manufacturing_year) vs "manufacturer"
# (-> manufacturer) score ~92% similar by plain ratio; "part number"
# (-> part_id) vs "po number" (-> po_numbers) score 80%. A bare top-1 fuzzy
# match risks silently mapping a column to the WRONG field, which is worse
# than not mapping it at all. So the best match must also beat the best
# match for every other canonical field by a healthy margin — a near-tie
# between two different fields (e.g. a truncated "manufactur", genuinely
# ambiguous between the two) is left unmapped rather than guessed.
_FUZZY_SCORE_THRESHOLD = 80
_FUZZY_MARGIN_THRESHOLD = 10


def _fuzzy_match(key: str) -> str | None:
    best_per_field: dict[str, float] = {}
    for synonym, field in FIELD_SYNONYMS.items():
        score = fuzz.ratio(key, synonym)
        if score > best_per_field.get(field, -1.0):
            best_per_field[field] = score

    if not best_per_field:
        return None

    ranked = sorted(best_per_field.items(), key=lambda item: item[1], reverse=True)
    top_field, top_score = ranked[0]
    runner_up_score = ranked[1][1] if len(ranked) > 1 else 0.0

    if top_score >= _FUZZY_SCORE_THRESHOLD and (top_score - runner_up_score) >= _FUZZY_MARGIN_THRESHOLD:
        return top_field
    return None
