"""Tests for HLHP hub state helpers, chat payloads, and bus client."""

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
from app.hlhp.core.chat_payload import ChatPayloadError, build_chat_message, normalize_img
from app.hlhp.core.hub_state import (
    get_bus_value,
    iter_doctor_lanes,
    lane_bucket,
    normalize_hub_state,
    unwrap_envelope,
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


def test_unwrap_envelope():
    assert unwrap_envelope({"statusCode": 200, "success": True, "data": {"a": 1}}) == {"a": 1}
    assert unwrap_envelope({"a": 1}) == {"a": 1}
    assert unwrap_envelope([1, 2]) == [1, 2]


def test_normalize_hub_state_nested_lane():
    raw = {
        "statusCode": 200,
        "success": True,
        "data": {
            "seekers": {
                "s1": {
                    "d1": {
                        "hlhp_goal_setup_v1": {"goalName": "Wedding", "ts": 1},
                        "hlhp_shared_chat_v1": [{"txt": "hi", "ts": 2}],
                    }
                }
            },
            "doctors": {"d1": {"hlhp_subscription_v1": {"fee": 1499, "ts": 3}}},
        },
    }
    state = normalize_hub_state(raw)
    assert get_bus_value(state, "hlhp_goal_setup_v1", seeker_id="s1", doctor_id="d1")[
        "goalName"
    ] == "Wedding"
    assert get_bus_value(state, "hlhp_subscription_v1", doctor_id="d1")["fee"] == 1499
    lane = lane_bucket(state, seeker_id="s1", doctor_id="d1")
    assert len(lane["hlhp_shared_chat_v1"]) == 1


def test_legacy_flat_seeker_lane():
    state = {
        "seekers": {
            "s1": {
                "hlhp_payment_v1": {"fee": 1499, "ts": 9},
            }
        }
    }
    assert get_bus_value(state, "hlhp_payment_v1", seeker_id="s1")["fee"] == 1499


def test_iter_doctor_lanes():
    state = {
        "seekers": {
            "s1": {"d1": {"hlhp_shared_chat_v1": []}},
            "s2": {"d2": {"hlhp_shared_chat_v1": [{"ts": 1}]}},
            "s3": {"d1": {"hlhp_shared_chat_v1": [{"ts": 2}]}},
        }
    }
    lanes = iter_doctor_lanes(state, "d1")
    assert {sid for sid, _ in lanes} == {"s1", "s3"}


def test_normalize_img_https():
    url = "https://cdn.example.com/a.jpg"
    assert normalize_img(url) == url


def test_normalize_img_rejects_garbage():
    with pytest.raises(ChatPayloadError):
        normalize_img("not-a-url")


def test_normalize_img_rejects_data_url():
    data = "data:image/jpeg;base64," + ("A" * 100)
    with pytest.raises(ChatPayloadError) as exc:
        normalize_img(data)
    assert "data URL" in str(exc.value).lower() or "not allowed" in str(exc.value).lower()


def test_build_chat_message_image_only():
    msg = build_chat_message(
        who="seeker",
        photo=True,
        img="https://cdn.example.com/selfie.jpg",
    )
    assert msg["photo"] is True
    assert msg["img"].startswith("https://")
    assert msg["who"] == "seeker"
    assert "ts" in msg


def test_build_chat_message_requires_content():
    with pytest.raises(ChatPayloadError):
        build_chat_message(who="seeker", txt="  ")


def test_normalize_media_upload_response():
    from app.hlhp.core.bus_client import normalize_media_upload_response

    out = normalize_media_upload_response(
        {"files": [{"url": "https://cdn.example.com/a.jpg", "name": "a.jpg"}]}
    )
    assert out["urls"] == ["https://cdn.example.com/a.jpg"]
    assert out["count"] == 1


def test_hub_ws_url_derived(monkeypatch):
    monkeypatch.setenv("HLHP_HUB_URL", "https://api.example.com/api/v1/hlhp/hub")
    monkeypatch.delenv("HLHP_HUB_WS_URL", raising=False)
    from app.hlhp.core.hlhp_settings import HlhpSettings, get_hlhp_settings

    get_hlhp_settings.cache_clear()
    settings = HlhpSettings()
    ws = settings.hub_ws_connect_url(service_key="abc", seeker_id="s1", doctor_id="d1")
    assert ws.startswith("wss://api.example.com/api/v1/hlhp/hub/ws?")
    assert "serviceKey=abc" in ws
    assert "seekerId=s1" in ws
    get_hlhp_settings.cache_clear()


@pytest.mark.anyio
async def test_bus_client_requires_hub_url(monkeypatch):
    monkeypatch.delenv("HLHP_HUB_URL", raising=False)
    from app.hlhp.core.bus_client import reset_bus_client
    from app.hlhp.core.hlhp_settings import HlhpSettings, get_hlhp_settings

    get_hlhp_settings.cache_clear()
    reset_bus_client()
    settings = HlhpSettings()
    assert not settings.hub_configured

    from app.hlhp.core.bus_client import HlhpBusClient, HlhpHubError

    client = HlhpBusClient()
    with pytest.raises(HlhpHubError) as exc:
        await client.publish("hlhp_goal_setup_v1", {"goalName": "Test", "ts": 1})
    assert exc.value.status_code == 503


@pytest.mark.anyio
async def test_bus_client_get_state_passes_format_raw(monkeypatch):
    monkeypatch.setenv("HLHP_HUB_URL", "https://hub.example/api/v1/hlhp/hub")
    from app.hlhp.core.bus_client import reset_bus_client
    from app.hlhp.core.hlhp_settings import get_hlhp_settings

    get_hlhp_settings.cache_clear()
    reset_bus_client()

    captured: dict = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "success": True,
                "data": {
                    "seekers": {
                        "s1": {"d1": {"hlhp_goal_setup_v1": {"goalName": "X", "ts": 1}}}
                    },
                    "chatPagination": {"hasMore": False},
                },
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, params=None, headers=None):
            captured["url"] = url
            captured["params"] = params
            captured["headers"] = headers
            return FakeResponse()

    monkeypatch.setattr("app.hlhp.core.bus_client.httpx.AsyncClient", FakeClient)

    from app.hlhp.core.bus_client import HlhpBusClient

    client = HlhpBusClient()
    state = await client.get_state(
        seeker_id="s1",
        doctor_id="d1",
        bearer_token="tok",
        chat_limit=50,
        chat_before_ts=99,
    )
    assert captured["params"]["format"] == "raw"
    assert captured["params"]["seekerId"] == "s1"
    assert captured["params"]["chatLimit"] == "50"
    assert captured["params"]["chatBeforeTs"] == "99"
    assert captured["headers"]["Authorization"] == "Bearer tok"
    assert get_bus_value(state, "hlhp_goal_setup_v1", seeker_id="s1", doctor_id="d1")[
        "goalName"
    ] == "X"
    assert state.get("chatPagination", {}).get("hasMore") is False


def test_payment_checkout_model_has_no_winback():
    from app.hlhp.models.hlhp_bus import HlhpPaymentCheckoutRequest

    fields = HlhpPaymentCheckoutRequest.model_fields
    assert "winback" not in fields
    body = HlhpPaymentCheckoutRequest(doctorId="d1", tncAccepted=True, name="A")
    assert body.doctor_id == "d1"
