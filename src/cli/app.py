"""Refactored CLI entrypoint with legacy compatibility."""

from __future__ import annotations

import argparse
import ast
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from src.core.errors import DomainError
from src.core.runner import ScraperService, ensure_payload


def _load_json_payload(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        if os.path.exists(raw):
            return json.loads(Path(raw).read_text(encoding="utf-8"))
        return ast.literal_eval(raw)


def _legacy_to_new_command(legacy_command: str) -> tuple[str, bool]:
    mapping = {
        "login": ("auth.login", False),
        "search": ("search.run", False),
        "best-match": ("search.bestmatch", False),
        "collect-urls": ("urls.collect", False),
        "collect-bestmatch-urls": ("urls.collect", True),
        "parse-job-urls": ("jobs.parse", False),
        "parse-bestmatch-urls": ("jobs.parse", True),
        "pull-jobs": ("jobs.pull", False),
        "pull-bestmatch-jobs": ("jobs.pull", True),
    }
    return mapping[legacy_command]


async def _run_async(parsed: argparse.Namespace) -> Any:
    service = ScraperService()
    payload = ensure_payload(parsed.payload)

    if parsed.command == "auth.login":
        return await service.login(payload)
    if parsed.command == "search.run":
        return await service.search(payload, require_query=True)
    if parsed.command == "search.bestmatch":
        return await service.search(payload, require_query=False)
    if parsed.command == "urls.collect":
        return await service.collect_urls(payload, bestmatch=parsed.bestmatch)
    if parsed.command == "jobs.parse":
        return await service.parse_urls(payload, bestmatch=parsed.bestmatch)
    if parsed.command == "jobs.pull":
        return service.pull_jobs(payload, bestmatch=parsed.bestmatch)
    raise DomainError(f"Unsupported command: {parsed.command}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Upwork scraper CLI service")
    parser.add_argument("--json-input", dest="json_input", help="JSON string or path to JSON file")
    parser.add_argument("--input-file", dest="input_file", help="Path to JSON file payload")

    # Legacy compatibility options (1:1 behavior)
    parser.add_argument(
        "--command",
        choices=[
            "login",
            "search",
            "best-match",
            "collect-urls",
            "collect-bestmatch-urls",
            "parse-job-urls",
            "parse-bestmatch-urls",
            "pull-jobs",
            "pull-bestmatch-jobs",
        ],
        help="Legacy command mode",
    )
    parser.add_argument("--jsonInput", dest="legacy_json_input", help="Legacy JSON input")

    parser.add_argument(
        "task",
        nargs="?",
        choices=["auth.login", "search.run", "search.bestmatch", "urls.collect", "jobs.parse", "jobs.pull"],
        help="New command format",
    )
    parser.add_argument("--bestmatch", action="store_true", help="Use bestmatch flow for grouped commands")
    return parser


def _resolve_payload(parsed: argparse.Namespace) -> dict[str, Any]:
    env_payload = os.environ.get("jsonInput")
    if env_payload:
        return _load_json_payload(env_payload)
    if parsed.input_file:
        return _load_json_payload(parsed.input_file)
    if parsed.json_input:
        return _load_json_payload(parsed.json_input)
    if parsed.legacy_json_input:
        return _load_json_payload(parsed.legacy_json_input)
    return {}


def main() -> int:
    parser = build_parser()
    parsed = parser.parse_args()
    parsed.payload = _resolve_payload(parsed)

    if parsed.command:
        mapped, bestmatch = _legacy_to_new_command(parsed.command)
        parsed.command = mapped
        parsed.bestmatch = bestmatch
    elif parsed.task:
        parsed.command = parsed.task
    else:
        parser.print_help()
        return 2

    try:
        result = asyncio.run(_run_async(parsed))
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except DomainError as error:
        print(json.dumps({"error": {"code": error.code, "message": error.message, "details": error.details}}, ensure_ascii=False))
        return 3
    except Exception as error:  # noqa: BLE001
        print(json.dumps({"error": {"code": "UNEXPECTED_ERROR", "message": str(error)}}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
