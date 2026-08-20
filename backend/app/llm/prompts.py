from app.schemas.canonical import CANONICAL_FIELDS

FIELD_EXTRACTION_PROMPT = """You are extracting structured data from a {doc_kind} document for an \
industrial supply-chain compliance system. Below is the raw text extracted from the document \
(page markers like [p1] indicate which page each line came from).

Extract every occurrence of the following canonical fields. Field names in the source document may \
use different terminology (e.g. "P/N", "Part No.", "Component ID" all mean part_id; \
"OEM", "Manufactured by", "Supplier" all mean manufacturer). Map them to the canonical name.

Canonical fields: {fields}

For each field you find, return an object with:
- "field_name": one of the canonical field names above
- "field_value": the extracted value, verbatim from the document
- "raw_label": the exact label/term used in the source document for this field
- "page": the page number (integer) where this value appears
- "confidence": your confidence (0.0-1.0) that this extraction is correct

If a field is not present in the document, omit it entirely — do not guess or invent values.
If multiple part items appear (e.g. a BOM table with many rows), extract each row's fields separately \
and repeat document_type/PO fields as needed per row.

Return ONLY a JSON object of the form: {{"fields": [ {{...}}, {{...}} ]}}

Document text:
---
{document_text}
---
"""


def build_field_extraction_prompt(document_text: str, doc_kind: str = "COC") -> str:
    return FIELD_EXTRACTION_PROMPT.format(
        doc_kind=doc_kind,
        fields=", ".join(CANONICAL_FIELDS),
        document_text=document_text,
    )
