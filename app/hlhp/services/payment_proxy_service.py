"""Proxy HLHP Glow Plan Plus payments to SkinBB Node (Razorpay).

Node owns checkout / verify / webhook / ledger / 80-20 split.
Python only forwards authenticated seeker calls and reads hub snapshots.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.hlhp.core.bus_client import HlhpHubError, get_bus_client
from app.hlhp.core.hlhp_settings import get_hlhp_settings
from app.hlhp.core.hub_state import get_bus_value, unwrap_envelope
from app.hlhp.models.hlhp_bus import (
    HlhpPaymentCheckoutRequest,
    HlhpPaymentDoctorScopedRequest,
    HlhpPaymentRenewRequest,
    HlhpPaymentVerifyRequest,
)

logger = logging.getLogger(__name__)


class HlhpPaymentError(Exception):
    def __init__(self, status_code: int, message: str, detail: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.detail = detail


def _auth_headers(bearer_token: str | None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    return headers


async def _node_post(
    path: str,
    payload: dict[str, Any],
    *,
    bearer_token: str | None,
) -> dict[str, Any]:
    settings = get_hlhp_settings()
    if not settings.node_configured:
        raise HlhpPaymentError(
            503,
            "HLHP payments are not configured (set HLHP_NODE_API_URL)",
        )

    url = f"{settings.node_hlhp_payments_base()}/{path.lstrip('/')}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            url,
            json=payload,
            headers=_auth_headers(bearer_token),
        )

    if response.status_code >= 400:
        detail: Any
        try:
            detail = response.json()
        except Exception:
            detail = response.text
        logger.warning("HLHP payment %s failed %s: %s", path, response.status_code, detail)
        raise HlhpPaymentError(response.status_code, f"Payment {path} failed", detail)

    try:
        raw = response.json()
    except Exception:
        return {"ok": True}

    data = unwrap_envelope(raw)
    if isinstance(data, dict):
        return data
    return {"ok": True, "raw": data}


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
    subscription: dict[str, Any] | None = None

    if client.configured:
        try:
            state = await client.get_state(
                seeker_id=seeker_id,
                doctor_id=doctor_id,
                bearer_token=bearer_token,
                as_role="seeker",
            )
            # Fee lives on doctor snapshot; fall back to lane if present.
            sub = get_bus_value(
                state,
                "hlhp_subscription_v1",
                seeker_id=seeker_id,
                doctor_id=doctor_id,
            )
            if isinstance(sub, dict):
                subscription = sub
                if sub.get("fee") is not None:
                    fee = int(sub["fee"])
                    live = True

            pay = get_bus_value(
                state,
                "hlhp_payment_v1",
                seeker_id=seeker_id,
                doctor_id=doctor_id,
            )
            if isinstance(pay, dict):
                payment = pay
        except HlhpHubError as exc:
            logger.warning("HLHP plus state hub read skipped: %s", exc.message)

    return {
        "fee": fee,
        "live": live,
        "payment": payment,
        "subscription": subscription,
        "currency": "INR",
        "doctorId": doctor_id,
    }


async def initiate_checkout(
    seeker_id: str,
    body: HlhpPaymentCheckoutRequest,
    *,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    if not body.tnc_accepted:
        raise HlhpPaymentError(400, "tncAccepted required — accept T&C before paying")
    if not (body.doctor_id or "").strip():
        raise HlhpPaymentError(400, "doctorId is required")

    payload: dict[str, Any] = {
        "doctorId": body.doctor_id.strip(),
        "tncAccepted": True,
        "seekerId": seeker_id,
    }
    if (body.name or "").strip():
        payload["name"] = body.name.strip()

    return await _node_post("checkout", payload, bearer_token=bearer_token)


async def verify_payment(
    seeker_id: str,
    body: HlhpPaymentVerifyRequest,
    *,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    payload = {
        "razorpayPaymentId": body.razorpay_payment_id.strip(),
        "razorpaySubscriptionId": body.razorpay_subscription_id.strip(),
        "razorpaySignature": body.razorpay_signature.strip(),
        "seekerId": seeker_id,
    }
    return await _node_post("verify", payload, bearer_token=bearer_token)


async def cancel_subscription(
    seeker_id: str,
    body: HlhpPaymentDoctorScopedRequest,
    *,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    payload = {
        "doctorId": body.doctor_id.strip(),
        "seekerId": seeker_id,
    }
    return await _node_post("cancel", payload, bearer_token=bearer_token)


async def resume_subscription(
    seeker_id: str,
    body: HlhpPaymentDoctorScopedRequest,
    *,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    payload = {
        "doctorId": body.doctor_id.strip(),
        "seekerId": seeker_id,
    }
    return await _node_post("resume", payload, bearer_token=bearer_token)


async def renew_subscription(
    seeker_id: str,
    body: HlhpPaymentRenewRequest,
    *,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    if not body.tnc_accepted:
        raise HlhpPaymentError(400, "tncAccepted required — accept T&C before renewing")

    payload: dict[str, Any] = {
        "doctorId": body.doctor_id.strip(),
        "tncAccepted": True,
        "seekerId": seeker_id,
    }
    if (body.name or "").strip():
        payload["name"] = body.name.strip()
    return await _node_post("renew", payload, bearer_token=bearer_token)
