"""Tests for HLHP bus contract and client."""

from __future__ import annotations

import pytest

from app.hlhp.core.bus_contract import (
    APPEND_KEYS,
    DOCTOR_WRITE_KEYS,
    MERGE_KEYS,
    SEEKER_WRITE_KEYS,
    TRANSIENT_KEYS,
    role_may_write,
)


def test_append_and_transient_keys_disjoint():
    assert not APPEND_KEYS & TRANSIENT_KEYS
    assert MERGE_KEYS <= SEEKER_WRITE_KEYS | DOCTOR_WRITE_KEYS


def test_role_write_matrix():
    assert role_may_write("seeker", "hlhp_goal_setup_v1")
    assert not role_may_write("seeker", "hlhp_panel_accept_v1")
    assert role_may_write("doctor", "hlhp_panel_accept_v1")
    assert not role_may_write("doctor", "hlhp_goal_setup_v1")
    assert role_may_write("admin", "hlhp_payment_v1")


@pytest.mark.anyio
async def test_bus_client_requires_hub_url(monkeypatch):
    monkeypatch.delenv("HLHP_HUB_URL", raising=False)
    from app.hlhp.core.hlhp_settings import HlhpSettings, get_hlhp_settings

    get_hlhp_settings.cache_clear()
    settings = HlhpSettings()
    assert not settings.hub_configured

    from app.hlhp.core.bus_client import HlhpBusClient, HlhpHubError

    client = HlhpBusClient()
    with pytest.raises(HlhpHubError) as exc:
        await client.publish("hlhp_goal_setup_v1", {"goalName": "Test", "ts": 1})
    assert exc.value.status_code == 503
