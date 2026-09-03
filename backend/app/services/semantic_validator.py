"""Semantic validation of COC against BOM using the forjinn.com agent.

After fast rule-based validation (identity fields, format matches, dates —
see validation/rules.py and validation/engine.py, unchanged), this layer
asks the same forjinn-hosted Qwen agent that does field extraction (see
semantic_extractor.py) a different question: "Given these extracted facts,
does the COC actually demonstrate compliance with this BOM's requirements?"
— catching semantic-equivalence nuance (e.g. BOM 'MCB1' vs COC 'Miniature
Circuit Breaker - 3P - C - 50A' being the same part) that rigid rules miss.

Both jobs go through the same forjinn_client.call_agent transport,
distinguished by the "task" field in the request payload.
"""

import asyncio
import logging
from typing import TYPE_CHECKING

from app.config import settings
from app.services.forjinn_client import ForjinnNotConfigured, call_agent
from app.validation.rules import RuleResult

if TYPE_CHECKING:
    from app.parameters.schema import BOMItem, ExtractedField

logger = logging.getLogger(__name__)


def _build_validation_payload(
    bom_item: "BOMItem | None",
    coc_fields: "list[ExtractedField]",
    contract_date: str | None,
) -> dict:
    """Structured input for the comparison/verdict job: the matched BOM
    line's requirements, the COC's extracted fields, and the contract date
    the COC's issue date is checked against. No prompt-string building here
    — that's the agent side's concern; this is just the clean payload."""
    return {
        "task": "validate",
        "bom_item": bom_item.model_dump() if bom_item is not None else None,
        "coc_fields": [f.model_dump() for f in coc_fields],
        "contract_date": contract_date,
    }


async def semantic_validate(
    bom_item: "BOMItem | None",
    coc_fields: "list[ExtractedField]",
    contract_date: str | None = None,
) -> list[dict]:
    """Calls the forjinn agent to validate COC compliance holistically,
    returning structured results in the same format as
    app/validation/engine.run_validation — so they integrate seamlessly into
    the COC validations list.

    If forjinn_api_url is unset (or the agent is unavailable), returns an
    empty list (semantic validation is skipped, fast rules are enough).

    Each result dict contains {rule_result, source_field}, where rule_result
    is a RuleResult with parameter, expected_value, actual_value, status,
    reason — matching the contract of the fast validation rules.

    Confirmed agent response shape (real test call):
    {
      "passes_compliance": bool,
      "reasoning": str,
      "missing_or_conflicting_fields": list[str],
    }
    This function turns that into one PASS/FAIL RuleResult (named
    "semantic_compliance") plus one WARNING RuleResult per flagged field —
    see _parse_agent_result below.
    """
    if not settings.forjinn_api_url:
        logger.debug("forjinn not configured — skipping semantic validation")
        return []

    try:
        payload = _build_validation_payload(bom_item, coc_fields, contract_date)
        agent_result = await asyncio.wait_for(
            call_agent(payload),
            timeout=settings.forjinn_timeout_seconds,
        )
        return _parse_agent_result(agent_result)

    except ForjinnNotConfigured:
        return []
    except asyncio.TimeoutError:
        logger.exception("Semantic validation timed out (timeout=%ds)", settings.forjinn_timeout_seconds)
        return [
            {
                "rule_result": RuleResult(
                    "semantic_compliance", None, None, "WARNING",
                    f"Semantic validation timed out after {settings.forjinn_timeout_seconds}s",
                ),
                "source_field": None,
            }
        ]
    except Exception:
        logger.exception("Semantic validation failed")
        return [
            {
                "rule_result": RuleResult(
                    "semantic_compliance", None, None, "WARNING",
                    "Semantic validation failed — could not reach the forjinn agent or parse its response",
                ),
                "source_field": None,
            }
        ]


def _parse_agent_result(agent_result: dict) -> list[dict]:
    passes = agent_result.get("passes_compliance")
    reasoning = agent_result.get("reasoning") or ""
    missing_or_conflicting = agent_result.get("missing_or_conflicting_fields") or []

    results = [
        {
            "rule_result": RuleResult(
                "semantic_compliance", None, None,
                "PASS" if passes else "FAIL",
                reasoning or ("Compliant" if passes else "Not compliant"),
            ),
            "source_field": None,
        }
    ]
    for field_name in missing_or_conflicting:
        results.append({
            "rule_result": RuleResult(
                field_name, None, None, "WARNING",
                f"Flagged by semantic validation as missing or conflicting — {reasoning}".strip(" —"),
            ),
            "source_field": None,
        })
    return results
