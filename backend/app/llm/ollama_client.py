import json
import httpx

from app.config import settings


class OllamaClient:
    """Thin client for a locally-hosted Ollama instance. No external API
    calls — this only ever talks to OLLAMA_HOST on the same VM/network."""

    def __init__(self, host: str | None = None, model: str | None = None):
        self.host = host or settings.ollama_host
        self.model = model or settings.ollama_model

    def generate_json(self, prompt: str, timeout: float = 120.0) -> dict:
        """Call Ollama with JSON-mode generation and parse the result.
        Raises ValueError if the model didn't return valid JSON."""
        resp = httpx.post(
            f"{self.host}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "format": "json",
                "stream": False,
                "options": {"temperature": 0.0},
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "")
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"Ollama did not return valid JSON: {raw[:500]}") from e

    def health_check(self) -> bool:
        try:
            resp = httpx.get(f"{self.host}/api/tags", timeout=5.0)
            return resp.status_code == 200
        except httpx.HTTPError:
            return False
