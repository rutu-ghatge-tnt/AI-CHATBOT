"""HLHP Mongo persistence errors — critical user writes must not fail silently."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class HlhpStoreError(RuntimeError):
    """A required HLHP Mongo write did not persist."""

    def __init__(
        self,
        *,
        collection: str,
        operation: str,
        cause: Exception | None = None,
    ) -> None:
        self.collection = collection
        self.operation = operation
        self.cause = cause
        msg = f"HLHP {collection} {operation} failed"
        if cause is not None:
            msg = f"{msg}: {cause}"
        super().__init__(msg)


def fail_write(collection: str, operation: str, exc: Exception) -> None:
    """Log and raise when a user-facing write must succeed."""
    logger.error("HLHP %s %s failed: %s", collection, operation, exc)
    raise HlhpStoreError(collection=collection, operation=operation, cause=exc) from exc
