"""Regression coverage for semantic_validator's field filtering — a field
the matched BOM item doesn't actually specify a value for must never
surface as a "missing or conflicting" WARNING row, even if the agent lists
it in missing_or_conflicting_fields. Mirrors engine.run_validation's own
skip of comparison rows with nothing to compare against (see engine.py's
docstring) — the semantic layer shouldn't be able to flag a field the
deterministic layer already decided has no BOM value at all.
"""

import pytest

from app.services import semantic_validator
from tests.factories import make_bom_item


@pytest.mark.asyncio
async def test_semantic_validate_drops_fields_the_bom_item_never_specifies(monkeypatch):
    bom_item = make_bom_item(part_id="XL62339", quantity=12.0)  # no description/manufacturer/model set

    async def fake_call_agent(payload):
        return {
            "passes_compliance": False,
            "reasoning": "Description and warranty don't match.",
            "missing_or_conflicting_fields": ["quantity", "description", "warranty_expiry"],
        }

    monkeypatch.setattr(semantic_validator, "call_agent", fake_call_agent)
    monkeypatch.setattr(semantic_validator.settings, "forjinn_api_url", "https://forjinn.test/predict")

    results = await semantic_validator.semantic_validate(bom_item, coc_fields=[])
    parameters = [r["rule_result"].parameter for r in results]

    # quantity IS on the BOM item (12.0) — the flag is legitimate, keep it.
    assert "quantity" in parameters
    # description/warranty_expiry are NOT set on this BOM item — nothing to
    # compare against, so the flag must be dropped even though the agent
    # returned it.
    assert "description" not in parameters
    assert "warranty_expiry" not in parameters
    # The overall semantic_compliance verdict itself is untouched by this
    # filter — only the per-field flags are filtered.
    assert any(r["rule_result"].parameter == "semantic_compliance" and r["rule_result"].status == "FAIL" for r in results)


@pytest.mark.asyncio
async def test_semantic_validate_drops_all_flagged_fields_when_unmatched(monkeypatch):
    async def fake_call_agent(payload):
        return {
            "passes_compliance": False,
            "reasoning": "No BOM line to compare against.",
            "missing_or_conflicting_fields": ["quantity", "description"],
        }

    monkeypatch.setattr(semantic_validator, "call_agent", fake_call_agent)
    monkeypatch.setattr(semantic_validator.settings, "forjinn_api_url", "https://forjinn.test/predict")

    results = await semantic_validator.semantic_validate(bom_item=None, coc_fields=[])
    parameters = [r["rule_result"].parameter for r in results]

    assert parameters == ["semantic_compliance"]
