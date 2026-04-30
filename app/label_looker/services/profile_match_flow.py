from __future__ import annotations

from typing import Any


async def score_product(*, user: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    from app.label_looker import profile_match_service as service

    return await service._score_product_impl(user=user, body=body)
