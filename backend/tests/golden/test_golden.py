"""Golden-file suite: runs the real files in review/ through the actual
unstructured parsing pipeline and the live forjinn extraction agent, and
checks the result against hand-verified fixtures (see fixtures/*.json and
this suite's own README) — the thing the fast fixture-based suite
(tests/test_semantic_extractor.py, tests/test_services.py) can't prove,
since it never touches unstructured or a real document's actual phrasing.

Deliberately loose on anything with wording variance (free-text
description, page/bbox echoes): the agent isn't temperature-0, so this
suite would be flaky if it asserted exact string equality on prose. What it
checks exactly is identifiers and short categorical/numeric fields, which
have no legitimate reason to vary run to run — a change there is either a
real regression or a real (and worth knowing about) shift in agent
behavior.

Skips cleanly (not a failure) when unstructured isn't installed or
BOMCOC_FORJINN_API_URL isn't set, so the fast suite stays fast/offline and
CI without network access doesn't break.
"""

import json
from pathlib import Path

import pytest

pytest.importorskip("unstructured")

from app.config import settings

pytestmark = pytest.mark.skipif(
    not settings.forjinn_api_url,
    reason="BOMCOC_FORJINN_API_URL not set — extraction has no rule-based fallback to test instead",
)

_REVIEW_DIR = Path(__file__).resolve().parents[3] / "review"
_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((_FIXTURES_DIR / name).read_text())


def _norm_ws(value: str | None) -> str:
    """Collapses whitespace before comparing model/part numbers — the
    source table cells carry stray OCR-artifact spaces (e.g.
    "MS3470-W18- 11PN") that the agent sometimes reproduces verbatim and
    sometimes normalizes away; neither is wrong, so this suite shouldn't
    care which one a given call happened to do."""
    return "".join((value or "").split())


@pytest.mark.asyncio
async def test_mdp_bom_extraction_matches_hand_verified_fields():
    from app.parsing.unstructured_parser import parse_document
    from app.services.semantic_extractor import extract_bom

    fixture = _load_fixture("mdp_bom.json")
    document = parse_document(str(_REVIEW_DIR / "MDP BOM.pdf"), "MDP BOM.pdf")
    items, contract_date = await extract_bom(document)

    if "contract_date" in fixture:
        assert contract_date == fixture["contract_date"]

    by_part_id = {item.part_id: item for item in items}

    for part_id, expected in fixture["items"].items():
        assert part_id in by_part_id, f"{part_id} missing from extraction — expected it in bom_items"
        item = by_part_id[part_id]

        if "manufacturer" in expected:
            assert item.manufacturer == expected["manufacturer"]
        if "manufacturer_contains" in expected:
            assert expected["manufacturer_contains"] in (item.manufacturer or "")
        if "model" in expected:
            assert _norm_ws(item.model) == _norm_ws(expected["model"])
        if "quantity" in expected:
            assert item.quantity == expected["quantity"]
        if "description_keyword" in expected:
            assert expected["description_keyword"] in (item.description or "")
        for key, value in expected.get("requirements", {}).items():
            assert item.requirements.get(key) == value, f"{part_id}.requirements[{key}]"


@pytest.mark.asyncio
async def test_xl62339_coc_extraction_matches_hand_verified_fields():
    from app.parsing.unstructured_parser import parse_document
    from app.services.semantic_extractor import extract_coc

    fixture = _load_fixture("xl62339_coc.json")
    document = parse_document(str(_REVIEW_DIR / "XL62339.pdf"), "XL62339.pdf")
    fields = await extract_coc(document)

    by_name = {f.field_name: f.field_value for f in fields}

    for field_name, expected_value in fixture["fields"].items():
        assert field_name in by_name, f"{field_name} missing from extraction"
        assert by_name[field_name] == expected_value, f"field {field_name}"

    # Checked only when present — see fixture's _note on why these aren't
    # required on every call.
    for field_name, expected_value in fixture.get("optional_fields", {}).items():
        if field_name in by_name:
            assert _norm_ws(by_name[field_name]) == _norm_ws(expected_value), f"field {field_name}"

    description = by_name.get("description", "")
    assert fixture["description_keyword"] in description

    # Deliberately not asserted: presence-only fields (signature, seal,
    # test_certificate, import_documents, authorization_letter). Whether the
    # agent judges a given phrase as solid-enough evidence to report is a
    # genuine judgment call on borderline text, confirmed to flicker between
    # identical calls against this same document even after the 2026-09-03
    # prompt fixes below — asserting on it would make this suite flaky for
    # no real signal (see this module's docstring on what is/isn't asserted
    # exactly, and why).
