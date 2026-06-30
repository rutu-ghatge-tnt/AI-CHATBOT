"""
test_engagement_api.py — exercises the engagement service end-to-end via TestClient.
Scoring is real (the v3.3.1 engine + locked library); stores are in-memory.
"""
from fastapi.testclient import TestClient
import engagement_api as svc

client = TestClient(svc.app)


def _onboard(uid, city="Pune", concern="Acne", skin="Oily", age="Adult", gender="Female"):
    r = client.post("/v2/onboarding/complete", json={
        "user_id": uid, "skin_type": skin, "concern": concern,
        "age_band": age, "gender_state": gender, "city": city})
    assert r.status_code == 200
    return r.json()


def test_onboarding_resolves_city_to_zone():
    assert _onboard("u_mum", city="Mumbai")["zone"] == "HH"
    assert _onboard("u_pune", city="Pune")["zone"] == "TP"


def test_today_has_full_ui_shape():
    _onboard("u_today", city="Pune", concern="Melasma", skin="Sensitive")
    d = client.get("/v2/today", params={"user_id": "u_today"}).json()
    for k in ["sfi", "personal_sfi", "band", "mascot_mood", "coach_line",
              "action_cluster", "risk", "risk_label", "confidence", "zone", "sensors"]:
        assert k in d, f"missing {k}"
    assert 0 <= d["sfi"] <= 100
    assert d["zone"] == "TP"
    assert d["mascot_mood"] in {"radiant", "happy", "watchful", "concerned", "stressed", "alarmed", "neutral"}


def test_personal_sfi_differs_by_concern_same_place():
    _onboard("u_mel", city="Goa", concern="Melasma", skin="Sensitive")
    _onboard("u_acn", city="Goa", concern="Acne", skin="Oily")
    mel = client.get("/v2/today", params={"user_id": "u_mel"}).json()
    acn = client.get("/v2/today", params={"user_id": "u_acn"}).json()
    assert mel["sfi"] == acn["sfi"]                 # same environment
    assert mel["personal_sfi"] != acn["personal_sfi"]  # different person-fit


def test_log_then_streak():
    _onboard("u_log", city="Pune")
    r = client.post("/v2/logs", json={"user_id": "u_log", "symptom": "breakout",
                                      "location": "cheeks", "count": "2-3"})
    assert r.status_code == 200
    assert r.json()["streak"] >= 1
    s = client.get("/v2/streak", params={"user_id": "u_log"}).json()
    assert s["current_streak"] >= 1 and s["badges"]["first_log"] is True


def test_patterns_progress_then_ready():
    _onboard("u_pat", city="Mumbai", concern="Eczema", skin="Sensitive")
    assert client.get("/v2/patterns", params={"user_id": "u_pat"}).json()["ready"] is False
    for _ in range(6):
        client.post("/v2/logs", json={"user_id": "u_pat", "symptom": "itchy"})
    p = client.get("/v2/patterns", params={"user_id": "u_pat"}).json()
    assert p["ready"] is True
    assert any(pat["driver"] == "Humidity" for pat in p["patterns"])  # Mumbai = humid


def test_surge_force_lowers_sfi():
    _onboard("u_surge", city="Mumbai")
    client.get("/v2/today", params={"user_id": "u_surge"})  # seed baseline
    d = client.get("/v2/surge/check", params={"user_id": "u_surge", "force_surge": True}).json()
    assert d["current_sfi"] <= d["baseline_sfi"]


def test_weekly_card_and_recap_run():
    _onboard("u_agg", city="Pune")
    client.get("/v2/today", params={"user_id": "u_agg"})
    wc = client.get("/v2/weekly-card", params={"user_id": "u_agg"}).json()
    assert "week_avg_sfi" in wc and wc["logged_days"] >= 1
    rc = client.get("/v2/recap", params={"user_id": "u_agg"}).json()
    assert rc["days"] == 30 and rc["avg_sfi"] is not None


def test_unknown_user_404():
    assert client.get("/v2/today", params={"user_id": "ghost"}).status_code == 404


def test_health_reports_library_version():
    h = client.get("/v2/health").json()
    assert h["status"] == "ok"
    assert h["engine_library_version"]  # comes from the engine/AlertResponse
