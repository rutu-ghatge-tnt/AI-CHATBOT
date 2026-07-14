"""HLHP hub / integration HTTP errors."""

from __future__ import annotations

from fastapi import HTTPException

from app.hlhp.core.bus_client import HlhpHubError
from app.hlhp.services.payment_proxy_service import HlhpPaymentError


def hub_unavailable_detail() -> dict[str, str]:
    return {
        "code": "hlhp_hub_unavailable",
        "message": "HLHP realtime hub is not available yet. Set HLHP_HUB_URL on the server.",
        "action": "Retry later or contact support if this persists.",
    }


def raise_for_hub_error(exc: HlhpHubError) -> None:
    if exc.status_code == 503:
        raise HTTPException(status_code=503, detail=hub_unavailable_detail()) from exc
    raise HTTPException(
        status_code=exc.status_code if 400 <= exc.status_code < 600 else 502,
        detail={
            "code": "hlhp_hub_error",
            "message": exc.message,
            "payload": exc.payload,
        },
    ) from exc


def raise_for_payment_error(exc: HlhpPaymentError) -> None:
    raise HTTPException(
        status_code=exc.status_code if 400 <= exc.status_code < 600 else 502,
        detail={
            "code": "hlhp_payment_error",
            "message": exc.message,
            "payload": exc.detail,
        },
    ) from exc
