from __future__ import annotations

from typing import Any


async def submit_profile_validation(*, body: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    from app.label_looker import analysis_service as legacy

    return await legacy._submit_profile_validation_impl(body=body, user=user)


async def profile_validation_status(*, body: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    from app.label_looker import analysis_service as legacy

    return await legacy._profile_validation_status_impl(body=body, user=user)
