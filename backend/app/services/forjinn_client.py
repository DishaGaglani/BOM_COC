"""Thin HTTP client for the forjinn.com-hosted flow (Qwen-based agent).

One flow, two jobs, both going through call_agent() below:
  - semantic field extraction (see semantic_extractor.py)
  - semantic COC-vs-BOM comparison / verdict (see semantic_validator.py)

Each caller builds its own task-specific payload dict (with a "task" key so
the agent's system prompt knows which job this is) and parses its own
response shape — this module only owns the transport concern common to
both: forjinn's prediction endpoint takes a single {"question": "<string>"}
body (not our payload as raw JSON), so our structured payload has to be
JSON-stringified going in.

Confirmed via real test calls (both task="extract" and task="validate"):
forjinn's prediction endpoint wraps the agent's structured reply as a JSON
*string* under a top-level "text" key, alongside a pile of flow metadata
(chatId, executionId, agentFlowExecutedData, ...) this client doesn't need.
_unwrap_response handles that — "answer"/"output" are also tried, and the
raw envelope is the final fallback, in case a differently-configured flow
ends up shaped differently.
"""

import json
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class ForjinnNotConfigured(Exception):
    """Raised when forjinn_api_url isn't set — callers should treat this as
    'the agent isn't available', not a hard failure (see each caller's own
    fallback behavior)."""


class AgentResponseError(ValueError):
    """Raised when the agent's response doesn't fit the contract a caller
    needs — e.g. a field extraction/semantic_extractor.py couldn't turn
    into a BOMItem/ExtractedField (wrong type, unparsable value). A
    ValueError subclass so it's caught by the same 422 handling as other
    business-rule failures in main.py, but with a message aimed at "the
    agent misbehaved" rather than a raw pydantic validation dump."""


def _unwrap_response(envelope: dict) -> dict:
    """The normal case (confirmed against real forjinn responses, both
    task="extract" and task="validate"): the agent's structured reply is a
    JSON string under envelope["text"]. "answer"/"output" are also tried
    (in case a differently-configured flow uses one of those names for the
    same shape), and the envelope itself is the final fallback."""
    for key in ("text", "answer", "output"):
        if key in envelope and isinstance(envelope[key], str):
            try:
                return json.loads(envelope[key])
            except json.JSONDecodeError:
                continue  # not actually a JSON-string wrapper for this key — fall through
    return envelope


async def call_agent(payload: dict) -> dict:
    """Sends payload (task-specific dict built by the caller) to the
    configured forjinn.com flow and returns the agent's parsed structured
    reply. Raises ForjinnNotConfigured if forjinn_api_url is unset, or
    httpx.HTTPError/ValueError on a transport, envelope, or parse failure —
    callers decide how to degrade, this function doesn't guess for them."""
    if not settings.forjinn_api_url:
        raise ForjinnNotConfigured("forjinn_api_url is not set")

    headers = {"Content-Type": "application/json"}
    if settings.forjinn_api_key:
        headers["Authorization"] = f"Bearer {settings.forjinn_api_key}"

    body = {"question": json.dumps(payload)}

    async with httpx.AsyncClient(timeout=settings.forjinn_timeout_seconds) as client:
        response = await client.post(settings.forjinn_api_url, json=body, headers=headers)
        response.raise_for_status()
        return _unwrap_response(response.json())
