"""Backward-compatible import path — use app.hlhp instead."""

import warnings

warnings.warn(
    "app.hl_engine was renamed to app.hlhp; update imports to app.hlhp",
    DeprecationWarning,
    stacklevel=2,
)

from app.hlhp.api.alerts import router as alerts_router
from app.hlhp.api.personalized_alerts import router as personalized_alerts_router

__all__ = ["alerts_router", "personalized_alerts_router"]
