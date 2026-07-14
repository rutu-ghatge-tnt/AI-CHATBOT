"""HTTP client for the HLHP event hub (skinbb-main-backend)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.hlhp.core.bus_contract import BusKey
from app.hlhp.core.hlhp_settings import get_hlhp_settings

logger = logging.getLogger(__name__)


class HlhpHubError(Exception):
    def __init__(self, status_code: int, message: str, payload: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.payload = payload


class HlhpBusClient:
    """Publishes bus events and reads hub state."""

    def __init__(self, *, timeout_s: float = 15.0) -> None:
        self._settings = get_hlhp_settings()
        self._timeout = timeout_s

    @property
    def configured(self) -> bool:
        return self._settings.hub_configured

    def _headers(
        self,
        *,
        bearer_token: str | None = None,
        on_behalf_user_id: str | None = None,
        on_behalf_role: str | None = None,
    ) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if bearer_token:
            headers["Authorization"] = f"Bearer {bearer_token}"
        elif self._settings.service_api_key:
            headers["Authorization"] = f"Bearer {self._settings.service_api_key}"
            headers["X-HLHP-Service-Key"] = self._settings.service_api_key
        if on_behalf_user_id:
            headers["X-On-Behalf-Of"] = on_behalf_user_id
        if on_behalf_role:
            headers["X-On-Behalf-Role"] = on_behalf_role
        return headers

    async def publish(
        self,
        key: BusKey | str,
        payload: dict[str, Any],
        *,
        seeker_id: str | None = None,
        doctor_id: str | None = None,
        src: str = "ai-tools",
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

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                self._settings.hub_events_url(),
                json=body,
                headers=self._headers(
                    bearer_token=bearer_token,
                    on_behalf_user_id=on_behalf_user_id,
                    on_behalf_role=on_behalf_role,
                ),
            )

        if response.status_code >= 400:
            detail: Any
            try:
                detail = response.json()
            except Exception:
                detail = response.text
            logger.warning("HLHP hub publish refused %s %s: %s", key, response.status_code, detail)
            raise HlhpHubError(response.status_code, f"Hub publish failed for {key}", detail)

        try:
            return response.json()
        except Exception:
            return {"applied": True}

    async def get_state(
        self,
        *,
        seeker_id: str | None = None,
        doctor_id: str | None = None,
        bearer_token: str | None = None,
    ) -> dict[str, Any]:
        if not self.configured:
            raise HlhpHubError(503, "HLHP hub is not configured (set HLHP_HUB_URL)")

        params: dict[str, str] = {}
        if seeker_id:
            params["seekerId"] = seeker_id
        if doctor_id:
            params["doctorId"] = doctor_id

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(
                self._settings.hub_state_url(),
                params=params or None,
                headers=self._headers(bearer_token=bearer_token),
            )

        if response.status_code >= 400:
            try:
                detail = response.json()
            except Exception:
                detail = response.text
            raise HlhpHubError(response.status_code, "Hub state read failed", detail)

        data = response.json()
        return data if isinstance(data, dict) else {}


_bus_client: HlhpBusClient | None = None


def get_bus_client() -> HlhpBusClient:
    global _bus_client
    if _bus_client is None:
        _bus_client = HlhpBusClient()
    return _bus_client
