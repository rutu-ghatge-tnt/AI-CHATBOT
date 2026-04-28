from __future__ import annotations

from typing import Any


async def ingredient_analysis(*, body: dict[str, Any], user: dict[str, Any] | None) -> dict[str, Any]:
    from app.label_looker import analysis_service as legacy

    return await legacy._ingredient_analysis_impl(body=body, user=user)


async def ingredient_analysis_from_text(
    *,
    body: dict[str, Any],
    user: dict[str, Any] | None,
) -> dict[str, Any]:
    from app.label_looker import analysis_service as legacy

    return await legacy._ingredient_analysis_from_text_impl(body=body, user=user)
