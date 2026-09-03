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

Confirmed via a real test call (task="validate"): forjinn's prediction
endpoint returns the agent's structured reply directly as the top-level
JSON response — no {"text": "..."}-style wrapper. _unwrap_response still
tries a few common wrapper keys first (in case a differently-configured
flow ends up needing it) but falls back to the raw response body, which is
the normal path now.
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


def _unwrap_response(envelope: dict) -> dict:
    """The normal case (confirmed against a real forjinn response): the
    agent's structured reply IS the response body, no wrapper. Still checks
    "text"/"answer"/"output" first in case they're present as a JSON
    *string* — the common Flowise wrapper shape — so a differently-behaving
    flow config doesn't silently break, but falls through to the envelope
    itself otherwise."""
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
