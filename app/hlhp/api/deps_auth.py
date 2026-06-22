"""HLHP API auth — SkinBB access token via Label Looker auth stack."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import Header, HTTPException

from app.label_looker.core.deps_auth import authenticate_any_user
from app.label_looker.core.errors import ScannerApiError
from app.label_looker.services.common_flow import extract_user_id


async def hlhp_authenticated_user(
    authorization: Optional[str] = Header(None),
    access_token: Optional[str] = Header(None, alias="access-token"),
    x_access_token: Optional[str] = Header(None, alias="x-access-token"),
) -> dict[str, Any]:
    try:
        return await authenticate_any_user(
            authorization=authorization,
            access_token=access_token,
            x_access_token=x_access_token,
        )
    except ScannerApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


def user_id_from_auth(user: dict[str, Any]) -> str:
    uid = extract_user_id(user)
    if uid is not None:
        return str(uid)
    for key in ("externalId", "profileUrl", "frontName"):
        val = user.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    raise HTTPException(status_code=401, detail="Authenticated user has no resolvable id")
