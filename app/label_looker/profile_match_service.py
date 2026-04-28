from __future__ import annotations

from typing import Any

from app.label_looker import ll2_service as _legacy


async def get_profile(*, user: dict[str, Any]) -> dict[str, Any]:
    return await _legacy.get_profile(user=user)


async def patch_profile(*, user: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    return await _legacy.patch_profile(user=user, body=body)


async def score_product(*, user: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    return await _legacy.score_product(user=user, body=body)


async def _score_product_impl(*, user: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    return await _legacy._score_product_impl(user=user, body=body)


async def submit_feedback(*, user: dict[str, Any], scan_id: str, body: dict[str, Any]) -> dict[str, Any]:
    return await _legacy.submit_feedback(user=user, scan_id=scan_id, body=body)


def __getattr__(name: str) -> Any:
    # Compatibility for tests/helper access during transition.
    return getattr(_legacy, name)
