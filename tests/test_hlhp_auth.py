"""HLHP API auth enforcement — user-scoped routes require a valid SkinBB token."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from app.hlhp.api.deps_auth import (
    resolve_optional_personalization_user_id,
    resolve_scan_user_id,
    verify_client_user_id,
)


def _auth_user(uid: str = "user-42") -> dict:
    return {"id": uid}


class TestAuthHelpers:
    def test_verify_client_user_id_accepts_match(self):
        assert verify_client_user_id(_auth_user("u1"), "u1") == "u1"

    def test_verify_client_user_id_rejects_mismatch(self):
        with pytest.raises(HTTPException) as exc:
            verify_client_user_id(_auth_user("u1"), "other")
        assert exc.value.status_code == 403

    def test_resolve_scan_guest_without_token(self):
        assert resolve_scan_user_id(None, None) is None

    def test_resolve_scan_requires_token_when_user_id_sent(self):
        with pytest.raises(HTTPException) as exc:
            resolve_scan_user_id("u1", None)
        assert exc.value.status_code == 401

    def test_resolve_scan_uses_token_when_user_id_omitted(self):
        assert resolve_scan_user_id(None, _auth_user("u1")) == "u1"

    def test_optional_personalization_blocks_spoofed_user_id(self):
        with pytest.raises(HTTPException) as exc:
            resolve_optional_personalization_user_id(None, "victim")
        assert exc.value.status_code == 401

    def test_optional_personalization_uses_token_without_query_id(self):
        assert resolve_optional_personalization_user_id(_auth_user("u1"), None) == "u1"


class TestHlhpAuthRoutes:
    def test_history_requires_auth(self):
        try:
            from httpx import ASGITransport, AsyncClient
        except ImportError:
            pytest.skip("httpx ASGITransport not available")

        async def _call():
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                r = await client.get("/api/hlhp/history", params={"user_id": "any"})
                assert r.status_code == 401
                assert r.json()["detail"]["code"] == "auth_required"

        asyncio.run(_call())

    def test_scan_guest_without_user_id_still_works(self):
        try:
            from httpx import ASGITransport, AsyncClient
        except ImportError:
            pytest.skip("httpx ASGITransport not available")

        async def _call():
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                r = await client.post(
                    "/api/hlhp/scan",
                    json={
                        "user_id": None,
                        "city": "Mumbai",
                        "local_time": "2026-05-12T08:32:00+05:30",
                        "raw_uvi": 8.0,
                        "raw_aqi": 145,
                        "raw_rh": 72.0,
                        "raw_temp": 31.0,
                    },
                )
                assert r.status_code == 200
                assert r.json()["mode"] == "guest"

        asyncio.run(_call())

    def test_scan_with_user_id_requires_auth(self):
        try:
            from httpx import ASGITransport, AsyncClient
        except ImportError:
            pytest.skip("httpx ASGITransport not available")

        async def _call():
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                r = await client.post(
                    "/api/hlhp/scan",
                    json={
                        "user_id": "someone",
                        "city": "Mumbai",
                        "local_time": "2026-05-12T08:32:00+05:30",
                        "raw_uvi": 8.0,
                        "raw_aqi": 145,
                        "raw_rh": 72.0,
                        "raw_temp": 31.0,
                    },
                )
                assert r.status_code == 401

        asyncio.run(_call())

    def test_explore_guest_without_user_id_still_works(self):
        try:
            from httpx import ASGITransport, AsyncClient
        except ImportError:
            pytest.skip("httpx ASGITransport not available")

        async def _call():
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                r = await client.get("/api/hlhp/explore", params={"city": "Mumbai"})
                assert r.status_code == 200

        asyncio.run(_call())

    def test_explore_with_user_id_requires_auth(self):
        try:
            from httpx import ASGITransport, AsyncClient
        except ImportError:
            pytest.skip("httpx ASGITransport not available")

        async def _call():
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                r = await client.get(
                    "/api/hlhp/explore",
                    params={"city": "Mumbai", "user_id": "victim"},
                )
                assert r.status_code == 401

        asyncio.run(_call())
