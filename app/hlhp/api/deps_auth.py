"""HLHP API auth — SkinBB access token via Label Looker auth stack."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import Header, HTTPException

from app.hlhp.api.errors import auth_failed_detail, auth_missing_token_detail
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
    except ScannerApiError:
        return None


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
