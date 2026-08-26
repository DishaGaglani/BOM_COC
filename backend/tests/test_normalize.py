from datetime import date

from app.validation.normalize import (
    normalize_identifier,
    normalize_identifier_loose,
    parse_bool_flag,
    parse_date,
    parse_quantity,
)


def test_normalize_identifier_trims_case_and_whitespace():
    assert normalize_identifier("  po-45892  ") == "PO-45892"
    assert normalize_identifier("PO   45892") == "PO 45892"


def test_normalize_identifier_keeps_separators_significant():
    # '-' and '/' are often meaningful in part/PO numbering — must NOT be
    # stripped, unlike whitespace/case.
    assert normalize_identifier("ABC-123") != normalize_identifier("ABC123")


def test_normalize_identifier_none_is_empty_string():
    assert normalize_identifier(None) == ""


def test_normalize_identifier_loose_strips_all_punctuation_and_whitespace():
    assert normalize_identifier_loose("PO-45892") == "PO45892"
    assert normalize_identifier_loose("PO 45892") == "PO45892"
    assert normalize_identifier_loose("po.45892") == "PO45892"
    assert normalize_identifier_loose("PO-45892") == normalize_identifier_loose("PO 45892")


def test_normalize_identifier_loose_none_and_empty():
    assert normalize_identifier_loose(None) == ""
    assert normalize_identifier_loose("") == ""


def test_parse_quantity_plain_and_decimal():
    assert parse_quantity("42") == 42.0
    assert parse_quantity("3.5") == 3.5


def test_parse_quantity_strips_thousands_separator():
    assert parse_quantity("1,250") == 1250.0


def test_parse_quantity_extracts_number_from_units_text():
    assert parse_quantity("100 pcs") == 100.0


def test_parse_quantity_no_number_returns_none():
    assert parse_quantity("N/A") is None


def test_parse_date_iso_and_slash_formats():
    assert parse_date("2026-08-12") == date(2026, 8, 12)
    assert parse_date("12/08/2026") == date(2026, 8, 12)  # dayfirst=True


def test_parse_date_iso_not_misread_as_dayfirst():
    # Regression: dateutil's dayfirst=True used to get applied to the
    # unambiguous YYYY-MM-DD order too, silently swapping month <-> day
    # (2026-08-12 came back as Dec 8 instead of Aug 12) — a wrong parse here
    # can flip a real coc_issue_date-vs-contract_date PASS to a FAIL.
    assert parse_date("2026-11-03") == date(2026, 11, 3)
    assert parse_date("2026/01/09") == date(2026, 1, 9)


def test_parse_date_fuzzy_prose():
    assert parse_date("Date of Issue: 12th August 2026") == date(2026, 8, 12)


def test_parse_date_unparseable_returns_none():
    assert parse_date("see attached schedule") is None


def test_parse_date_none_returns_none():
    assert parse_date(None) is None


def test_parse_bool_flag_truthy_falsy_and_unknown():
    assert parse_bool_flag("Yes") is True
    assert parse_bool_flag("No") is False
    assert parse_bool_flag("N/A") is False
    assert parse_bool_flag("") is None
    assert parse_bool_flag(None) is None
    assert parse_bool_flag("unclear") is None
