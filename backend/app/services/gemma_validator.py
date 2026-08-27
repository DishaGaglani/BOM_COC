"""Semantic validation of COC against BOM using Gemma (via Ollama).

After fast rule-based validation (identity fields, format matches, dates),
this layer asks Gemma: "Given these extracted facts, does the COC actually
demonstrate compliance with this BOM's requirements?" — catching nuance
that rigid rules miss.

Gemma runs locally on the VM via Ollama (app/config.py:ollama_base_url),
so no documents leave the machine.
"""

import asyncio
import json
import logging
from typing import TYPE_CHECKING

from app.config import settings
from app.validation.rules import RuleResult

if TYPE_CHECKING:
    from app.parameters.schema import BOMItem, ExtractedField

logger = logging.getLogger(__name__)

# Maximum tokens in a Gemma response — enough for a structured validation result.
_GEMMA_MAX_TOKENS = 2048


def _build_gemma_prompt(
    bom_item: "BOMItem | None",
    coc_fields: "list[ExtractedField]",
    contract_date: str | None,
) -> str:
    """Construct a prompt for Gemma asking: does this COC satisfy the BOM?

    TODO: build a clear, structured prompt that:
    1. Provides the BOM line's requirements (part_id, manufacturer, quantity, etc.)
    2. Provides the extracted COC fields (what was found in the document)
    3. Asks Gemma to assess compliance holistically
    4. Requests a JSON response with fields: {
         "passes_compliance": bool,
         "reasoning": str,
         "missing_or_conflicting_fields": list[str],
       }
    """
    # Placeholder — user implements based on Gemma's prompt engineering best practices.
    raise NotImplementedError(
        "Gemma prompt construction is not yet implemented. "
        "See app/services/gemma_validator.py:_build_gemma_prompt for details."
    )


async def _call_gemma(prompt: str) -> dict:
    """Call Gemma via Ollama's API and parse the response.

    Ollama exposes a /api/generate endpoint that takes:
    {
      "model": "gemma:7b",
      "prompt": "...",
      "stream": false,
      "temperature": 0.3 (low for consistency),
    }

    Returns:
    {
      "response": "...",  # Gemma's text response
      "done": true,
    }

    TODO: implement the Ollama HTTP call, parse Gemma's JSON response,
    and return a dict with keys: passes_compliance, reasoning, missing_fields.
    """
    # Placeholder.
    raise NotImplementedError(
        "Ollama/Gemma integration is not yet implemented. "
        "See app/services/gemma_validator.py:_call_gemma for details."
    )


async def semantic_validate(
    bom_item: "BOMItem | None",
    coc_fields: "list[ExtractedField]",
    contract_date: str | None = None,
) -> list[dict]:
    """Call Gemma to validate COC compliance holistically, returning structured
    results in the same format as app/validation/engine.run_validation — so
    they integrate seamlessly into the COC validations list.

    If ollama_base_url is unset (or Gemma is unavailable), returns an empty
    list (semantic validation is skipped, fast rules are enough).

    Each result dict contains {rule_result, source_field}, where rule_result
    is a RuleResult with parameter, expected_value, actual_value, status,
    reason — matching the contract of the fast validation rules.
    """
    if not settings.ollama_base_url:
        logger.debug("Ollama not configured — skipping semantic validation")
        return []

    try:
        prompt = _build_gemma_prompt(bom_item, coc_fields, contract_date)
        gemma_result = await asyncio.wait_for(
            _call_gemma(prompt),
            timeout=settings.ollama_timeout_seconds,
        )

        results = []

        # TODO: parse gemma_result and yield one or more RuleResult entries
        # for the validation report. For example:
        # - If Gemma says compliance fails, add a FAIL result with the reasoning.
        # - If Gemma flags missing/conflicting fields, add WARNING results per field.
        # - Otherwise, add a PASS for "holistic semantic validation".

        return results

    except asyncio.TimeoutError:
        logger.exception("Gemma validation timed out (timeout=%ds)", settings.ollama_timeout_seconds)
        return [
            {
                "rule_result": RuleResult(
                    "gemma_semantic_validation", None, None, "WARNING",
                    f"Semantic validation timed out after {settings.ollama_timeout_seconds}s",
                ),
                "source_field": None,
            }
        ]
    except Exception:
        logger.exception("Gemma validation failed")
        return [
            {
                "rule_result": RuleResult(
                    "gemma_semantic_validation", None, None, "WARNING",
                    "Semantic validation failed — could not reach Gemma/Ollama or parse response",
                ),
                "source_field": None,
            }
        ]
