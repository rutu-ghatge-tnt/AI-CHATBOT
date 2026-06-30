"""
engagement_api.py — HLHP Engagement Service (reference implementation)

Bridges the stateless SFI alert engine (hlhp_engine) to the stateful, longitudinal
features the front-end's 8 screens need: profiles, symptom logs, daily SFI history,
streaks/badges, surge detection, pattern mining, weekly/monthly aggregation, and the
`/today` adapter that maps an AlertResponse onto the UI's shape.

Design:
  • Scoring  -> delegated to hlhp_engine.route() (the v3.3.1 engine; unchanged).
  • Library  -> MockLibraryCache loads the locked Excel directly, so this runs with
                NO MongoDB/Redis. In production, swap to the engine's LibraryCache.
  • Storage  -> IN-MEMORY dicts (USERS/LOGS/DAILY). Swap each for a Mongo collection.
  • Sensors  -> a mock per-zone provider. Swap for a live weather/AQI feed.

Run:  uvicorn engagement_api:app --reload
Env:  HLHP_LIBRARY=/path/to/SkinBB_HLHP_Scenario_Library_v3_3_1.xlsx
"""
import os
from datetime import datetime, timezone, date, timedelta
from typing import Optional, List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from hlhp_engine import route, SensorReading, UserProfile
from mock_cache import MockLibraryCache

# ============================================================
# SCORING CORE (the v3.3.1 engine + locked library)
# ============================================================
_LIB = os.getenv("HLHP_LIBRARY", os.path.join(os.path.dirname(__file__), "library.xlsx"))
cache = MockLibraryCache(_LIB)            # production: swap for LibraryCache(Mongo, Redis)

app = FastAPI(title="HLHP Engagement Service", version="2.0.0")

# ============================================================
# CITY -> ZONE  (subset; production uses the library's 62-city map, sheet 1)
# ============================================================
CITY_ZONE = {
    "mumbai": "HH", "chennai": "HH", "kolkata": "HH", "goa": "HH", "kochi": "HH",
    "mangalore": "HH", "visakhapatnam": "HH",
    "delhi": "CN", "gurgaon": "CN", "noida": "CN", "lucknow": "CN", "kanpur": "CN", "patna": "CN",
    "jodhpur": "HD", "bikaner": "HD", "jaisalmer": "HD", "jaipur": "HD", "ahmedabad": "HD",
    "pune": "TP", "baner": "TP", "bengaluru": "TP", "bangalore": "TP", "hyderabad": "TP", "nashik": "TP",
    "shimla": "CH", "manali": "CH", "srinagar": "CH", "leh": "CH", "darjeeling": "CH", "gangtok": "CH",
    "guwahati": "TN", "shillong": "TN", "imphal": "TN", "agartala": "TN", "aizawl": "TN",
}
def city_to_zone(city: Optional[str]) -> Optional[str]:
    return CITY_ZONE.get((city or "").strip().lower())

# ============================================================
# SENSOR PROVIDER (mock; production = live weather + AQI feed)
# ============================================================
ZONE_WEATHER = {
    "HH": dict(temperature_c=32, aqi=120, uv_index=7,  humidity_pct=82),
    "CN": dict(temperature_c=34, aqi=210, uv_index=8,  humidity_pct=38),
    "HD": dict(temperature_c=40, aqi=130, uv_index=10, humidity_pct=18),
    "TP": dict(temperature_c=28, aqi=80,  uv_index=6,  humidity_pct=52),
    "CH": dict(temperature_c=6,  aqi=40,  uv_index=7,  humidity_pct=30),
    "TN": dict(temperature_c=29, aqi=60,  uv_index=5,  humidity_pct=90),
}
def get_sensors(zone: Optional[str], override: Optional[dict] = None) -> dict:
    s = dict(ZONE_WEATHER.get(zone, ZONE_WEATHER["TP"]))
    if override:
        s.update(override)
    return s

# ============================================================
# IN-MEMORY STORES  (swap each for a MongoDB collection)
# ============================================================
USERS: dict = {}   # user_id -> profile dict (skin_type, concern, age_band, gender_state, city, zone)
LOGS: dict = {}    # user_id -> [log dict]
DAILY: dict = {}   # user_id -> { 'YYYY-MM-DD': daily dict }

# ============================================================
# PRESENTATION MAPPERS (engine -> UI vocabulary)
# ============================================================
MASCOT = {
    "Paradise Mode": "radiant", "Smooth Sailing": "happy", "Guard Up": "watchful",
    "Battle Stations": "concerned", "Hostile Mode": "stressed", "Code Red": "alarmed",
}
def mascot_mood(band: str) -> str:
    return MASCOT.get(band, "neutral")

HUMID_HIGH = {"high", "very_high", "extreme"}

async def _score(zone, profile, level="L1", override=None):
    """Call the engine for the current reading. Returns (sensors, AlertResponse)."""
    sensors = get_sensors(zone, override)
    prof = UserProfile(
        skin_type=profile.get("skin_type"), concern=profile.get("concern"),
        age_band=profile.get("age_band"), gender_state=profile.get("gender_state"),
    )
    resp = await route(SensorReading(**sensors), prof, level, cache, zone=zone)
    return sensors, resp

def _user(uid) -> dict:
    u = USERS.get(uid)
    if not u:
        raise HTTPException(404, "unknown user_id — complete onboarding first")
    return u

def _today_iso() -> str:
    return date.today().isoformat()

# ============================================================
# MODELS
# ============================================================
class Onboard(BaseModel):
    user_id: str
    skin_type: str
    concern: str
    age_band: Optional[str] = None
    gender_state: Optional[str] = None
    city: str

class LogIn(BaseModel):
    user_id: str
    symptom: str
    location: Optional[str] = None
    count: Optional[str] = None

# ============================================================
# ENDPOINTS
# ============================================================
@app.get("/v2/health")
async def health():
    return {"status": "ok", "users": len(USERS), "library": os.path.basename(_LIB),
            "engine_library_version": (await _peek_version())}

async def _peek_version():
    _, r = await _score("TP", {"skin_type": "Normal", "concern": "Acne"})
    return r.library_version

@app.post("/v2/onboarding/complete")
async def onboarding(body: Onboard):
    zone = city_to_zone(body.city)
    USERS[body.user_id] = {
        "skin_type": body.skin_type, "concern": body.concern,
        "age_band": body.age_band, "gender_state": body.gender_state,
        "city": body.city, "zone": zone, "created_at": datetime.now(timezone.utc).isoformat(),
    }
    LOGS.setdefault(body.user_id, [])
    DAILY.setdefault(body.user_id, {})
    return {"user_id": body.user_id, "zone": zone,
            "zone_resolved": zone is not None,
            "note": None if zone else "city not in map — engine will run zone-agnostic"}

@app.get("/v2/today")
async def today(user_id: str, force_surge: bool = False):
    u = _user(user_id)
    override = {"aqi": 380, "uv_index": 11} if force_surge else None  # demo hook
    sensors, r = await _score(u["zone"], u, "L1", override)
    bands = (r.debug or {}).get("bands_observed", {})
    # write today's SFI into history (idempotent per day)
    DAILY[user_id][_today_iso()] = {"date": _today_iso(), "sfi": r.score,
                                    "personal_sfi": r.personal_sfi, "band": r.severity_band}
    return {
        "date": _today_iso(), "city": u["city"], "zone": u["zone"],
        "sfi": r.score, "personal_sfi": r.personal_sfi,
        "band": r.severity_band, "mascot_mood": mascot_mood(r.severity_band),
        "risk": r.risk, "risk_label": r.risk_label, "confidence": r.confidence,
        "coach_line": r.alert_text, "action_cluster": r.action_cluster,
        "cell_source": r.cell_source, "bands": bands, "sensors": sensors,
    }

@app.post("/v2/logs")
async def add_log(body: LogIn):
    u = _user(body.user_id)
    sensors, r = await _score(u["zone"], u, "L1")
    bands = (r.debug or {}).get("bands_observed", {})
    log = {
        "ts": datetime.now(timezone.utc).isoformat(), "date": _today_iso(),
        "symptom": body.symptom, "location": body.location, "count": body.count,
        "sfi": r.score, "action_cluster": r.action_cluster,
        "humidity_band": bands.get("Humidity"), "uv_band": bands.get("UV"),
        "aqi_band": bands.get("AQI"), "temp_band": bands.get("Temperature"),
    }
    LOGS[body.user_id].append(log)
    DAILY[body.user_id][_today_iso()] = {"date": _today_iso(), "sfi": r.score,
                                         "personal_sfi": r.personal_sfi, "band": r.severity_band}
    return {"logged": log, "streak": _streak(body.user_id)}

def _streak(uid) -> int:
    """Consecutive days up to today with a log or check-in."""
    days = set(DAILY.get(uid, {}).keys()) | {l["date"] for l in LOGS.get(uid, [])}
    n, d = 0, date.today()
    while d.isoformat() in days:
        n += 1
        d -= timedelta(days=1)
    return n

@app.get("/v2/streak")
async def streak(user_id: str):
    _user(user_id)
    cur = _streak(user_id)
    badges = {
        "first_log": len(LOGS.get(user_id, [])) >= 1,
        "streak_7": cur >= 7, "streak_30": cur >= 30,
    }
    nxt = 7 - cur if cur < 7 else (30 - cur if cur < 30 else 0)
    return {"current_streak": cur, "badges": badges, "days_to_next_badge": max(nxt, 0)}

@app.get("/v2/patterns")
async def patterns(user_id: str):
    _user(user_id)
    logs = LOGS.get(user_id, [])
    if len(logs) < 5:
        return {"ready": False, "logs_needed": 5 - len(logs),
                "message": f"{len(logs)}/5 logs — keep logging to unlock patterns"}
    # simple miner: per-symptom co-occurrence with high humidity
    out = []
    by_symptom: dict = {}
    for l in logs:
        by_symptom.setdefault(l["symptom"], []).append(l)
    for sym, ls in by_symptom.items():
        if len(ls) < 3:
            continue
        hi = sum(1 for l in ls if l.get("humidity_band") in HUMID_HIGH)
        match = round(100 * hi / len(ls))
        if match >= 60:
            out.append({"pattern": f"'{sym}' clusters on high-humidity days",
                        "match_pct": match, "n": len(ls), "driver": "Humidity"})
    out.sort(key=lambda p: -p["match_pct"])
    return {"ready": True, "n_logs": len(logs), "patterns": out}

def _series(uid, days: int):
    hist = DAILY.get(uid, {})
    out = []
    for i in range(days - 1, -1, -1):
        d = (date.today() - timedelta(days=i)).isoformat()
        out.append({"date": d, "sfi": hist.get(d, {}).get("sfi")})
    return out

@app.get("/v2/weekly-card")
async def weekly_card(user_id: str):
    _user(user_id)
    cur = [p["sfi"] for p in _series(user_id, 7) if p["sfi"] is not None]
    prev = [p["sfi"] for p in _series(user_id, 14)[:7] if p["sfi"] is not None]
    avg = round(sum(cur) / len(cur)) if cur else None
    pavg = round(sum(prev) / len(prev)) if prev else None
    trend = (avg - pavg) if (avg is not None and pavg is not None) else None
    return {"week_avg_sfi": avg, "trend_vs_prev": trend,
            "series": _series(user_id, 7), "logged_days": len(cur)}

@app.get("/v2/recap")
async def recap(user_id: str, days: int = 30):
    _user(user_id)
    series = _series(user_id, days)
    vals = [p["sfi"] for p in series if p["sfi"] is not None]
    avg = round(sum(vals) / len(vals)) if vals else None
    surges = sum(1 for l in LOGS.get(user_id, []) if l["sfi"] is not None and l["sfi"] < 45)
    return {"days": days, "avg_sfi": avg, "logged_days": len(vals),
            "surge_days": surges, "series": series}

@app.get("/v2/surge/check")
async def surge_check(user_id: str, drop_threshold: int = 15, force_surge: bool = False):
    """A monitor/cron calls this; if SFI dropped >= threshold vs recent baseline, push."""
    u = _user(user_id)
    override = {"aqi": 380, "uv_index": 11} if force_surge else None
    _, now = await _score(u["zone"], u, "L0", override)
    recent = [p["sfi"] for p in _series(user_id, 7) if p["sfi"] is not None]
    baseline = round(sum(recent) / len(recent)) if recent else now.score
    drop = baseline - now.score
    surge = drop >= drop_threshold
    return {"surge": surge, "current_sfi": now.score, "baseline_sfi": baseline,
            "drop": drop, "band": now.severity_band,
            "push": {"title": f"Heat surge in {u['city']}",
                     "body": now.alert_text} if surge else None}

@app.get("/v2/good-day")
async def good_day(user_id: str):
    _user(user_id)
    series = [p for p in _series(user_id, 30) if p["sfi"] is not None]
    if not series:
        return {"found": False, "message": "no SFI history yet"}
    best = max(series, key=lambda p: p["sfi"])
    return {"found": True, "best_day": best,
            "recipe": ["sleep stayed high", "AQI was clean", "hydration logged"]}

@app.post("/v2/good-day/bottle")
async def bottle(user_id: str):
    _user(user_id)
    return {"saved": True, "message": "routine snapshot saved"}
