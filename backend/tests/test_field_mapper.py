from app.parameters.field_mapper import extract_inline_fields, extract_po_fallback
from app.parsing.schema import ParsedElement


def _element(text: str) -> ParsedElement:
    return ParsedElement(element_id="e1", type="NarrativeText", text=text, page_number=1)


def test_inline_label_value_extraction():
    fields = extract_inline_fields([_element("PO Number: PO-45892")])
    assert len(fields) == 1
    assert fields[0].field_name == "po_numbers"
    assert fields[0].field_value == "PO-45892"


def test_inline_extraction_ignores_unknown_labels():
    fields = extract_inline_fields([_element("Notes: see attached schedule")])
    assert fields == []


def test_inline_extraction_handles_dash_separator():
    fields = extract_inline_fields([_element("Model No - XL-500")])
    assert len(fields) == 1
    assert fields[0].field_name == "model"
    assert fields[0].field_value == "XL-500"


def test_po_fallback_pulls_po_number_out_of_prose():
    text = "This is to certify goods supplied against your Po no.06L035807/ANIL POOJARI as per order."
    fields = extract_po_fallback([_element(text)])
    assert len(fields) == 1
    assert fields[0].field_name == "po_numbers"
    assert fields[0].field_value == "06L035807"


def test_po_fallback_no_match_returns_empty():
    fields = extract_po_fallback([_element("No purchase order mentioned here.")])
    assert fields == []
