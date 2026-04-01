"""API key authentication helpers."""

from __future__ import annotations

import os

from fastapi import Header, HTTPException


def _get_allowed_keys() -> set[str]:
    raw = os.getenv("API_KEYS", "")
    return {item.strip() for item in raw.split(",") if item.strip()}


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    keys = _get_allowed_keys()
    if not keys:
        raise HTTPException(status_code=503, detail="API keys are not configured")
    if not x_api_key or x_api_key not in keys:
        raise HTTPException(status_code=401, detail="Invalid API key")
