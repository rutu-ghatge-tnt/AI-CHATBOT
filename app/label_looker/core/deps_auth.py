from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

import httpx
import jwt
from fastapi import Depends, Header

from app.label_looker.core.errors import ScannerApiError
from app.label_looker.core.settings import get_label_looker_settings

logger = logging.getLogger(__name__)

_AUTH_DEBUG = os.getenv("LABEL_LOOKER_AUTH_DEBUG", "").lower() in ("1", "true", "yes")


@dataclass
class PanelUserContext:
    user: dict[str, Any]
    role: Any
    permissions: list[Any]


def _strip_bearer_prefix(value: str) -> str:
    """Strip one or more leading 'Bearer ' prefixes and whitespace (avoids 'Bearer Bearer <jwt>')."""
    t = value.strip()
    while t.lower().startswith("bearer "):
        t = t[7:].strip()
    return t


def _raw_token_from_merged_sources(
    authorization: Optional[str],
    access_token: Optional[str],
    x_access_token: Optional[str],
) -> Optional[str]:
    for part in (authorization, access_token, x_access_token):
        if not part or not str(part).strip():
            continue
        raw = _strip_bearer_prefix(str(part).strip())
        if raw:
            return raw
    return None


def _merged_authorization_header(
    authorization: Optional[str],
    access_token: Optional[str],
    x_access_token: Optional[str],
) -> Optional[str]:
    raw = _raw_token_from_merged_sources(authorization, access_token, x_access_token)
    return f"Bearer {raw}" if raw else None


def _bearer(authorization: Optional[str]) -> str:
    """Return raw token string (no 'Bearer ' prefix) from a header value."""
    if not authorization or not str(authorization).strip():
        raise ScannerApiError(401, "Unauthorized: missing Authorization header")
    t = _strip_bearer_prefix(str(authorization).strip())
    if not t:
        raise ScannerApiError(401, "Unauthorized: empty token")
    return t


def _user_details_url(base_norm: str) -> str:
    path = (os.getenv("SKIN_BB_USER_DETAILS_PATH") or "/api/v1/users/user-details").strip()
    if not path.startswith("/"):
        path = "/" + path
    return f"{base_norm}{path}"


def _jwt_verify_secrets() -> list[str]:
    s = get_label_looker_settings()
    out: list[str] = []
    for raw in (
        s.skin_bb_client_secret,
        os.getenv("ACCESS_TOKEN_SECRET"),
    ):
        secret = (raw or "").strip()
        if secret and secret not in out:
            out.append(secret)
    return out


def _user_from_token_payload(payload: dict[str, Any], token: str) -> dict[str, Any]:
    nested = payload.get("user")
    if isinstance(nested, dict):
        user = dict(nested)
    else:
        skip = {"exp", "iat", "nbf", "iss", "aud", "sub", "jti", "typ"}
        user = {k: v for k, v in dict(payload).items() if k not in skip}
    uid = (
        user.get("externalId")
        or user.get("id")
        or user.get("_id")
        or user.get("userId")
        or user.get("user_id")
    )
    if uid is not None and str(uid).strip():
        user.setdefault("id", str(uid).strip())
    elif isinstance(user.get("profileUrl"), str) and user["profileUrl"].strip():
        user.setdefault("id", user["profileUrl"].strip())
    user["_label_looker_access_token"] = token
    return user


def _auth_base_urls() -> list[str]:
    s = get_label_looker_settings()
    bases: list[str] = []
    for raw in (s.skin_bb_base_url_norm, s.server_url):
        base = (raw or "").strip().rstrip("/")
        if base and base not in bases:
            bases.append(base)
    return bases


async def authenticate_local_jwt(authorization: Optional[str] = Header(None)) -> dict[str, Any]:
    """Verify SkinBB access JWT locally (no Node HTTP) — used when user-details is down."""
    token = _bearer(authorization)
    secrets = _jwt_verify_secrets()
    if not secrets:
        raise ScannerApiError(401, "JWT auth is not configured (set SKIN_BB_CLIENT_SECRET or ACCESS_TOKEN_SECRET)")
    last_err: Exception | None = None
    for secret in secrets:
        try:
            payload = jwt.decode(token, secret, algorithms=["HS256"], options={"verify_signature": True})
            if not isinstance(payload, dict):
                continue
            user = _user_from_token_payload(payload, token)
            if user.get("id") or user.get("_id") or user.get("externalId") or user.get("profileUrl"):
                if _AUTH_DEBUG:
                    logger.warning("Label Looker auth: local JWT verified for id=%s", user.get("id"))
                return user
        except jwt.PyJWTError as e:
            last_err = e
    raise ScannerApiError(401, f"JWT verification failed: {last_err!s}" if last_err else "JWT verification failed")


async def _fetch_user_details_at_base(*, base_norm: str, token: str) -> dict[str, Any]:
    url = _user_details_url(base_norm)
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url, headers=headers)
    if _AUTH_DEBUG:
        logger.warning(
            "Label Looker auth: GET %s status=%s body_prefix=%s",
            url,
            r.status_code,
            (r.text[:200] + "…") if len(r.text) > 200 else r.text,
        )
    if r.status_code >= 400:
        extra = ""
        try:
            jb = r.json()
            if isinstance(jb, dict) and jb.get("message") is not None:
                extra = f" Node says: {str(jb.get('message'))[:160]}"
        except Exception:
            pass
        raise ScannerApiError(401, f"Invalid or expired app token (user-details HTTP {r.status_code}).{extra}")
    try:
        body = r.json()
    except Exception as e:
        raise ScannerApiError(502, "Invalid auth service response") from e
    if isinstance(body, dict) and body.get("success") is False:
        msg = ""
        if isinstance(body.get("message"), str):
            msg = f" {body.get('message')[:160]}"
        raise ScannerApiError(401, f"User-details rejected token (success=false).{msg}")
    user = _parse_user_details_auth_response(body)
    if user is None:
        raise ScannerApiError(
            401,
            "User-details returned no user row (empty data[] or unexpected JSON). "
            "Confirm GET user-details with this Bearer token returns data[0] on Node.",
        )
    user["_label_looker_access_token"] = token
    role = None
    raw_data = body.get("data") if isinstance(body, dict) else None
    if isinstance(raw_data, dict):
        role = raw_data.get("role")
    user["_label_looker_role"] = role
    return user


async def scanner_auth_sso(authorization: Optional[str] = Header(None)) -> dict[str, Any]:
    token = _bearer(authorization)
    s = get_label_looker_settings()
    if not s.skin_bb_client_secret:
        raise ScannerApiError(500, "Scanner auth is not configured")

    url = f"{s.skin_bb_base_url_norm}/api/v1/users/verify-token"
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url, headers={"Authorization": f"Bearer {token}"})
    if r.status_code >= 400:
        # Node verify-token down — still accept if JWT signature is valid locally.
        try:
            return await authenticate_local_jwt(authorization=authorization)
        except ScannerApiError:
            raise ScannerApiError(401, "Invalid or expired token") from None

    try:
        payload = jwt.decode(token, s.skin_bb_client_secret, algorithms=["HS256"], options={"verify_signature": True})
    except jwt.PyJWTError as e:
        raise ScannerApiError(401, f"JWT verification failed: {e!s}") from e

    user = _user_from_token_payload(payload if isinstance(payload, dict) else {}, token)
    if not (user.get("id") or user.get("_id") or user.get("externalId")):
        raise ScannerApiError(401, "Invalid token payload")
    return user


async def scanner_auth_sso_optional(authorization: Optional[str] = Header(None)) -> Optional[dict[str, Any]]:
    if not authorization:
        return None
    return await scanner_auth_sso(authorization=authorization)


def _parse_user_details_auth_response(body: Any) -> dict[str, Any] | None:
    """
    Node SkinTruth: GET /api/v1/users/user-details →
    { "data": [ { "firstName", "externalId", ... } ], "success": true, ... }
    Legacy verify-app-token shape: { "data": { "user": {...}, "role": ... } }
    """
    if not isinstance(body, dict):
        return None
    raw = body.get("data")
    row: dict[str, Any] | None = None
    if isinstance(raw, list):
        if raw and isinstance(raw[0], dict):
            row = dict(raw[0])
    elif isinstance(raw, dict):
        nested = raw.get("user")
        if isinstance(nested, dict):
            row = dict(nested)
        else:
            row = dict(raw)
    if not row:
        return None
    out = dict(row)
    uid = (
        out.get("externalId")
        or out.get("id")
        or out.get("_id")
        or out.get("userId")
        or out.get("user_id")
    )
    if uid is not None and str(uid).strip():
        out.setdefault("id", str(uid).strip())
    elif isinstance(out.get("username"), str) and out["username"].strip():
        out.setdefault("id", out["username"].strip())
    elif isinstance(out.get("profileUrl"), str) and out["profileUrl"].strip():
        out.setdefault("id", out["profileUrl"].strip())
    return out


async def authenticate_app_user(authorization: Optional[str] = Header(None)) -> dict[str, Any]:
    token = _bearer(authorization)
    bases = _auth_base_urls()
    if not bases:
        raise ScannerApiError(500, "SKIN_BB_BASE_URL is not configured")
    last_err: ScannerApiError | None = None
    for base in bases:
        try:
            return await _fetch_user_details_at_base(base_norm=base, token=token)
        except ScannerApiError as e:
            if e.status_code in (401, 403):
                last_err = e
                continue
            raise
    raise last_err or ScannerApiError(401, "Invalid or expired app token")


async def authenticate_any_user(
    authorization: Optional[str] = Header(None),
    access_token: Optional[str] = Header(None, alias="access-token"),
    x_access_token: Optional[str] = Header(None, alias="x-access-token"),
) -> dict[str, Any]:
    auth_header = _merged_authorization_header(authorization, access_token, x_access_token)
    if not auth_header:
        raise ScannerApiError(401, "Unauthorized: missing Authorization Bearer token")

    auth_steps = (
        ("user-details", authenticate_app_user),
        ("local-jwt", authenticate_local_jwt),
        ("verify-token", scanner_auth_sso),
    )
    failures: list[str] = []
    for label, fn in auth_steps:
        try:
            return await fn(authorization=auth_header)
        except ScannerApiError as err:
            if err.status_code not in (401, 403):
                raise
            failures.append(f"{label}: {err.message}")
            if _AUTH_DEBUG:
                logger.warning("Label Looker auth step failed (%s): %s", label, err.message)

    raise ScannerApiError(
        401,
        "Unauthorized: could not validate access token. "
        f"Tried: {'; '.join(failures)}. "
        "Send a SkinBB access JWT (not refresh token) in Authorization Bearer. "
        "Profile data is loaded from Mongo after auth — fix the token, not Mongo.",
    )


async def authenticate_any_user_optional(
    authorization: Optional[str] = Header(None),
    access_token: Optional[str] = Header(None, alias="access-token"),
    x_access_token: Optional[str] = Header(None, alias="x-access-token"),
) -> Optional[dict[str, Any]]:
    auth_header = _merged_authorization_header(authorization, access_token, x_access_token)
    if not auth_header:
        return None
    try:
        return await authenticate_any_user(
            authorization=auth_header,
            access_token=None,
            x_access_token=None,
        )
    except ScannerApiError as e:
        if e.status_code in (401, 403):
            return None
        raise


async def authenticate_app_user_optional(
    authorization: Optional[str] = Header(None),
    access_token: Optional[str] = Header(None, alias="access-token"),
    x_access_token: Optional[str] = Header(None, alias="x-access-token"),
) -> Optional[dict[str, Any]]:
    auth_header = _merged_authorization_header(authorization, access_token, x_access_token)
    if not auth_header:
        return None
    try:
        return await authenticate_app_user(authorization=auth_header)
    except ScannerApiError as e:
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
    return PanelUserContext(user=user, role=data.get("role"), permissions=list(data.get("permissions") or []))


async def authorize_scan_overview_view(ctx: PanelUserContext = Depends(verify_jwt_panel)) -> PanelUserContext:
    if not _user_can(ctx.permissions, ctx.role, "scan-overview", "view"):
        raise ScannerApiError(403, "Forbidden")
    return ctx


def _user_can(permissions: list[Any], role: Any, page: str, action: str) -> bool:
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
    return ctx
