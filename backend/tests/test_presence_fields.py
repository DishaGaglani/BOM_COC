from app.parameters.presence_fields import extract_presence_fields
from app.parsing.schema import ParsedElement


def _element(text: str) -> ParsedElement:
    return ParsedElement(element_id="e1", type="NarrativeText", text=text, page_number=1)


def test_detects_each_compliance_marker():
    text = (
        "This certificate is signed by the Authorised Signatory and bears the company seal. "
        "Test Certificate No. TC-1234 is attached along with the Bill of Entry and a "
        "Letter of Authorisation."
    )
    fields = extract_presence_fields([_element(text)])
    found = {f.field_name for f in fields}
    assert found == {"signature", "seal", "test_certificate", "import_documents", "authorization_letter"}


def test_no_markers_present_returns_empty():
    fields = extract_presence_fields([_element("Plain shipment note with no compliance language.")])
    assert fields == []


def test_only_matches_each_field_once_across_elements():
    elements = [_element("Signature: John Doe"), _element("Signed by: Jane Doe")]
    fields = extract_presence_fields(elements)
    assert len([f for f in fields if f.field_name == "signature"]) == 1
