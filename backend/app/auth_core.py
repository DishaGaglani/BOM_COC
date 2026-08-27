"""Pure API-key matching logic, split out from app/auth.py so the fast test
suite (requirements-dev.txt, no fastapi) can cover it without needing
fastapi installed."""


def is_authorized(presented_key: str | None, configured_key: str | None) -> bool:
    """`configured_key=None` means auth is off (local dev) — always
    authorized. Otherwise the presented header must match exactly."""
    if configured_key is None:
        return True
    return presented_key == configured_key
