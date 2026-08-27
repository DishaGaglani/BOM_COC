from app.parameters.file_signatures import matches_signature


def test_pdf_magic_bytes_accepted():
    assert matches_signature(".pdf", b"%PDF-1.4\n...") is True


def test_pdf_extension_with_wrong_content_rejected():
    # e.g. an .html payload renamed to .pdf
    assert matches_signature(".pdf", b"<html><body>not a pdf</body></html>") is False


def test_docx_and_xlsx_share_the_zip_signature():
    zip_bytes = b"PK\x03\x04rest-of-file"
    assert matches_signature(".docx", zip_bytes) is True
    assert matches_signature(".xlsx", zip_bytes) is True


def test_xls_accepts_either_ole_or_zip_signature():
    ole_bytes = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1rest"
    assert matches_signature(".xls", ole_bytes) is True
    assert matches_signature(".xls", b"not a valid xls") is False


def test_png_and_jpeg_magic_bytes():
    assert matches_signature(".png", b"\x89PNG\r\n\x1a\n...") is True
    assert matches_signature(".jpg", b"\xff\xd8\xff...") is True
    assert matches_signature(".png", b"\xff\xd8\xff...") is False


def test_unregistered_extension_has_nothing_to_check():
    # csv/tsv/txt/html/eml have no reliable magic bytes — extension alone
    # is the only signal available, so anything passes here.
    assert matches_signature(".csv", b"a,b,c\n1,2,3") is True
    assert matches_signature(".html", b"<html></html>") is True


def test_case_insensitive_extension():
    assert matches_signature(".PDF", b"%PDF-1.4") is True
