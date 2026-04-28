from __future__ import annotations

from typing import Any, Callable, Coroutine

from fastapi import APIRouter

from app.label_looker.profile_match_router import profile_match_routes


def ll2_routes(auth_user: Callable[..., Coroutine[Any, Any, dict[str, Any]]]) -> APIRouter:
    # Backward-compatible alias while migrating away from ll2 naming.
    return profile_match_routes(auth_user)
