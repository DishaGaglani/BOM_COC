from app.schemas.canonical import ExtractedField

# Fields where an exact deterministic match should win over an LLM guess
# (architecture doc section 10 — "Preferred Validation: Exact / normalized match").
RULE_PREFERRED_FIELDS = {"po_numbers", "part_id", "model", "serial_numbers", "quantity"}


def merge_fields(rule_fields: list[ExtractedField], llm_fields: list[ExtractedField]) -> list[ExtractedField]:
    """Combine rule-based and LLM-extracted fields into one list. For
    RULE_PREFERRED_FIELDS, rule-based hits suppress LLM hits with the same
    field_name+value already covered; otherwise both extractions are kept
    so the validation engine (or a human reviewer) can see full provenance."""
    merged = list(rule_fields)
    rule_values = {(f.field_name, f.field_value.strip().lower()) for f in rule_fields}

    for f in llm_fields:
        if f.field_name in RULE_PREFERRED_FIELDS:
            if any(rn == f.field_name for rn, _ in rule_values):
                # A rule-based extraction already exists for this critical
                # field; skip the LLM duplicate to avoid conflicting values.
                if (f.field_name, f.field_value.strip().lower()) not in rule_values:
                    continue
        merged.append(f)

    return merged
