"""Pytest hooks for this repo."""

from __future__ import annotations

import pytest


@pytest.fixture(params=["asyncio"])
def anyio_backend(request: pytest.FixtureRequest) -> str:
    """Restrict anyio-marked async tests to asyncio (trio + anyio can break on newer trio)."""
    return request.param
