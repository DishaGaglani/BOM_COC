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


def test_seal_pattern_recognizes_real_compliance_phrasings():
    for text in [
        "This certificate bears the Company Seal.",
        "Official Stamp affixed below.",
        "Seal & Signature of Authorized Signatory",
        "Signature and Seal",
        "Seal of the Company",
        "Sealed by the Company on this date",
    ]:
        fields = extract_presence_fields([_element(text)])
        assert any(f.field_name == "seal" for f in fields), f"expected a seal match in: {text!r}"


def test_seal_pattern_ignores_seal_as_a_part_description():
    # Regression: a bare `seal` match used to false-PASS the compliance
    # check on any BOM/COC line mentioning a gasket/O-ring/rubber seal.
    for text in [
        "The enclosure is sealed for weatherproofing.",
        "Rubber seal, part no. RS-100",
        "O-ring seal assembly included",
        "Vacuum sealed packaging",
        "Seal replacement kit",
    ]:
        fields = extract_presence_fields([_element(text)])
        assert not any(f.field_name == "seal" for f in fields), f"unexpected seal match in: {text!r}"
