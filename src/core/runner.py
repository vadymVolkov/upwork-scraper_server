"""Core service runner used by both CLI and API layers."""

from __future__ import annotations

from typing import Any

from main import (
    cli_collect_bestmatch_urls,
    cli_collect_urls,
    cli_login,
    cli_parse_urls_to_jobs,
    cli_pull_unchecked_jobs,
    cli_search_with_cookies,
)

from .errors import DomainError, map_runtime_error


class ScraperService:
    """Unified async facade over existing scraper commands."""

    async def login(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            cookies_path = await cli_login(payload)
            return {"cookies_path": cookies_path}
        except Exception as error:  # noqa: BLE001
            raise map_runtime_error(error) from error

    async def search(self, payload: dict[str, Any], require_query: bool = True) -> list[dict[str, Any]]:
        try:
            return await cli_search_with_cookies(payload, require_query=require_query)
        except Exception as error:  # noqa: BLE001
            raise map_runtime_error(error) from error

    async def collect_urls(self, payload: dict[str, Any], *, bestmatch: bool = False) -> dict[str, Any]:
        try:
            if bestmatch:
                saved = await cli_collect_bestmatch_urls(payload)
            else:
                saved = await cli_collect_urls(payload)
            return {"saved": saved}
        except Exception as error:  # noqa: BLE001
            raise map_runtime_error(error) from error

    async def parse_urls(self, payload: dict[str, Any], *, bestmatch: bool = False) -> dict[str, Any]:
        try:
            table = "job_urls_bestmatch" if bestmatch else "job_urls"
            return await cli_parse_urls_to_jobs(payload, table)
        except Exception as error:  # noqa: BLE001
            raise map_runtime_error(error) from error

    def pull_jobs(self, payload: dict[str, Any], *, bestmatch: bool = False) -> list[dict[str, Any]]:
        try:
            table = "job_bestmach" if bestmatch else "jobs"
            return cli_pull_unchecked_jobs(payload, table)
        except Exception as error:  # noqa: BLE001
            raise map_runtime_error(error) from error


def ensure_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise DomainError("Payload must be a JSON object.")
    return payload
