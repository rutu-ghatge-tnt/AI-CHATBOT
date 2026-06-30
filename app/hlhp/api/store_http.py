"""Map HLHP store failures to HTTP responses."""

from __future__ import annotations

from typing import NoReturn

from fastapi import HTTPException

from app.hlhp.api.errors import service_unavailable_detail
from app.hlhp.db_errors import HlhpStoreError


def http_503_for_store_error(exc: HlhpStoreError) -> NoReturn:
    reason = str(exc.cause or exc)
    raise HTTPException(
        status_code=503,
        detail=service_unavailable_detail(
            code="store_write_failed",
            message="We could not save your data right now. Please try again in a moment.",
            reason=reason,
        ),
    ) from exc
