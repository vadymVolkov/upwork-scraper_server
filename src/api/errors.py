"""API exception mappers and response helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from src.core.errors import (
    AuthRequiredError,
    CookiesExpiredError,
    CookiesMissingError,
    DatabaseError,
    DomainError,
    ExternalServiceError,
    ValidationError,
)


def build_error_payload(*, code: str, message: str, request_id: str, details: dict | None = None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        },
        "request_id": request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", str(uuid4()))


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:  # type: ignore[override]
        status = 500
        if isinstance(exc, ValidationError):
            status = 400
        elif isinstance(exc, (AuthRequiredError, CookiesMissingError, CookiesExpiredError)):
            status = 401
        elif isinstance(exc, ExternalServiceError):
            status = 503
        elif isinstance(exc, DatabaseError):
            status = 500
        return JSONResponse(
            status_code=status,
            content=build_error_payload(
                code=exc.code,
                message=exc.message,
                request_id=_request_id(request),
                details=exc.details,
            ),
        )

    @app.exception_handler(HTTPException)
    async def handle_http_error(request: Request, exc: HTTPException) -> JSONResponse:  # type: ignore[override]
        return JSONResponse(
            status_code=exc.status_code,
            content=build_error_payload(
                code=f"HTTP_{exc.status_code}",
                message=str(exc.detail),
                request_id=_request_id(request),
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:  # type: ignore[override]
        return JSONResponse(
            status_code=500,
            content=build_error_payload(
                code="INTERNAL_SERVER_ERROR",
                message=str(exc),
                request_id=_request_id(request),
            ),
        )
