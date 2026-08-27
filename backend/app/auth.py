from fastapi import Header, HTTPException

from app.auth_core import is_authorized
from app.config import settings


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """No-op when settings.api_key is unset (local dev). Once set, every
    dependent route must present a matching X-API-Key header — a single
    shared key, not a user/session system, since this is an internal review
    tool for a handful of known users rather than a multi-tenant product."""
    if not is_authorized(x_api_key, settings.api_key):
        raise HTTPException(status_code=401, detail="Missing or invalid API key")
