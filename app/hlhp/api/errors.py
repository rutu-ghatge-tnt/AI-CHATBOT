"""Structured HTTP error payloads for HLHP API routes."""

from __future__ import annotations

from typing import Any


def http_error_detail(*, code: str, message: str, **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message}
    for key, value in extra.items():
        if value is None:
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        body[key] = value
    return body


def auth_missing_token_detail() -> dict[str, Any]:
    return http_error_detail(
        code="auth_required",
        message="Sign in required. Send your SkinBB access token with this request.",
        hint="Use Authorization: Bearer <access_token>, or the access-token / x-access-token header.",
    )


def auth_failed_detail(message: str) -> dict[str, Any]:
    return http_error_detail(
        code="auth_invalid",
        message="Your session could not be verified. Sign in again and retry.",
        reason=message,
    )


def profile_incomplete_detail(diagnosis: dict[str, Any]) -> dict[str, Any]:
    missing = list(diagnosis.get("missing_fields") or [])
    invalid = list(diagnosis.get("invalid_fields") or [])
    message = str(diagnosis.get("message") or "Complete your skin profile to get personalised alerts.")
    return http_error_detail(
        code="profile_incomplete",
        message=message,
        missing_fields=missing,
        invalid_fields=invalid,
        action="Open your account profile and add or fix the fields listed above, then try again.",
    )


def service_unavailable_detail(*, code: str, message: str, reason: str | None = None) -> dict[str, Any]:
    return http_error_detail(code=code, message=message, reason=reason)
