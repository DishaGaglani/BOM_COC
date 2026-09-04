"""Regression coverage for semantic_extractor's coercion of the forjinn
agent's raw JSON into BOMItem/ExtractedField — see _coerce_str. The agent
represents some fields as native JSON types (e.g. a real boolean for
`is_imported`) even though BOMItem.requirements is dict[str, str] and
ExtractedField.field_value/raw_label are str; constructing the models
directly from the agent's raw dict crashed with a pydantic ValidationError
whenever a response happened to include one of these (confirmed against a
real forjinn call against review/MDP BOM.pdf).

Also covers the oversized-table chunking in _table_call_groups/
_chunk_table_rows — added after a real ~40-row COC table (xh02020.pdf)
caused the agent to give up on per-row extraction entirely in one call;
see MAX_TABLE_ROWS_PER_CALL's own comment for the full story.
"""

import pytest

from app.services import semantic_extractor
from app.services.forjinn_client import AgentResponseError
from tests.factories import make_multi_table_document, make_parsed_document


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


def _rows(n: int) -> list[list[str]]:
    """A header row plus n data rows, e.g. _rows(3) -> header + 3 rows."""
    return [["Item No.", "Description", "Qty"]] + [[f"XH{i:05d}", f"Part {i}", str(i)] for i in range(n)]


# Sized relative to MAX_TABLE_ROWS_PER_CALL (not hardcoded) so these tests
# stay correct regardless of the constant's exact tuned value.
_SMALL_TABLE_DATA_ROWS = max(1, semantic_extractor.MAX_TABLE_ROWS_PER_CALL - 2)
_OVERSIZED_TABLE_DATA_ROWS = semantic_extractor.MAX_TABLE_ROWS_PER_CALL * 3


def test_chunk_table_rows_leaves_small_tables_untouched():
    rows = _rows(_SMALL_TABLE_DATA_ROWS)  # under MAX_TABLE_ROWS_PER_CALL
    assert semantic_extractor._chunk_table_rows(rows) == [rows]


def test_chunk_table_rows_splits_oversized_table_with_header_repeated():
    rows = _rows(_OVERSIZED_TABLE_DATA_ROWS)  # well over MAX_TABLE_ROWS_PER_CALL
    chunks = semantic_extractor._chunk_table_rows(rows)

    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= semantic_extractor.MAX_TABLE_ROWS_PER_CALL
        assert chunk[0] == rows[0]  # header repeated in every chunk
    # every data row appears in exactly one chunk (accounting for the
    # repeated header in each)
    reassembled = [row for chunk in chunks for row in chunk[1:]]
    assert reassembled == rows[1:]


def test_table_call_groups_bundles_small_tables_but_splits_the_oversized_one():
    small_a, small_b = _SMALL_TABLE_DATA_ROWS, max(1, _SMALL_TABLE_DATA_ROWS - 1)
    document = make_multi_table_document([_rows(small_a), _rows(_OVERSIZED_TABLE_DATA_ROWS), _rows(small_b)])

    groups = semantic_extractor._table_call_groups(document)

    # The two small tables share one call; the oversized table gets pulled
    # into its own additional call(s) instead of joining that shared call.
    small_group = next(g for g in groups if len(g) == 2)
    assert {len(t["rows"]) for t in small_group} == {small_a + 1, small_b + 1}  # header + data rows

    large_table_groups = [g for g in groups if g is not small_group]
    assert len(large_table_groups) > 1
    for g in large_table_groups:
        assert len(g) == 1
        assert len(g[0]["rows"]) <= semantic_extractor.MAX_TABLE_ROWS_PER_CALL
    # each oversized-table chunk is labeled distinctly so overlapping
    # bboxes from the same source table aren't confused for different ones
    table_ids = [g[0]["table_id"] for g in large_table_groups]
    assert len(set(table_ids)) == len(table_ids)


@pytest.mark.asyncio
async def test_extract_bom_merges_results_across_multiple_calls_for_oversized_table(monkeypatch):
    document = make_multi_table_document([_rows(_OVERSIZED_TABLE_DATA_ROWS)])
    calls = []

    async def fake_call_agent(payload):
        calls.append(payload)
        # Each call "extracts" one BOMItem, distinguishing calls by index.
        return {
            "bom_items": [{"part_id": f"CALL{len(calls)}", "quantity": 1}],
            "contract_date": "2026-01-01" if len(calls) == 2 else None,
        }

    monkeypatch.setattr(semantic_extractor, "call_agent", fake_call_agent)

    items, contract_date = await semantic_extractor.extract_bom(document)

    assert len(calls) > 1  # the oversized table forced more than one call
    assert len(items) == len(calls)  # every call's bom_items made it into the merged result
    assert contract_date == "2026-01-01"  # first non-null value found across calls, not overwritten by later Nones
