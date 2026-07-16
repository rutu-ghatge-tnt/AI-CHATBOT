"""HLHP Plus payments — proxy to Node Razorpay."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.hlhp.api.deps_auth import hlhp_authenticated_user, verify_client_user_id
from app.hlhp.api.hub_errors import raise_for_hub_error, raise_for_payment_error
from app.hlhp.core.bus_client import HlhpHubError
from app.hlhp.models.hlhp_bus import (
    HlhpPaymentCheckoutRequest,
    HlhpPaymentDoctorScopedRequest,
    HlhpPaymentRenewRequest,
    HlhpPaymentVerifyRequest,
)
from app.hlhp.services.payment_proxy_service import (
    HlhpPaymentError,
    cancel_subscription,
    get_plus_state,
    initiate_checkout,
    renew_subscription,
    resume_subscription,
    verify_payment,
)

router = APIRouter(prefix="/v2", tags=["HLHP Payments"])


def _bearer_from_user(user: dict[str, Any]) -> str | None:
    token = user.get("_label_looker_access_token")
    return str(token) if token else None


@router.get("/plus")
async def plus_state(
    user_id: str = Query(...),
    doctor_id: str | None = Query(None, alias="doctorId"),
    user: dict = Depends(hlhp_authenticated_user),
) -> dict[str, Any]:
    uid = verify_client_user_id(user, user_id)
    try:
        return await get_plus_state(uid, doctor_id, bearer_token=_bearer_from_user(user))
    except HlhpHubError as exc:
        raise_for_hub_error(exc)


@router.post("/payments/checkout")
async def checkout(
    body: HlhpPaymentCheckoutRequest,
    user: dict = Depends(hlhp_authenticated_user),
) -> dict[str, Any]:
    uid = verify_client_user_id(user, body.user_id)
    try:
        return await initiate_checkout(uid, body, bearer_token=_bearer_from_user(user))
    except HlhpPaymentError as exc:
        raise_for_payment_error(exc)


@router.post("/payments/verify")
async def verify(
    body: HlhpPaymentVerifyRequest,
    user: dict = Depends(hlhp_authenticated_user),
) -> dict[str, Any]:
    uid = verify_client_user_id(user, body.user_id)
    try:
        return await verify_payment(uid, body, bearer_token=_bearer_from_user(user))
    except HlhpPaymentError as exc:
        raise_for_payment_error(exc)


@router.post("/payments/cancel")
async def cancel(
    body: HlhpPaymentDoctorScopedRequest,
    user: dict = Depends(hlhp_authenticated_user),
) -> dict[str, Any]:
    uid = verify_client_user_id(user, body.user_id)
    try:
        return await cancel_subscription(uid, body, bearer_token=_bearer_from_user(user))
    except HlhpPaymentError as exc:
        raise_for_payment_error(exc)


@router.post("/payments/resume")
async def resume(
    body: HlhpPaymentDoctorScopedRequest,
    user: dict = Depends(hlhp_authenticated_user),
) -> dict[str, Any]:
    uid = verify_client_user_id(user, body.user_id)
    try:
        return await resume_subscription(uid, body, bearer_token=_bearer_from_user(user))
    except HlhpPaymentError as exc:
        raise_for_payment_error(exc)


@router.post("/payments/renew")
async def renew(
    body: HlhpPaymentRenewRequest,
    user: dict = Depends(hlhp_authenticated_user),
) -> dict[str, Any]:
    uid = verify_client_user_id(user, body.user_id)
    try:
        return await renew_subscription(uid, body, bearer_token=_bearer_from_user(user))
    except HlhpPaymentError as exc:
        raise_for_payment_error(exc)
