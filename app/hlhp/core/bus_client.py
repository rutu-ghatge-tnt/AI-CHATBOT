"""HTTP client for the HLHP event hub (SkinBB Node Phase 1)."""

from __future__ import annotations

import logging
from typing import Any, Sequence

import httpx

from app.hlhp.core.bus_contract import BusKey
from app.hlhp.core.hlhp_settings import get_hlhp_settings
from app.hlhp.core.hub_state import normalize_hub_state, unwrap_envelope

logger = logging.getLogger(__name__)


class HlhpHubError(Exception):
    def __init__(self, status_code: int, message: str, payload: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.payload = payload


class HlhpBusClient:
    """Publishes bus events, reads hub state (``format=raw``), uploads media."""

    def __init__(self, *, timeout_s: float = 15.0) -> None:
        self._settings = get_hlhp_settings()
        self._timeout = timeout_s

    @property
    def configured(self) -> bool:
        return self._settings.hub_configured

    def _auth_headers(
        self,
        *,
        bearer_token: str | None = None,
        on_behalf_user_id: str | None = None,
        on_behalf_role: str | None = None,
        json_content: bool = True,
    ) -> dict[str, str]:
        headers: dict[str, str] = {}
        if json_content:
            headers["Content-Type"] = "application/json"

        if bearer_token:
            headers["Authorization"] = f"Bearer {bearer_token}"
        elif self._settings.service_api_key:
            # Node M2M: X-HLHP-Service-Key (do not pretend the key is a user JWT).
            headers["X-HLHP-Service-Key"] = self._settings.service_api_key

        if on_behalf_user_id:
            headers["X-On-Behalf-Of"] = on_behalf_user_id
        if on_behalf_role:
            headers["X-On-Behalf-Role"] = on_behalf_role
        return headers

    def _raise_http(self, response: httpx.Response, *, action: str) -> None:
        detail: Any
        try:
            detail = response.json()
        except Exception:
            detail = response.text
        logger.warning("HLHP hub %s refused %s: %s", action, response.status_code, detail)
        raise HlhpHubError(response.status_code, f"Hub {action} failed", detail)

    async def publish(
        self,
        key: BusKey | str,
        payload: dict[str, Any],
        *,
        seeker_id: str | None = None,
        doctor_id: str | None = None,
        src: str = "ai-tools",
        as_role: str | None = None,
        bearer_token: str | None = None,
        on_behalf_user_id: str | None = None,
        on_behalf_role: str | None = None,
    ) -> dict[str, Any]:
        if not self.configured:
            raise HlhpHubError(503, "HLHP hub is not configured (set HLHP_HUB_URL)")

        body: dict[str, Any] = {"key": key, "payload": payload, "src": src}
        if seeker_id:
            body["seekerId"] = seeker_id
        if doctor_id:
            body["doctorId"] = doctor_id
        role = as_role or on_behalf_role
        if role:
            body["asRole"] = role

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                self._settings.hub_events_url(),
                json=body,
                headers=self._auth_headers(
                    bearer_token=bearer_token,
                    on_behalf_user_id=on_behalf_user_id,
                    on_behalf_role=on_behalf_role,
                ),
            )

        if response.status_code >= 400:
            self._raise_http(response, action=f"publish:{key}")

        try:
            raw = response.json()
        except Exception:
            return {"applied": True}

        data = unwrap_envelope(raw)
        if isinstance(data, dict):
            return data
        return {"applied": True, "raw": data}

    async def get_state(
        self,
        *,
        seeker_id: str | None = None,
        doctor_id: str | None = None,
        as_role: str | None = None,
        bearer_token: str | None = None,
        state_format: str = "raw",
        chat_limit: int | None = None,
        chat_before_ts: int | None = None,
    ) -> dict[str, Any]:
        if not self.configured:
            raise HlhpHubError(503, "HLHP hub is not configured (set HLHP_HUB_URL)")

        params: dict[str, str] = {"format": state_format or "raw"}
        if seeker_id:
            params["seekerId"] = seeker_id
        if doctor_id:
            params["doctorId"] = doctor_id
        if as_role:
            params["asRole"] = as_role
        if chat_limit is not None and chat_limit > 0:
            params["chatLimit"] = str(int(chat_limit))
        if chat_before_ts is not None and chat_before_ts > 0:
            params["chatBeforeTs"] = str(int(chat_before_ts))

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(
                self._settings.hub_state_url(),
                params=params,
                headers=self._auth_headers(bearer_token=bearer_token),
            )

        if response.status_code >= 400:
            self._raise_http(response, action="state")

        try:
            raw = response.json()
        except Exception:
            return {}
        return normalize_hub_state(raw)

    async def upload_media(
        self,
        files: Sequence[tuple[str, bytes, str]],
        *,
        bearer_token: str | None = None,
        on_behalf_user_id: str | None = None,
        on_behalf_role: str | None = None,
    ) -> dict[str, Any]:
        """Multipart upload to ``POST /hlhp/hub/media`` (field name ``files``)."""
        if not self.configured:
            raise HlhpHubError(503, "HLHP hub is not configured (set HLHP_HUB_URL)")
        if not files:
            raise HlhpHubError(400, "At least one file is required")

        multipart = [
            ("files", (name, content, content_type or "application/octet-stream"))
            for name, content, content_type in files
        ]

        async with httpx.AsyncClient(timeout=max(self._timeout, 60.0)) as client:
            response = await client.post(
                self._settings.hub_media_url(),
                files=multipart,
                headers=self._auth_headers(
                    bearer_token=bearer_token,
                    on_behalf_user_id=on_behalf_user_id,
                    on_behalf_role=on_behalf_role,
                    json_content=False,
                ),
            )

        if response.status_code >= 400:
            self._raise_http(response, action="media")

        try:
            raw = response.json()
        except Exception:
            return {"ok": True}

        data = unwrap_envelope(raw)
        if isinstance(data, dict):
            return data
        if isinstance(data, list):
            return {"files": data, "urls": _urls_from_media_list(data)}
        return {"ok": True, "raw": data}


def _urls_from_media_list(items: list[Any]) -> list[str]:
    urls: list[str] = []
    for item in items:
        if isinstance(item, str) and item.startswith("http"):
            urls.append(item)
        elif isinstance(item, dict):
            for key in ("url", "img", "secureUrl", "secure_url"):
                val = item.get(key)
                if isinstance(val, str) and val.startswith("http"):
                    urls.append(val)
                    break
    return urls


def normalize_media_upload_response(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize Node media responses into ``{ urls, files }``."""
    urls: list[str] = []
    files: list[Any] = []

    if isinstance(data.get("urls"), list):
        urls = [u for u in data["urls"] if isinstance(u, str) and u.startswith("http")]
    if isinstance(data.get("files"), list):
        files = data["files"]
        urls = urls or _urls_from_media_list(files)
    if not urls:
        for key in ("url", "img"):
            val = data.get(key)
            if isinstance(val, str) and val.startswith("http"):
                urls = [val]
                break
    if not files and urls:
        files = [{"url": u} for u in urls]

    return {"urls": urls, "files": files, "count": len(urls)}


_bus_client: HlhpBusClient | None = None


def get_bus_client() -> HlhpBusClient:
    global _bus_client
    if _bus_client is None:
        _bus_client = HlhpBusClient()
    return _bus_client


def reset_bus_client() -> None:
    """Clear singleton (tests / after env reload)."""
    global _bus_client
    _bus_client = None
