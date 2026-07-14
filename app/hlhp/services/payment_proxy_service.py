"""Proxy HLHP Plus payments to skinbb-main-backend (Razorpay)."""

from __future__ import annotations

from typing import Any

import httpx

from app.hlhp.core.bus_client import HlhpHubError, get_bus_client
from app.hlhp.core.hlhp_settings import get_hlhp_settings
from app.hlhp.models.hlhp_bus import HlhpPaymentCheckoutRequest


class HlhpPaymentError(Exception):
    def __init__(self, status_code: int, message: str, detail: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.detail = detail


async def get_plus_state(
    seeker_id: str,
    doctor_id: str | None = None,
    *,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    settings = get_hlhp_settings()
    client = get_bus_client()
    fee = settings.default_plus_fee_inr
    live = False
    payment: dict[str, Any] | None = None

    if client.configured:
        try:
            state = await client.get_state(
                seeker_id=seeker_id,
                doctor_id=doctor_id,
                bearer_token=bearer_token,
            )
            sub = state.get("hlhp_subscription_v1")
            if isinstance(sub, dict) and sub.get("fee"):
                fee = int(sub["fee"])
                live = True
            pay = state.get("hlhp_payment_v1")
            if isinstance(pay, dict):
                payment = pay
        except HlhpHubError:
            pass

    return {
        "fee": fee,
        "live": live,
        "payment": payment,
        "currency": "INR",
    }


async def initiate_checkout(
    seeker_id: str,
    body: HlhpPaymentCheckoutRequest,
    *,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    if not body.tnc_accepted:
        raise HlhpPaymentError(400, "tnc_accepted required — accept T&C before paying")

    settings = get_hlhp_settings()
    if not settings.node_configured:
        raise HlhpPaymentError(
            503,
            "HLHP payments are not configured (set HLHP_NODE_API_URL)",
        )

    url = f"{settings.node_hlhp_payments_base()}/checkout"
    payload = {
        "doctorId": body.doctor_id,
        "tncAccepted": True,
        "name": body.name,
        "winback": body.winback,
        "seekerId": seeker_id,
    }
    headers = {"Content-Type": "application/json"}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=payload, headers=headers)

    if response.status_code >= 400:
        detail: Any
        try:
            detail = response.json()
        except Exception:
            detail = response.text
        raise HlhpPaymentError(response.status_code, "Payment checkout failed", detail)

    data = response.json()
    if isinstance(data, dict) and "data" in data:
        return data["data"] if isinstance(data["data"], dict) else data
    return data if isinstance(data, dict) else {"raw": data}
