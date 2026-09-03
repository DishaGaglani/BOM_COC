"""Regression coverage for semantic_extractor's coercion of the forjinn
agent's raw JSON into BOMItem/ExtractedField — see _coerce_str. The agent
represents some fields as native JSON types (e.g. a real boolean for
`is_imported`) even though BOMItem.requirements is dict[str, str] and
ExtractedField.field_value/raw_label are str; constructing the models
directly from the agent's raw dict crashed with a pydantic ValidationError
whenever a response happened to include one of these (confirmed against a
real forjinn call against review/MDP BOM.pdf).
"""

import pytest

from app.services import semantic_extractor
from app.services.forjinn_client import AgentResponseError
from tests.factories import make_parsed_document


@pytest.mark.asyncio
async def test_extract_bom_coerces_non_string_requirement_values(monkeypatch):
    async def fake_call_agent(payload):
        return {
            "bom_items": [
                {
                    "part_id": "XL62339",
                    "description": "MCB, 3 Pole, 50A, 480VAC.",
                    "manufacturer": "ABB",
                    "quantity": 12,
                    "requirements": {
                        "country_of_origin": "India",
                        "is_imported": False,  # real JSON bool, not "false"
                        "warranty_years": 5,  # real JSON int, not "5"
                    },
                    "page_number": 2,
                }
            ],
            "contract_date": None,
        }

    monkeypatch.setattr(semantic_extractor, "call_agent", fake_call_agent)

    items, contract_date = await semantic_extractor.extract_bom(make_parsed_document(table_rows=None))

    assert len(items) == 1
    assert items[0].requirements == {
        "country_of_origin": "India",
        "is_imported": "false",
        "warranty_years": "5",
    }


@pytest.mark.asyncio
async def test_extract_coc_coerces_non_string_field_value_and_raw_label(monkeypatch):
    async def fake_call_agent(payload):
        return {
            "coc_fields": [
                {"field_name": "quantity", "field_value": 12, "raw_label": 42},
                {"field_name": "signature", "field_value": "Authorised Signatory"},
                {"field_name": "seal", "field_value": None},  # no evidence — dropped
            ],
        }

    monkeypatch.setattr(semantic_extractor, "call_agent", fake_call_agent)

    fields = await semantic_extractor.extract_coc(make_parsed_document(table_rows=None))

    assert [f.field_name for f in fields] == ["quantity", "signature"]
    assert fields[0].field_value == "12"
    assert fields[0].raw_label == "42"
    assert fields[1].field_value == "Authorised Signatory"


@pytest.mark.asyncio
async def test_extract_bom_raises_agent_response_error_on_unparsable_quantity(monkeypatch):
    """quantity is a typed BOMItem field (float | None), not a requirements
    entry — _coerce_str doesn't touch it, so a genuinely unparsable value
    (not the bool/int mismatch _coerce_str exists for) should still surface
    as a clear, caller-facing AgentResponseError instead of a raw pydantic
    ValidationError."""

    async def fake_call_agent(payload):
        return {"bom_items": [{"part_id": "XL1", "quantity": "N/A"}], "contract_date": None}

    monkeypatch.setattr(semantic_extractor, "call_agent", fake_call_agent)

    with pytest.raises(AgentResponseError) as exc_info:
        await semantic_extractor.extract_bom(make_parsed_document(table_rows=None))

    assert "XL1" in str(exc_info.value)
    assert "quantity" in str(exc_info.value)


@pytest.mark.asyncio
async def test_extract_coc_raises_agent_response_error_on_unparsable_page_number(monkeypatch):
    async def fake_call_agent(payload):
        return {"coc_fields": [{"field_name": "part_id", "field_value": "XL1", "page_number": "one"}]}

    monkeypatch.setattr(semantic_extractor, "call_agent", fake_call_agent)

    with pytest.raises(AgentResponseError) as exc_info:
        await semantic_extractor.extract_coc(make_parsed_document(table_rows=None))

    assert "part_id" in str(exc_info.value)
    assert "page_number" in str(exc_info.value)
