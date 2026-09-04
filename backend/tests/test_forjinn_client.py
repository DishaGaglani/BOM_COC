"""Regression coverage for forjinn_client.call_agent's retry-on-transport-
failure behavior — added after a real long-running chunked extraction
sequence (semantic_extractor.py splitting an oversized table across many
calls) failed entirely on a single httpx.ConnectError mid-sequence, even
though every other call in that same run had already succeeded.
"""

import httpx
import pytest

from app.services import forjinn_client


class _FakeResponse:
    def __init__(self, json_body: dict):
        self._json_body = json_body

    def raise_for_status(self):
        pass

    def json(self):
        return self._json_body


class _FakeAsyncClient:
    """Stands in for httpx.AsyncClient — .post() is driven by a queue of
    behaviors (an exception to raise, or a response to return), one per
    call, so a test can script "fail twice, then succeed" precisely."""

    def __init__(self, behaviors: list):
        self._behaviors = behaviors
        self.call_count = 0

    def __call__(self, *args, **kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def post(self, *args, **kwargs):
        behavior = self._behaviors[self.call_count]
        self.call_count += 1
        if isinstance(behavior, Exception):
            raise behavior
        return behavior


@pytest.fixture(autouse=True)
def _configure_forjinn(monkeypatch):
    monkeypatch.setattr(forjinn_client.settings, "forjinn_api_url", "https://forjinn.test/predict")
    monkeypatch.setattr(forjinn_client, "_RETRY_BACKOFF_SECONDS", [0, 0])  # no real sleeping in tests


@pytest.mark.asyncio
async def test_call_agent_succeeds_first_try_without_retrying(monkeypatch):
    fake_client = _FakeAsyncClient([_FakeResponse({"text": '{"ok": true}'})])
    monkeypatch.setattr(httpx, "AsyncClient", fake_client)

    result = await forjinn_client.call_agent({"task": "extract"})

    assert result == {"ok": True}
    assert fake_client.call_count == 1


@pytest.mark.asyncio
async def test_call_agent_retries_transport_failure_then_succeeds(monkeypatch):
    fake_client = _FakeAsyncClient([
        httpx.ConnectError("nodename nor servname provided, or not known"),
        httpx.ReadTimeout("timed out"),
        _FakeResponse({"text": '{"ok": true}'}),
    ])
    monkeypatch.setattr(httpx, "AsyncClient", fake_client)

    result = await forjinn_client.call_agent({"task": "extract"})

    assert result == {"ok": True}
    assert fake_client.call_count == 3  # 2 failed attempts + 1 that succeeded


@pytest.mark.asyncio
async def test_call_agent_gives_up_after_max_attempts(monkeypatch):
    fake_client = _FakeAsyncClient([
        httpx.ConnectError("fail 1"),
        httpx.ConnectError("fail 2"),
        httpx.ConnectError("fail 3"),
    ])
    monkeypatch.setattr(httpx, "AsyncClient", fake_client)

    with pytest.raises(httpx.ConnectError):
        await forjinn_client.call_agent({"task": "extract"})

    assert fake_client.call_count == forjinn_client._MAX_ATTEMPTS


@pytest.mark.asyncio
async def test_call_agent_does_not_retry_a_real_http_error_response(monkeypatch):
    """A 4xx/5xx that actually reached forjinn is a real signal (bad
    payload, auth failure, server error) — retrying it blindly would just
    fail identically again, wasting real forjinn compute for nothing."""

    class _ErrorResponse(_FakeResponse):
        def raise_for_status(self):
            raise httpx.HTTPStatusError("500 error", request=None, response=None)

    fake_client = _FakeAsyncClient([_ErrorResponse({})])
    monkeypatch.setattr(httpx, "AsyncClient", fake_client)

    with pytest.raises(httpx.HTTPStatusError):
        await forjinn_client.call_agent({"task": "extract"})

    assert fake_client.call_count == 1  # no retry attempted
