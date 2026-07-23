"""HLHP API auth — SkinBB access token via Label Looker auth stack."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import Header, HTTPException

from app.hlhp.api.errors import (
    auth_failed_detail,
    auth_missing_token_detail,
    auth_user_mismatch_detail,
)
from app.label_looker.core.deps_auth import (
    _merged_authorization_header,
    authenticate_any_user,
)
from app.label_looker.core.errors import ScannerApiError
from app.label_looker.services.common_flow import extract_user_id


async def hlhp_authenticated_user(
    authorization: Optional[str] = Header(None),
    access_token: Optional[str] = Header(None, alias="access-token"),
    x_access_token: Optional[str] = Header(None, alias="x-access-token"),
) -> dict[str, Any]:
    if not _merged_authorization_header(authorization, access_token, x_access_token):
        raise HTTPException(status_code=401, detail=auth_missing_token_detail())
    try:
        return await authenticate_any_user(
            authorization=authorization,
            access_token=access_token,
            x_access_token=x_access_token,
        )
    except ScannerApiError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=auth_failed_detail(exc.message),
        ) from exc


async def hlhp_optional_authenticated_user(
    authorization: Optional[str] = Header(None),
    access_token: Optional[str] = Header(None, alias="access-token"),
    x_access_token: Optional[str] = Header(None, alias="x-access-token"),
) -> dict[str, Any] | None:
    """Return auth user when a token is present; otherwise None (guest scan)."""
    if not _merged_authorization_header(authorization, access_token, x_access_token):
        return None
    try:
        return await authenticate_any_user(
            authorization=authorization,
            access_token=access_token,
            x_access_token=x_access_token,
        )
    except ScannerApiError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=auth_failed_detail(exc.message),
        ) from exc


def user_id_from_auth(user: dict[str, Any]) -> str:
    uid = extract_user_id(user)
    if uid is not None:
        return str(uid)
    for key in ("externalId", "profileUrl", "frontName"):
        val = user.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    raise HTTPException(
        status_code=401,
        detail={
            "code": "auth_invalid",
            "message": "Your account was authenticated but has no user id we can load a profile for.",
            "action": "Sign out and sign in again, or contact support if this keeps happening.",
        },
    )


def verify_client_user_id(
    auth_user: dict[str, Any],
    client_user_id: str | None,
) -> str:
    """Return the canonical user id from the token; reject a different client id."""
    auth_uid = user_id_from_auth(auth_user)
    if client_user_id is not None:
        client = str(client_user_id).strip()
        if client and client != auth_uid:
            raise HTTPException(status_code=403, detail=auth_user_mismatch_detail())
    return auth_uid


def resolve_optional_personalization_user_id(
    auth_user: dict[str, Any] | None,
    client_user_id: str | None,
) -> str | None:
    """Guest-safe personalization: user_id in query requires a valid token that matches."""
    if client_user_id is not None and str(client_user_id).strip():
        if auth_user is None:
            raise HTTPException(status_code=401, detail=auth_missing_token_detail())
        return verify_client_user_id(auth_user, client_user_id)
    if auth_user is not None:
        return user_id_from_auth(auth_user)
    return None


def resolve_scan_user_id(
    client_user_id: str | None,
    auth_user: dict[str, Any] | None,
) -> str | None:
    """Guest scan when anonymous; personalised scan requires a valid token."""
    if client_user_id is not None and str(client_user_id).strip():
        if auth_user is None:
            raise HTTPException(status_code=401, detail=auth_missing_token_detail())
        return verify_client_user_id(auth_user, client_user_id)
    if auth_user is not None:
        return user_id_from_auth(auth_user)
    return None
