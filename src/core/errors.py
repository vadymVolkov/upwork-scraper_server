"""Domain exceptions and normalization helpers."""

from __future__ import annotations


class DomainError(Exception):
    """Base class for expected domain-level failures."""

    code = "DOMAIN_ERROR"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ValidationError(DomainError):
    code = "VALIDATION_ERROR"


class AuthRequiredError(DomainError):
    code = "AUTH_REQUIRED"


class CookiesMissingError(DomainError):
    code = "COOKIES_MISSING"


class CookiesExpiredError(DomainError):
    code = "COOKIES_EXPIRED"


class UpworkAccessError(DomainError):
    code = "UPWORK_ACCESS_ERROR"


class ExternalServiceError(DomainError):
    code = "EXTERNAL_SERVICE_ERROR"


class DatabaseError(DomainError):
    code = "DATABASE_ERROR"


class ConfigError(DomainError):
    code = "CONFIG_ERROR"


def map_runtime_error(error: Exception) -> DomainError:
    """Map low-level runtime errors to stable domain exceptions."""
    message = str(error)
    text = message.lower()
    if "required" in text and ("limit" in text or "search" in text):
        return ValidationError(message)
    if "cookies not found" in text:
        return CookiesMissingError(message)
    if "cookies are expired or invalid" in text:
        return CookiesExpiredError(message)
    if "upwork credentials are required" in text or "both credentials are required" in text:
        return AuthRequiredError(message)
    if "sqlite" in text or "database" in text or "table" in text:
        return DatabaseError(message)
    if "proxy" in text or "captcha" in text:
        return ExternalServiceError(message)
    if "config" in text:
        return ConfigError(message)
    if "upwork" in text or "login failed" in text:
        return UpworkAccessError(message)
    return DomainError(message)
