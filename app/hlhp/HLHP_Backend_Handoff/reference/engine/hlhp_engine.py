"""
hlhp_engine.py
HLHP Alert Engine — runtime routing logic.

Stack: FastAPI + MongoDB (motor for async) + Redis (aiocache)
Latency target: <50ms after cache warmup.

Architecture:
  1. Sensors come in (or are fetched from upstream weather/AQI APIs)
  2. Score computed, override rules applied
  3. Per-factor cells looked up (Redis cache → MongoDB fallback)
  4. Dominant factor identified
  5. Compound match attempted (with 1-band-step tolerance)
  6. Alert frame chosen
  7. Age + Gender modifiers composed
  8. Confidence-aware tone modulation
  9. Render and return
"""
import json
import os
from typing import Optional, Literal
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
# motor (MongoDB) and redis are imported lazily inside startup() so this module can
# be imported as a library (engagement service, tests, tooling) without those
# drivers installed. They are only required to run the live HTTP API.


# ============================================================
# CONFIG — locked routing decisions from Phase 5
# ============================================================
LIBRARY_VERSION = "1.0.0"
COMPOUND_TOLERANCE = 1                # bands within 1 step still considered match
SECONDARY_RISK_THRESHOLD = 3          # surface non-dominant factors at risk >= 3
MAX_SECONDARY_MENTIONS = 2
FACTOR_TIEBREAKER = ["UV", "AQI", "Temperature", "Humidity"]  # priority on score-tie

# Diagnostic `debug` payload is dev-only. The HTTP layer strips it from responses
# unless this is enabled. route() still computes it (tests read resp.debug directly).
DEBUG_RESPONSES = os.getenv("HLHP_DEBUG_RESPONSES", "false").lower() in ("1", "true", "yes")

# Personal SFI — per-concern weights applied to the SAME four environmental
# sub-scores (does not add new factors). Illustrative starting point — tune
# clinically. Age/gender stay on the risk axis, not here.
CONCERN_WEIGHTS = {
    # Pigmentation: UV dominant; heat/IR-A and pollution (PIH) secondary; humidity minimal.
    "Melasma":                 {"Temperature": 1.0, "AQI": 1.0, "UV": 2.0, "Humidity": 0.5},
    "Uneven Skin Tone / Tan":  {"Temperature": 1.0, "AQI": 1.0, "UV": 2.0, "Humidity": 0.5},
    # Sebum/pore: humidity + pollution lead.
    "Acne":                    {"Temperature": 0.5, "AQI": 1.5, "UV": 0.5, "Humidity": 1.5},
    "Oily Skin":               {"Temperature": 0.5, "AQI": 1.5, "UV": 0.5, "Humidity": 1.5},
    # Barrier/water-loss: humidity leads temperature.
    "Dryness":                 {"Temperature": 1.0, "AQI": 0.5, "UV": 0.5, "Humidity": 2.0},
    "Eczema":                  {"Temperature": 1.0, "AQI": 1.0, "UV": 0.5, "Humidity": 2.0},
}

# Band ordering for distance/tolerance calculations
BAND_ORDER = {
    "Temperature": ["extreme_cold","cold","cool","optimal","warm","hot","extreme_heat"],
    "AQI":         ["good","satisfactory","moderate","poor","very_poor","severe"],
    "UV":          ["low","moderate","high","very_high","extreme"],
    "Humidity":    ["critical_low","very_low","low","optimal","high","very_high","extreme"],
}

# Severity bands from total score
SEVERITY_BANDS = [
    (75, 100, "Paradise Mode"),
    (60, 74,  "Smooth Sailing"),
    (45, 59,  "Guard Up"),
    (30, 44,  "Battle Stations"),
    (15, 29,  "Hostile Mode"),
    (0,  14,  "Code Red"),
]


# ============================================================
# DATA MODELS
# ============================================================
class SensorReading(BaseModel):
    temperature_c: float
    aqi: int
    uv_index: float
    humidity_pct: float


class UserProfile(BaseModel):
    user_id: Optional[str] = None
    skin_type: Optional[Literal["Normal","Dry","Oily","Combination","Sensitive"]] = None
    concern: Optional[Literal[
        "Dryness","Eczema","Oily Skin","Acne","Uneven Skin Tone / Tan","Melasma"
    ]] = None
    age_band: Optional[Literal[
        "Pediatric","Adolescent","Young Adult","Adult","Mature","Senior"
    ]] = None
    gender_state: Optional[Literal[
        "Male","Female","Female + Pregnancy","Female + Lactation",
        "Female + Perimenopause","Female + Menopause"
    ]] = None


class AlertRequest(BaseModel):
    profile: UserProfile = Field(default_factory=UserProfile)
    sensors: SensorReading
    alert_level: Literal["L0","L1","L2"] = "L1"
    # Climatic zone of the reading (HH/CN/HD/TP/CH/TN). Usually derived upstream
    # from the same location as the sensors. Optional — None = zone-agnostic.
    zone: Optional[str] = None


class AlertResponse(BaseModel):
    score: int                            # Environmental SFI (0-100)
    personal_sfi: Optional[int] = None    # profile-weighted SFI for the user's concern
    severity_band: str
    risk: int
    risk_label: str
    confidence: str
    alert_text: str
    action_cluster: str
    cell_source: str   # "compound" | "single_factor_dominant" | "guest"
    library_version: str
    debug: Optional[dict] = None   # diagnostic, surface only in dev


# ============================================================
# BAND CLASSIFICATION — sensor reading → band_key + points
# ============================================================
def classify_temperature(c):
    if c < 5:   return ("extreme_cold", 0)
    if c < 15:  return ("cold", 5)
    if c < 20:  return ("cool", 12)
    if c < 28:  return ("optimal", 25)
    if c < 35:  return ("warm", 12)
    if c < 43:  return ("hot", 5)
    return ("extreme_heat", 0)

def classify_aqi(a):
    if a <= 50:  return ("good", 25)
    if a <= 100: return ("satisfactory", 18)
    if a <= 200: return ("moderate", 10)
    if a <= 300: return ("poor", 5)
    if a <= 400: return ("very_poor", 2)
    return ("severe", 0)

def classify_uv(u):
    if u <= 2:  return ("low", 25)
    if u <= 5:  return ("moderate", 18)
    if u <= 7:  return ("high", 12)
    if u <= 10: return ("very_high", 2)   # 8-10: heavy skin penalty (UV is a top stressor)
    return ("extreme", 0)

def classify_humidity(h):
    if h < 10:  return ("critical_low", 0)
    if h < 20:  return ("very_low", 5)
    if h < 40:  return ("low", 12)        # comfortable band narrowed to 40-60% (barrier/TEWL)
    if h <= 60: return ("optimal", 25)
    if h < 80:  return ("high", 12)
    if h < 90:  return ("very_high", 5)
    return ("extreme", 0)


# ============================================================
# CACHE LAYER — Redis with MongoDB fallback
# ============================================================
class LibraryCache:
    """Loads the library into Redis on startup. ~2 MB total."""

    def __init__(self, mongo_db, redis_client):
        self.db = mongo_db
        self.redis = redis_client
        self.warmed = False

    async def warm(self):
        """Hydrate Redis from MongoDB. Run once on app startup."""
        async for cell in self.db.scenario_cells.find({"library_version": LIBRARY_VERSION}):
            key = f"cell:{LIBRARY_VERSION}:{cell['factor']}:{cell['band_key']}:{cell['skin_type']}:{cell['concern']}"
            await self.redis.set(key, json.dumps(cell, default=str))

        async for cell in self.db.compound_cells.find({"library_version": LIBRARY_VERSION}):
            key = f"compound:{LIBRARY_VERSION}:{cell['scenario_id']}:{cell['skin_type']}:{cell['concern']}"
            await self.redis.set(key, json.dumps(cell, default=str))

        async for cell in self.db.guest_cells.find({"library_version": LIBRARY_VERSION}):
            bk = cell.get("band_key") or "none"
            key = f"guest:{LIBRARY_VERSION}:{cell['cell_type']}:{cell['factor_or_scenario']}:{bk}:{cell['skin_type']}"
            await self.redis.set(key, json.dumps(cell, default=str))

        async for s in self.db.compound_scenarios.find({"library_version": LIBRARY_VERSION}):
            key = f"scenario:{LIBRARY_VERSION}:{s['_id']}"
            await self.redis.set(key, json.dumps(s, default=str))

        # Modifiers stay small enough to load into a Python dict
        self.age_mods = {}
        async for m in self.db.age_modifiers.find({"library_version": LIBRARY_VERSION}):
            self.age_mods[(m["age_band"], m["concern"])] = m

        self.gender_mods = {}
        async for m in self.db.gender_modifiers.find({"library_version": LIBRARY_VERSION}):
            self.gender_mods[(m["state"], m["concern"])] = m

        self.scenarios = {}
        async for s in self.db.compound_scenarios.find({"library_version": LIBRARY_VERSION}):
            self.scenarios[s["_id"]] = s

        self.warmed = True

    async def get_cell(self, factor, band_key, skin_type, concern):
        key = f"cell:{LIBRARY_VERSION}:{factor}:{band_key}:{skin_type}:{concern}"
        raw = await self.redis.get(key)
        if raw:
            return json.loads(raw)
        # fallback to mongo if cache miss
        return await self.db.scenario_cells.find_one({
            "library_version": LIBRARY_VERSION,
            "factor": factor, "band_key": band_key,
            "skin_type": skin_type, "concern": concern,
        })

    async def get_compound_cell(self, scenario_id, skin_type, concern):
        key = f"compound:{LIBRARY_VERSION}:{scenario_id}:{skin_type}:{concern}"
        raw = await self.redis.get(key)
        if raw:
            return json.loads(raw)
        return await self.db.compound_cells.find_one({
            "library_version": LIBRARY_VERSION,
            "scenario_id": scenario_id,
            "skin_type": skin_type, "concern": concern,
        })

    async def get_guest_cell(self, cell_type, factor_or_scenario, skin_type, band_key=None):
        bk = band_key or "none"
        key = f"guest:{LIBRARY_VERSION}:{cell_type}:{factor_or_scenario}:{bk}:{skin_type}"
        raw = await self.redis.get(key)
        if raw:
            return json.loads(raw)
        query = {
            "library_version": LIBRARY_VERSION,
            "cell_type": cell_type,
            "factor_or_scenario": factor_or_scenario,
            "skin_type": skin_type,
        }
        if cell_type == "single_factor" and band_key:
            query["band_key"] = band_key
        return await self.db.guest_cells.find_one(query)


# ============================================================
# ROUTING LOGIC — the 7-step decision flow
# ============================================================
def severity_band(score):
    for lo, hi, name in SEVERITY_BANDS:
        if lo <= score <= hi:
            return name
    return "Unknown"


def personal_sfi(points, concern):
    """Profile-weighted Skin Friendliness Index (0-100) for a concern.
    Re-weights the same four sub-scores; returns None when the concern has no
    weight profile (caller then just uses the environmental SFI/score)."""
    w = CONCERN_WEIGHTS.get(concern)
    if not w:
        return None
    num = sum(w[f] * points[f] for f in points)
    den = 25 * sum(w.values())
    return round(100 * num / den)


def band_distance(factor, band_a, band_b):
    """How many steps apart are two bands of the same factor?"""
    order = BAND_ORDER.get(factor, [])
    if band_a not in order or band_b not in order:
        return 999
    return abs(order.index(band_a) - order.index(band_b))


def find_compound_match(observed_bands, scenarios, dominant_factor, tolerance=1, zone=None):
    """Search the named scenarios for a near-match. Returns (scenario, distance) or (None, None).

    Zone-aware: when `zone` is given, first restrict the search to scenarios whose
    `zones` include that zone (or are zone-agnostic, "any"). Only if no in-zone
    scenario matches do we fall back to the full set — so an inland scenario can't
    win a coastal reading just because its weather bands happen to sit closer.
    """
    def _zone_ok(s):
        z = s.get("zones") or []
        return (zone in z) or ("any" in z)

    # zone given -> in-zone pass, then fall back to all; zone None -> single pass
    for restrict_to_zone in ((True, False) if zone else (False,)):
        best = None
        best_dist = 999
        for sid, s in scenarios.items():
            # Constraint: dominant factor must be in the scenario's dominant_drivers
            if dominant_factor not in s.get("dominant_drivers", []):
                continue
            # Zone constraint (first pass only)
            if restrict_to_zone and not _zone_ok(s):
                continue
            # Count the scenario's concrete (non-"any") bands. Most scenarios pin all
            # four; low-specificity indoor scenarios (e.g. C20 AC Transition Stress)
            # intentionally leave UV/AQI as "any". Require EVERY concrete band to match
            # within tolerance, with a floor of 2, so such scenarios are reachable
            # without letting a single-band coincidence fire a match.
            concrete_bands = [b for b in s["bands"].values() if b and b != "any"]
            min_required = max(2, min(3, len(concrete_bands)))
            total_dist = 0
            match_count = 0
            valid = True
            for factor, observed_band in observed_bands.items():
                scen_band = s["bands"].get(factor)
                if not scen_band or scen_band == "any":
                    continue
                d = band_distance(factor, scen_band, observed_band)
                if d > tolerance:
                    valid = False
                    break
                total_dist += d
                match_count += 1
            if (valid and match_count == len(concrete_bands)
                    and match_count >= min_required and total_dist < best_dist):
                best = s
                best_dist = total_dist
        if best is not None:
            return best, best_dist
    return None, None


def apply_modifiers(base_risk, addenda, age_mods, gender_mods, profile):
    """Apply age + gender/life-stage deltas. Returns (new_risk, addenda_list, evidence_anchors)."""
    risk = base_risk
    evidence = []

    if profile.age_band and profile.concern:
        mod = age_mods.get((profile.age_band, profile.concern))
        if mod:
            risk += mod.get("risk_delta", 0)
            addenda.append(f"[Age: {profile.age_band}] {mod['addendum']}")
            evidence.append(mod.get("evidence", ""))

    if profile.gender_state and profile.concern:
        mod = gender_mods.get((profile.gender_state, profile.concern))
        if mod:
            risk += mod.get("risk_delta", 0)
            addenda.append(f"[{profile.gender_state}] {mod['addendum']}")
            evidence.append(mod.get("evidence", ""))

    return max(0, min(5, risk)), addenda, evidence


def modulate_tone(text, confidence):
    """Confidence-aware tone modulation (the layer from the engagement discussion)."""
    if confidence == "INFERRED":
        return f"{text}\n\n(Research on this exact pattern is still emerging — let us know what you noticed.)"
    return text


async def route(sensors: SensorReading, profile: UserProfile, alert_level: str,
                cache: LibraryCache, zone: Optional[str] = None) -> AlertResponse:
    """Main decision flow. `zone` (optional) is the user's climatic zone code
    (e.g. HH, CN, HD, TP, CH, TN); when supplied, compound matching prefers
    scenarios meant for that zone before falling back to zone-agnostic search."""

    # Step 1 — classify sensors and compute score
    bands = {
        "Temperature": classify_temperature(sensors.temperature_c),
        "AQI":         classify_aqi(sensors.aqi),
        "UV":          classify_uv(sensors.uv_index),
        "Humidity":    classify_humidity(sensors.humidity_pct),
    }
    points = {f: pts for f, (_, pts) in bands.items()}
    score = sum(points.values())
    psfi = personal_sfi(points, profile.concern)   # profile-weighted SFI (None if no concern)

    # Override rule: any factor at 0 → escalate severity band by 1 tier
    zero_factors = [f for f, pts in points.items() if pts == 0]
    severity = severity_band(score)
    if zero_factors:
        # crude escalation: drop to the next-worse named band
        idx = next((i for i, (lo, hi, name) in enumerate(SEVERITY_BANDS) if name == severity), -1)
        if idx >= 0 and idx + 1 < len(SEVERITY_BANDS):
            severity = SEVERITY_BANDS[idx + 1][2]

    # Zone-aware routing: ignore unrecognised zone codes so a typo can't silently
    # suppress all in-zone matches (falls back to zone-agnostic behaviour).
    if zone is not None:
        known_zones = {z for s in cache.scenarios.values()
                       for z in s.get("zones", []) if z != "any"}
        if zone not in known_zones:
            zone = None

    # Step 2 — determine profile completeness
    has_skin_type = profile.skin_type is not None
    has_concern   = profile.concern is not None

    # GUEST PATH — no concern selected
    if not has_concern:
        skin_type = profile.skin_type or "Normal"

        # Try compound match using guest fallback
        observed = {f: bk for f, (bk, _) in bands.items()}
        # Use the same dominant-factor tiebreaker as the full-profile path so a
        # guest and a logged-in user resolve identical weather to the same factor.
        min_score = min(points.values())
        candidates = [f for f, p in points.items() if p == min_score]
        dominant_factor = sorted(candidates, key=lambda f: FACTOR_TIEBREAKER.index(f))[0]
        compound, dist = find_compound_match(observed, cache.scenarios, dominant_factor, COMPOUND_TOLERANCE, zone=zone)

        if compound:
            cell = await cache.get_guest_cell("compound", compound["name"], skin_type)
            source = "guest_compound"
        else:
            band_key, _ = bands[dominant_factor]
            cell = await cache.get_guest_cell(
                "single_factor", dominant_factor, skin_type, band_key=band_key
            )
            source = "guest_single"

        if not cell:
            raise HTTPException(status_code=500, detail="Guest cell not found in library")

        return AlertResponse(
            score=score,
            personal_sfi=psfi,
            severity_band=severity,
            risk=cell["risk"],
            risk_label=cell["risk_label"],
            confidence="N/A (guest)",
            alert_text=cell["alerts"][alert_level],
            action_cluster=cell["action_cluster"],
            cell_source=source,
            library_version=LIBRARY_VERSION,
        )

    # FULL-PROFILE PATH
    # Step 3 — per-factor cell lookup
    cells = {}
    for factor, (band_key, _) in bands.items():
        c = await cache.get_cell(factor, band_key, profile.skin_type, profile.concern)
        if c:
            cells[factor] = c

    # Step 4 — dominant factor (lowest score; tiebreaker by UV>AQI>Temp>Humidity)
    min_score = min(points.values())
    candidates = [f for f, p in points.items() if p == min_score]
    dominant_factor = sorted(candidates, key=lambda f: FACTOR_TIEBREAKER.index(f))[0]

    # Step 5 — compound match search
    observed = {f: bk for f, (bk, _) in bands.items()}
    compound, dist = find_compound_match(observed, cache.scenarios, dominant_factor, COMPOUND_TOLERANCE, zone=zone)

    # Step 6 — pick frame
    if compound:
        primary = await cache.get_compound_cell(compound["_id"], profile.skin_type, profile.concern)
        source = "compound"
    else:
        primary = cells.get(dominant_factor)
        source = "single_factor_dominant"

    if not primary:
        raise HTTPException(status_code=500, detail=f"Primary cell not found (factor={dominant_factor})")

    # Step 7 — secondary modifiers (factors at risk >= threshold, excluding dominant)
    secondaries = []
    if source == "single_factor_dominant":
        for f, c in cells.items():
            if f != dominant_factor and c["risk"] >= SECONDARY_RISK_THRESHOLD:
                secondaries.append(c)
        secondaries.sort(key=lambda c: c["risk"], reverse=True)
        secondaries = secondaries[:MAX_SECONDARY_MENTIONS]

    # Step 8 — apply age + gender modifiers
    base_risk = primary["risk"]
    addenda = []
    final_risk, addenda, evidence_extra = apply_modifiers(
        base_risk, addenda, cache.age_mods, cache.gender_mods, profile
    )

    # Step 9 — compose alert text
    alert_text = primary["alerts"][alert_level]

    if secondaries and alert_level in ("L1", "L2"):
        sec_names = [f"{s['factor']} {s['band_label']}" for s in secondaries]
        alert_text += f"\n\nAlso stacking: {', '.join(sec_names)}."

    if addenda and alert_level == "L2":
        alert_text += "\n\n" + "\n".join(addenda)

    alert_text = modulate_tone(alert_text, primary["confidence"])

    return AlertResponse(
        score=score,
        personal_sfi=psfi,
        severity_band=severity,
        risk=final_risk,
        risk_label=["Negligible","Low","Moderate","High","Severe","Critical"][final_risk],
        confidence=primary["confidence"],
        alert_text=alert_text,
        action_cluster=primary["action_cluster"],
        cell_source=source,
        library_version=LIBRARY_VERSION,
        debug={
            "dominant_factor": dominant_factor,
            "zone": zone,
            "bands_observed": observed,
            "compound_id": compound["_id"] if compound else None,
            "compound_distance": dist if compound else None,
            "base_risk": base_risk,
            "modifier_evidence": evidence_extra,
        },
    )


# ============================================================
# FASTAPI APP
# ============================================================
app = FastAPI(title="SkinBB HLHP Alert Engine", version=LIBRARY_VERSION)

# Wire these to your environment
mongo_client = None
redis_client = None
cache = None

@app.on_event("startup")
async def startup():
    global mongo_client, redis_client, cache
    from motor.motor_asyncio import AsyncIOMotorClient
    import redis.asyncio as redis_lib
    mongo_client = AsyncIOMotorClient(os.getenv("MONGO_URL", "mongodb://localhost:27017"))
    redis_client = redis_lib.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
    cache = LibraryCache(mongo_client.skinbb_hlhp, redis_client)
    await cache.warm()
    print(f"Library v{LIBRARY_VERSION} hydrated into Redis cache.")


@app.post("/v1/alert", response_model=AlertResponse, response_model_exclude_none=True)
async def get_alert(req: AlertRequest):
    if cache is None or not cache.warmed:
        raise HTTPException(status_code=503, detail="Library cache not warmed")
    resp = await route(req.sensors, req.profile, req.alert_level, cache, zone=req.zone)
    # Strip internal diagnostics from production responses unless explicitly enabled.
    if not DEBUG_RESPONSES:
        resp.debug = None
    return resp


@app.get("/v1/health")
async def health():
    return {
        "status": "ok",
        "library_version": LIBRARY_VERSION,
        "cache_warmed": cache is not None and cache.warmed,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# Run with: uvicorn hlhp_engine:app --reload
