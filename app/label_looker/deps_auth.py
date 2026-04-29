from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import httpx
import jwt
from fastapi import Depends, Header

from app.label_looker.errors import ScannerApiError
from app.label_looker.settings import get_label_looker_settings


@dataclass
class PanelUserContext:
    user: dict[str, Any]
    role: Any
    permissions: list[Any]


def _bearer(authorization: Optional[str]) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ScannerApiError(401, "Unauthorized")
    return authorization.split(" ", 1)[1].strip()


async def scanner_auth_sso(authorization: Optional[str] = Header(None)) -> dict[str, Any]:
    """Legacy scanner: verify-token then PyJWT verify (Node scannerAuthSSO)."""
    token = _bearer(authorization)
    s = get_label_looker_settings()
    if not s.skin_bb_client_secret:
        raise ScannerApiError(500, "Scanner auth is not configured")

    url = f"{s.skin_bb_base_url_norm}/api/v1/users/verify-token"
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url, headers={"Authorization": f"Bearer {token}"})
    if r.status_code >= 400:
        raise ScannerApiError(401, "Invalid or expired token")

    try:
        payload = jwt.decode(
            token,
            s.skin_bb_client_secret,
            algorithms=["HS256"],
            options={"verify_signature": True},
        )
    except jwt.PyJWTError as e:
        raise ScannerApiError(401, f"JWT verification failed: {e!s}") from e

    user = payload.get("user")
    if not isinstance(user, dict):
        user = {k: v for k, v in dict(payload).items() if k not in ("exp", "iat", "nbf", "iss", "aud")}
    if not user:
        raise ScannerApiError(401, "Invalid token payload")
    user["_label_looker_access_token"] = token
    return user


async def scanner_auth_sso_optional(
    authorization: Optional[str] = Header(None),
) -> Optional[dict[str, Any]]:
    if not authorization:
        return None
    return await scanner_auth_sso(authorization=authorization)


async def authenticate_app_user(authorization: Optional[str] = Header(None)) -> dict[str, Any]:
    """V1 app user: verify-app-token → { data: { user, role } }."""
    token = _bearer(authorization)
    s = get_label_looker_settings()
    url = f"{s.skin_bb_base_url_norm}/api/v1/users/verify-app-token"
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url, headers={"Authorization": f"Bearer {token}"})
    if r.status_code >= 400:
        raise ScannerApiError(401, "Invalid or expired app token")
    try:
        body = r.json()
    except Exception as e:
        raise ScannerApiError(502, "Invalid auth service response") from e
    data = body.get("data") or {}
    user = data.get("user")
    if not isinstance(user, dict):
        raise ScannerApiError(401, "Invalid app token payload")
    user["_label_looker_role"] = data.get("role")
    user["_label_looker_access_token"] = token
    return user


async def authenticate_app_user_optional(
    authorization: Optional[str] = Header(None),
) -> Optional[dict[str, Any]]:
    """Optional app auth for public endpoints with enhanced mode."""
    if not authorization:
        return None
    try:
        return await authenticate_app_user(authorization=authorization)
    except ScannerApiError as e:
        # Public routes should still work for anonymous users if a stale token is sent.
        if e.status_code in (401, 403):
            return None
        raise


async def verify_jwt_panel(authorization: Optional[str] = Header(None)) -> PanelUserContext:
    token = _bearer(authorization)
    s = get_label_looker_settings()
    url = f"{s.skin_bb_base_url_norm}/api/v1/users/verify-panel-token"
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url, headers={"Authorization": f"Bearer {token}"})
    if r.status_code >= 400:
        raise ScannerApiError(401, "Invalid or expired panel token")
    try:
        body = r.json()
    except Exception as e:
        raise ScannerApiError(502, "Invalid panel auth response") from e
    data = body.get("data") or body
    user = data.get("user")
    if not isinstance(user, dict):
        raise ScannerApiError(401, "Invalid panel token payload")
    return PanelUserContext(
        user=user,
        role=data.get("role"),
        permissions=list(data.get("permissions") or []),
    )


async def authorize_scan_overview_view(
    ctx: PanelUserContext = Depends(verify_jwt_panel),
) -> PanelUserContext:
    if not _user_can(ctx.permissions, ctx.role, "scan-overview", "view"):
        raise ScannerApiError(403, "Forbidden")
    return ctx


def _user_can(permissions: list[Any], role: Any, page: str, action: str) -> bool:
    """Node authorizeUser.middleware.js behavior (flexible shapes)."""
    for entry in permissions or []:
        perm = entry.get("permission") if isinstance(entry, dict) else None
        if perm is None and isinstance(entry, dict):
            perm = entry
        if not isinstance(perm, dict):
            continue
        if perm.get("page") != page:
            continue
        acts = perm.get("action") or perm.get("actions")
        if acts is None:
            continue
        if isinstance(acts, str) and acts == action:
            return True
        if isinstance(acts, (list, tuple, set)) and action in acts:
            return True
    _ = role
    return False


async def panel_auth_only(ctx: PanelUserContext = Depends(verify_jwt_panel)) -> PanelUserContext:
    """verifyJWTForPanelAuth only (e.g. analytics)."""
    return ctx
