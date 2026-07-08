"""
hlhp_patterns_engine.py
=======================
Reference backend for the HLHP **Patterns** tab.

PURPOSE (read me first)
-----------------------
This is a *runnable reference implementation* for the backend developer. It is
framework-agnostic (pure Python stdlib) with an OPTIONAL thin Flask layer at the
bottom. It encodes the signed-off rules from:
    - patterns-tab-rules-v1.md          (product rules + scenarios)
    - patterns-implementation-spec-v1.md (build contract)

It exists because in the current front-end (`hlhp-interactive.html`) the Patterns
tab is FAKE: `animSP()` renders hardcoded arrays (TL/WK/HR and a fixed 83%).
Nothing is persisted, there is no user id, and `state.logCount` only lives in the
browser. This file provides the real thing the tab should consume.

HOW THE FRONT-END IS WIRED TODAY (verified from hlhp-interactive.html)
---------------------------------------------------------------------
1. The evidence library `EV` is loaded once via:
        fetch("hlhp-evidence.json") -> EV = json  (fallback: FALLBACK_EV)
   `EV.master` is a dict keyed:
        slug(factor) | band_key | slug(skin) | slug(concern)
   -> cell = { l0, l1, l2, action, zones, evidence, pmids[], confidence, factor, band }
   Other EV tables: bands, zones, city_zone, zone_weather, compound_cells,
   gender_rules, age_rules, time_overlay, guest_mode, nuggets, nutrition, lifestyle.

2. `state` (browser-only): { city, skin, concern, age, life, mode, logCount, ... }.
   `slug(s)` = lowercase, non-alphanumerics -> "_", trim underscores. WE REUSE IT.

3. `TREND` (30-day SFI history) and `DAILY_LOGS` are generated client-side with a
   seeded RNG (`buildHistory`). They are placeholders for what THIS engine returns.

WHAT THIS FILE ADDS (the missing backend)
-----------------------------------------
    * Persistence-ready data models: DailyLog, EnvDay, PatternState, Pattern.
    * Log-day counting + rolling-window evaluation.
    * Unlock gates: 30-day floor from FIRST LOG, 25/30 log-days, 5 exposure days.
    * Post-unlock decay: ACTIVE / FADING / PAUSED + 3-of-5 reactivation.
    * Deterministic detection: exposure, hits, lift, label, promote/demote.
    * The exact JSON payloads the front-end needs, INCLUDING the v4
      correlation-chart series (chart:[{lvl,sym}]) and 1-5 confidence dots.
    * AI-narration contract: packet builder + numeral validator + template fallback.
    * A explicit OLD->NEW mapping so the front-end dev knows what to replace.

The AI NEVER detects patterns. It only narrates numbers this engine computed.
See build_narration_packet() / validate_narration().
"""

from __future__ import annotations

import re
import json
import math
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from typing import Optional


# ============================================================================
# 0. CONFIG — server-side, mirrors patterns-implementation-spec-v1.md §2
#    (Do NOT hardcode these in the client. Serve them or read from config.)
# ============================================================================
class Config:
    WINDOW_DAYS = 30            # rolling window length
    UNLOCK_HARD_FLOOR_DAYS = 30  # min days since FIRST LOG (non-negotiable)
    UNLOCK_LOG_DAYS = 25        # log-days required within the rolling window
    EXPOSURE_MIN_DAYS = 5       # adverse-driver days (any driver) that are logged

    PROMOTE_MIN_EXPOSURE = 5    # per-pattern E required to display
    PROMOTE_MIN_LIFT = 1.5
    DEMOTE_LIFT = 1.2           # sustained below this for DEMOTE_DAYS -> Emerging
    DEMOTE_DAYS = 14

    LABEL_HIGH_E, LABEL_HIGH_LIFT = 10, 2.0
    LABEL_MOD_E, LABEL_MOD_LIFT = 7, 1.5

    ACTIVE_MIN_LOG_DAYS = 20    # in rolling window
    FADING_MIN_LOG_DAYS = 12
    REACT_LOGS, REACT_WINDOW = 3, 5   # 3 log-days within 5 calendar days

    MAX_DISPLAYED = 3           # top N patterns; rest -> "emerging"
    BASELINE_FLOOR = 0.05
    SYMPTOM_LAG_HOURS = 24
    CHART_DAYS = 14             # days shown in the v4 correlation chart


# The four environmental drivers + the symptom vocabulary, matching the client.
DRIVERS = ["temp", "uv", "humidity", "aqi"]           # DRIVER_KEYS values in JS
SYMPTOMS = ["dry", "oily", "dull", "breakout", "spots"]  # LOG_CHIPS keys (minus 'normal')

# Adverse bands for exposure counting — synced with app.hlhp.core.bands vocabulary.
# Production code may override via band_bridge.ADVERSE_BANDS at import time.
try:
    from app.hlhp.patterns.band_bridge import ADVERSE_BANDS as _BB_ADVERSE
    ADVERSE_BANDS = _BB_ADVERSE
except ImportError:
    ADVERSE_BANDS = {
        "temp": {"warm", "hot", "very_hot"},
        "uv": {"high", "very_high", "extreme"},
        "humidity": {"high", "very_high"},
        "aqi": {"poor", "very_poor", "severe"},
    }

# Plain-language + colour metadata for each driver, so the engine can emit a
# fully-formed card the v4 UI can render without extra lookups.
DRIVER_UI = {
    "humidity": {"label": "Sticky, humid days", "leg": "humidity",     "w_icon": "ti-droplet",         "color_var": "--drv-humidity"},
    "aqi":      {"label": "Dusty mornings",     "leg": "morning dust", "w_icon": "ti-wind",            "color_var": "--drv-aqi"},
    "uv":       {"label": "High-UV days",       "leg": "UV",           "w_icon": "ti-sun-high",        "color_var": "--drv-uv"},
    "temp":     {"label": "Hot days",           "leg": "heat",         "w_icon": "ti-temperature-sun", "color_var": "--drv-temp"},
}
SYMPTOM_UI = {
    "breakout": {"label": "Breakouts", "leg": "breakouts", "s_icon": "ti-mood-sad"},
    "spots":    {"label": "Spots",     "leg": "spots",     "s_icon": "ti-point"},
    "dull":     {"label": "Dull skin", "leg": "dull days", "s_icon": "ti-circle-half-2"},
    "dry":      {"label": "Dryness",   "leg": "dry days",  "s_icon": "ti-droplet-off"},
    "oily":     {"label": "Oiliness",  "leg": "oily days", "s_icon": "ti-oil"},
}


# ============================================================================
# 1. SHARED HELPERS — reuse the client's slug() so keys line up with EV.master
# ============================================================================
def slug(s: str) -> str:
    """Identical to the JS slug(): lowercase, non-alnum -> '_', trim underscores."""
    return re.sub(r"^_|_$", "", re.sub(r"[^a-z0-9]+", "_", str(s or "").lower()))


def master_key(factor: str, band_key: str, skin: str, concern: str) -> str:
    """Build the EV.master lookup key exactly as the front-end does."""
    return f"{slug(factor)}|{band_key}|{slug(skin)}|{slug(concern)}"


# ============================================================================
# 2. DATA MODELS — persistence-ready (map these to your ORM / tables)
#    See patterns-implementation-spec-v1.md §6 for the table shapes.
# ============================================================================
@dataclass
class DailyLog:
    """One calendar day of user input. Enforce UNIQUE(user_id, log_date) so
    multiple saves in a day collapse to ONE log-day (richness is merged)."""
    user_id: str
    log_date: date
    city: str
    symptoms: list[str] = field(default_factory=list)   # subset of SYMPTOMS (or empty = 'normal')
    zones: list[str] = field(default_factory=list)
    tz: str = "Asia/Kolkata"

    @property
    def is_normal(self) -> bool:
        return not self.symptoms


@dataclass
class EnvDay:
    """Resolved environment for a city on a date (from EV.zone_weather + bands).
    band_keys maps driver -> band_key (e.g. {'humidity':'high', ...})."""
    city: str
    day: date
    band_keys: dict[str, str] = field(default_factory=dict)

    def adverse_drivers(self) -> set[str]:
        return {d for d, b in self.band_keys.items() if b in ADVERSE_BANDS.get(d, set())}


@dataclass
class Pattern:
    driver: str
    symptom: str
    city: str
    E: int          # exposure days (adverse-driver days that were logged)
    H: int          # hits (exposure days where symptom appeared within lag)
    match: float    # H / E
    lift: float
    label: str      # HIGH | MODERATE | EARLY
    status: str     # promoted | emerging | demoted | recalibrating
    lag_hours: int
    zones: list[str]
    weekday_hits: int
    weekend_hits: int
    library_cell_id: Optional[str]
    pmids: list[str]
    first_detected: date
    last_confirmed: date
    chart: list[dict] = field(default_factory=list)  # v4 correlation series [{lvl,sym}]
    weak_lift_days: int = 0  # consecutive days lift < DEMOTE_LIFT (for demotion)


@dataclass
class PatternState:
    user_id: str
    state: str                       # LOCKED | EARLY_SIGNALS | UNLOCKED_ACTIVE | UNLOCKED_FADING | UNLOCKED_PAUSED
    first_log_date: Optional[date]
    unlocked_at: Optional[datetime]
    log_days_30: int
    exposure_days_30: int
    projected_unlock_date: Optional[date]
    last_decay_notified_state: Optional[str] = None
    # optional nudge timestamps (persisted in Mongo; not used by evaluate_state)
    last_behind_pace_push_at: Optional[datetime] = None
    last_weekly_digest_at: Optional[datetime] = None
    last_locked_push_d2_at: Optional[datetime] = None


# ============================================================================
# 3. WINDOW MATH — the two gates + the state machine (§4 of the spec)
# ============================================================================
def _window_logs(logs: list[DailyLog], today: date, days: int = Config.WINDOW_DAYS) -> list[DailyLog]:
    start = today - timedelta(days=days - 1)
    # collapse to one log per calendar day (defensive; DB UNIQUE should guarantee)
    by_day: dict[date, DailyLog] = {}
    for lg in logs:
        if start <= lg.log_date <= today:
            by_day[lg.log_date] = lg
    return list(by_day.values())


def _log_day_count(logs: list[DailyLog], today: date) -> int:
    return len(_window_logs(logs, today))


def _exposure_day_count(logs: list[DailyLog], env: dict[date, EnvDay], today: date) -> int:
    """Distinct logged days in-window that were adverse for at least one driver."""
    n = 0
    for lg in _window_logs(logs, today):
        ed = env.get(lg.log_date)
        if ed and ed.adverse_drivers():
            n += 1
    return n


def _projected_unlock(first_log: Optional[date], log_days: int, today: date) -> Optional[date]:
    """Naive estimate assuming the user logs daily from now on. Used for the
    'unlocks ~12 July' copy. Recompute daily."""
    if first_log is None:
        return None
    days_to_floor = max(0, Config.UNLOCK_HARD_FLOOR_DAYS - (today - first_log).days)
    days_to_logs = max(0, Config.UNLOCK_LOG_DAYS - log_days)
    return today + timedelta(days=max(days_to_floor, days_to_logs))


def evaluate_state(ps: PatternState, logs: list[DailyLog], env: dict[date, EnvDay],
                   today: date) -> PatternState:
    """Run the state machine. Call on (a) every log save, (b) daily midnight job.
    `unlocked` is a one-way latch: once UNLOCKED_* we never return to LOCKED.
    Returns the updated PatternState (mutated in place and returned)."""
    log_days = _log_day_count(logs, today)
    exposure_days = _exposure_day_count(logs, env, today)
    ps.log_days_30 = log_days
    ps.exposure_days_30 = exposure_days
    ps.projected_unlock_date = _projected_unlock(ps.first_log_date, log_days, today)

    already_unlocked = ps.unlocked_at is not None
    if not already_unlocked:
        floor_ok = ps.first_log_date is not None and \
            (today - ps.first_log_date).days >= Config.UNLOCK_HARD_FLOOR_DAYS
        consistency_ok = log_days >= Config.UNLOCK_LOG_DAYS
        exposure_ok = exposure_days >= Config.EXPOSURE_MIN_DAYS

        if floor_ok and consistency_ok and exposure_ok:
            ps.unlocked_at = datetime.now()
            ps.state = "UNLOCKED_ACTIVE"           # fire UNLOCK event once (see caller)
        elif floor_ok and consistency_ok and not exposure_ok:
            # calm month: unlock a "stability" partial, keep watching for adverse days
            ps.state = "EARLY_SIGNALS"             # flag STABILITY_PARTIAL in the payload
        elif log_days >= 5:
            ps.state = "EARLY_SIGNALS"
        else:
            ps.state = "LOCKED"
    else:
        # post-unlock decay — never re-locks
        if log_days >= Config.ACTIVE_MIN_LOG_DAYS:
            ps.state = "UNLOCKED_ACTIVE"
        elif log_days >= Config.FADING_MIN_LOG_DAYS:
            ps.state = "UNLOCKED_FADING"
        else:
            ps.state = "UNLOCKED_PAUSED"
    return ps


def reactivation_progress(logs: list[DailyLog], today: date) -> dict:
    """3-of-5: count log-days in the last REACT_WINDOW days. Used only while PAUSED."""
    start = today - timedelta(days=Config.REACT_WINDOW - 1)
    done = len({lg.log_date for lg in logs if start <= lg.log_date <= today})
    return {"done": min(done, Config.REACT_LOGS), "need": Config.REACT_LOGS,
            "window": Config.REACT_WINDOW, "reactivated": done >= Config.REACT_LOGS}


# ============================================================================
# 3b. "WARN ME NEXT TIME" — per-pattern pre-emptive alert subscription.
#     Tapping the button on a pattern card opts the user in to a heads-up push
#     when THAT pattern's driver is forecast back into its adverse band. This is
#     the payoff loop: a confirmed pattern turns into a pre-symptom warning.
#
#     Reuses the app's existing surge/notification plumbing (EV.zone_weather +
#     the push system) — it does NOT invent a new channel. Respects the user's
#     global notif prefs; if surge alerts are off, honour that.
# ============================================================================
@dataclass
class PatternAlert:
    """One opt-in. UNIQUE(user_id, pattern_id). pattern_id = 'humidity:breakout'."""
    user_id: str
    pattern_id: str          # f"{driver}:{symptom}"
    driver: str
    symptom: str
    created_at: datetime
    last_fired_on: Optional[date] = None   # dedupe: at most one push per adverse episode
    active: bool = True


def subscribe_alert(user_id: str, pattern: Pattern, existing: list[PatternAlert]) -> PatternAlert:
    """Toggle ON. Idempotent — returns the existing sub if already subscribed."""
    pid = f"{pattern.driver}:{pattern.symptom}"
    for a in existing:
        if a.user_id == user_id and a.pattern_id == pid:
            a.active = True
            return a
    return PatternAlert(user_id=user_id, pattern_id=pid, driver=pattern.driver,
                        symptom=pattern.symptom, created_at=datetime.now())


def unsubscribe_alert(user_id: str, pattern_id: str, existing: list[PatternAlert]) -> None:
    for a in existing:
        if a.user_id == user_id and a.pattern_id == pattern_id:
            a.active = False


def is_subscribed(user_id: str, pattern_id: str, existing: list[PatternAlert]) -> bool:
    return any(a.user_id == user_id and a.pattern_id == pattern_id and a.active
               for a in existing)


def check_pattern_alerts(alerts: list[PatternAlert], forecast_env: dict[date, EnvDay],
                         notif_prefs: dict, today: date,
                         horizon_days: int = 2) -> list[dict]:
    """Run in the forecast job. For each active subscription, if the driver is
    forecast into an adverse band within `horizon_days`, emit a push descriptor.
    De-dupes via last_fired_on so a multi-day surge fires once, not daily.

    forecast_env: {date -> EnvDay} for upcoming days (from EV.zone_weather forecast).
    notif_prefs:  the user's toggles, e.g. {'surge': True}. Surge off -> no push.
    Returns a list of {pattern_id, driver, symptom, when, band} for the notifier
    to render via prompts.pattern_alert_copy().
    """
    if not notif_prefs.get("surge", True):
        return []
    out = []
    upcoming = [today + timedelta(days=d) for d in range(1, horizon_days + 1)]
    for a in alerts:
        if not a.active:
            continue
        for day in upcoming:
            ed = forecast_env.get(day)
            if not ed:
                continue
            band = ed.band_keys.get(a.driver)
            if band in ADVERSE_BANDS.get(a.driver, set()):
                # already warned for a current run? skip until it clears.
                if a.last_fired_on and (day - a.last_fired_on).days <= horizon_days:
                    break
                a.last_fired_on = today
                out.append({"pattern_id": a.pattern_id, "driver": a.driver,
                            "symptom": a.symptom,
                            "when": "tomorrow" if day == today + timedelta(days=1)
                                    else day.isoformat(),
                            "band": band})
                break
    return out


# ============================================================================
# 4. DETECTION ENGINE — deterministic. AI is NOT involved here. (§5 of the spec)
# ============================================================================
def _symptom_present(logs_by_day: dict[date, DailyLog], day: date, symptom: str,
                     lag_hours: int = Config.SYMPTOM_LAG_HOURS) -> bool:
    """Symptom logged on `day` or within the lag window (next calendar day)."""
    if day in logs_by_day and symptom in logs_by_day[day].symptoms:
        return True
    if lag_hours >= 24:
        nxt = day + timedelta(days=1)
        if nxt in logs_by_day and symptom in logs_by_day[nxt].symptoms:
            return True
    return False


def _baseline_rate(logs_by_day: dict[date, DailyLog], env: dict[date, EnvDay],
                   symptom: str, window_days: list[date]) -> float:
    """Rate of `symptom` on calm (non-adverse) logged days. Floored to avoid
    divide-by-zero blowing up the lift ratio."""
    calm = [d for d in window_days
            if d in logs_by_day and (d not in env or not env[d].adverse_drivers())]
    if not calm:
        return Config.BASELINE_FLOOR
    hits = sum(1 for d in calm if symptom in logs_by_day[d].symptoms)
    return max(hits / len(calm), Config.BASELINE_FLOOR)


def _label_for(E: int, lift: float) -> str:
    if E >= Config.LABEL_HIGH_E and lift >= Config.LABEL_HIGH_LIFT:
        return "HIGH"
    if E >= Config.LABEL_MOD_E and lift >= Config.LABEL_MOD_LIFT:
        return "MODERATE"
    return "EARLY"


def _confidence_dots(label: str) -> int:
    """Map the label to the 1-5 dots the v4 UI shows ('How sure')."""
    return {"HIGH": 5, "MODERATE": 4, "EARLY": 3}.get(label, 3)


def _build_chart(logs_by_day: dict[date, DailyLog], env: dict[date, EnvDay],
                 driver: str, symptom: str, today: date) -> list[dict]:
    """Build the v4 correlation series: last CHART_DAYS days as
    [{lvl: driver intensity 0-1, sym: symptom logged bool}]. `lvl` is a coarse
    0/.35/.7/1 proxy from the band; replace with a real normalized intensity if
    you store raw driver values."""
    from app.hlhp.patterns.band_bridge import band_intensity

    out = []
    for i in range(Config.CHART_DAYS - 1, -1, -1):
        d = today - timedelta(days=i)
        ed = env.get(d)
        band = ed.band_keys.get(driver) if ed else None
        lvl = band_intensity(band)
        sym = bool(d in logs_by_day and symptom in logs_by_day[d].symptoms)
        out.append({"lvl": round(lvl, 2), "sym": sym})
    return out


def detect_patterns(user_id: str, logs: list[DailyLog], env: dict[date, EnvDay],
                    profile: dict, ev_master: dict, today: date,
                    prev_patterns: Optional[list[Pattern]] = None) -> list[Pattern]:
    """Return the current pattern set (promoted + emerging). Pure & reproducible.

    profile: {skin, concern, age, life}  (used only for the library-cell lookup)
    ev_master: the EV.master dict from hlhp-evidence.json (for L1 text + PMIDs)
    prev_patterns: yesterday's patterns (for demotion tracking) — optional.
    """
    win_logs = _window_logs(logs, today)
    logs_by_day = {lg.log_date: lg for lg in logs}          # full history for lag lookups
    window_days = [lg.log_date for lg in win_logs]

    candidates: list[Pattern] = []
    for driver in DRIVERS:
        exposure_days = [d for d in window_days
                         if d in env and driver in env[d].adverse_drivers()]
        E = len(exposure_days)
        if E == 0:
            continue
        for symptom in SYMPTOMS:
            H = sum(1 for d in exposure_days if _symptom_present(logs_by_day, d, symptom))
            if H == 0:
                continue
            match = H / E
            base = _baseline_rate(logs_by_day, env, symptom, window_days)
            lift = match / base
            weekday_hits = sum(1 for d in exposure_days
                               if _symptom_present(logs_by_day, d, symptom) and d.weekday() < 5)
            weekend_hits = H - weekday_hits
            band_key = next((env[d].band_keys.get(driver) for d in exposure_days
                             if env.get(d) and env[d].band_keys.get(driver)), "high")
            cell_key = master_key(driver, band_key, profile.get("skin", "normal"),
                                  profile.get("concern", "acne"))
            cell = ev_master.get(cell_key)
            label = _label_for(E, lift)
            candidates.append(Pattern(
                driver=driver, symptom=symptom, city=profile.get("city", ""),
                E=E, H=H, match=round(match, 3), lift=round(lift, 2),
                label=label, status="promoted",
                lag_hours=Config.SYMPTOM_LAG_HOURS,
                zones=[],  # fill from logs_by_day[d].zones aggregation if desired
                weekday_hits=weekday_hits, weekend_hits=weekend_hits,
                library_cell_id=cell_key if cell else None,
                pmids=(cell or {}).get("pmids", []),
                first_detected=today, last_confirmed=today,
                chart=_build_chart(logs_by_day, env, driver, symptom, today),
            ))

    # promotion gate
    promoted = [c for c in candidates
                if c.E >= Config.PROMOTE_MIN_EXPOSURE and c.lift >= Config.PROMOTE_MIN_LIFT]
    # sort: HIGH first, then by match desc
    label_rank = {"HIGH": 0, "MODERATE": 1, "EARLY": 2}
    promoted.sort(key=lambda p: (label_rank.get(p.label, 3), -p.match))

    prev_map = {(p.driver, p.symptom): p for p in (prev_patterns or [])}
    for p in promoted:
        prev = prev_map.get((p.driver, p.symptom))
        p.weak_lift_days = prev.weak_lift_days if prev else 0
        if prev:
            p.first_detected = prev.first_detected
        if p.lift < Config.DEMOTE_LIFT:
            p.weak_lift_days += 1
        else:
            p.weak_lift_days = 0
            p.last_confirmed = today
        if p.weak_lift_days >= Config.DEMOTE_DAYS:
            p.status = "emerging"

    for i, p in enumerate(promoted):
        if p.status == "promoted" and i >= Config.MAX_DISPLAYED:
            p.status = "emerging"
    return promoted


# ============================================================================
# 5. PAYLOAD BUILDERS — the JSON the FRONT-END consumes.
#    These replace the hardcoded arrays in animSP() (see §7 OLD->NEW map).
# ============================================================================
def pattern_to_card(p: Pattern, subscribed: bool = False) -> dict:
    """Shape one Pattern into the v4 card contract (patterns-lifecycle-ui-v4.html).
    The `narrative` fields (say/plain) are filled by the AI layer (§6); here we
    provide deterministic template fallbacks so the card renders even w/o AI.
    `subscribed` drives the "Warn me next time" button state on the card."""
    dui = DRIVER_UI.get(p.driver, {})
    sui = SYMPTOM_UI.get(p.symptom, {})
    hi = sum(1 for c in p.chart if c["lvl"] >= 0.6)
    hit = sum(1 for c in p.chart if c["lvl"] >= 0.6 and c["sym"])
    return {
        "id": f"{p.driver}:{p.symptom}",
        "color_var": dui.get("color_var", "--accent-primary"),
        "w_icon": dui.get("w_icon", "ti-cloud"),
        "w_label": dui.get("label", p.driver),
        "s_icon": sui.get("s_icon", "ti-mood-neutral"),
        "s_label": sui.get("label", p.symptom),
        "driver_leg": dui.get("leg", p.driver),
        "sym_leg": sui.get("leg", p.symptom),
        # deterministic template text (AI overrides say/plain/cc_note when available)
        "say": f"{dui.get('label', p.driver)} → {sui.get('leg', p.symptom)}, usually next day",
        "plain": f"Happened {p.H} of {p.E} times. The tall bars and your {sui.get('leg', p.symptom)} line up.",
        "cc_note": f"{hit} of {hi} high-{p.driver} days matched your {sui.get('leg', p.symptom)}.",
        "conf": _confidence_dots(p.label),
        "label": p.label,
        "score_line": f"{hit} of {hi} lined up",
        "chart": p.chart,                       # [{lvl,sym}] -> correlation graph
        "pmids": p.pmids,
        "status": p.status,
        "subscribed": subscribed,               # "Warn me next time" toggle state
        "src": f"Based on your logs · {(p.pmids or ['—'])[0]}",
    }


def build_patterns_payload(ps: PatternState, patterns: list[Pattern],
                           logs: list[DailyLog], today: date,
                           stability_partial: bool = False,
                           alerts: Optional[list["PatternAlert"]] = None) -> dict:
    """Top-level payload for GET /v1/patterns  (+ /v1/patterns/state merged in).
    The front-end switches its Patterns screen purely on `state`.
    `alerts`: the user's PatternAlert subscriptions -> sets each card's
    `subscribed` flag so the 'Warn me next time' button renders on/off."""
    promoted = [p for p in patterns if p.status == "promoted"]
    emerging = [p for p in patterns if p.status == "emerging"]
    alerts = alerts or []
    _sub = {a.pattern_id for a in alerts if a.active}

    payload = {
        "state": ps.state,                       # drives which screen renders
        "stability_partial": stability_partial,
        "meter": {
            "log_days": ps.log_days_30,
            "log_days_target": Config.UNLOCK_LOG_DAYS,
            "exposure_days": ps.exposure_days_30,
            "exposure_target": Config.EXPOSURE_MIN_DAYS,
            "days_since_first_log": ((today - ps.first_log_date).days
                                     if ps.first_log_date else 0),
            "floor_days": Config.UNLOCK_HARD_FLOOR_DAYS,
            "projected_unlock_date": (ps.projected_unlock_date.isoformat()
                                      if ps.projected_unlock_date else None),
        },
        "freshness": {
            "UNLOCKED_ACTIVE": "active", "UNLOCKED_FADING": "fading",
            "UNLOCKED_PAUSED": "paused",
        }.get(ps.state),
        "patterns": [pattern_to_card(p, subscribed=f"{p.driver}:{p.symptom}" in _sub)
                     for p in promoted],
        "emerging": [
            {"id": f"{p.driver}:{p.symptom}",
             "text": f"{DRIVER_UI.get(p.driver, {}).get('label', p.driver)} "
                     f"→ {SYMPTOM_UI.get(p.symptom, {}).get('leg', p.symptom)} "
                     f"— {p.H} of {p.E} so far. A couple more confirmations and we can name it."}
            for p in emerging
        ],
    }
    if ps.state == "UNLOCKED_FADING":
        from app.hlhp.patterns.hlhp_patterns_prompts import lifecycle

        payload["decay_banner"] = lifecycle("fading.banner")
    elif ps.state == "UNLOCKED_PAUSED":
        from app.hlhp.patterns.hlhp_patterns_prompts import lifecycle

        payload["decay_banner"] = lifecycle("paused.react")
        payload["reactivation"] = reactivation_progress(logs, today)
    return payload


# ============================================================================
# 6. AI NARRATION CONTRACT — AI narrates ONLY. It never detects. (§7 of the spec)
# ============================================================================
def build_narration_packet(ps: PatternState, patterns: list[Pattern],
                           profile: dict, month_summary: dict,
                           ev_master: dict, voice_rules: str = "") -> dict:
    """Everything the LLM is allowed to see. NOTE: no raw logs, no PII, city only.
    Every number the model may write appears here; the validator enforces that.

    `voice_rules`: pass hlhp_patterns_prompts.VOICE_RULES. The actual system
    prompt, few-shot example, output schema, and per-output user templates live
    in hlhp_patterns_prompts.py -> build_messages(packet)."""
    def cell_l1(p: Pattern) -> str:
        return (ev_master.get(p.library_cell_id or "") or {}).get("l1", "")
    return {
        "voice_rules": voice_rules,
        "profile": {k: profile.get(k) for k in ("skin", "concern", "age", "life")},
        "city": profile.get("city"),
        "patterns": [{
            "driver": p.driver, "symptom": p.symptom, "band": None,
            "E": p.E, "H": p.H, "match": round(p.match, 2),
            "lag_hours": p.lag_hours, "zones": p.zones,
            "weekday_hits": p.weekday_hits, "weekend_hits": p.weekend_hits,
            "label": p.label, "library_l1": cell_l1(p), "pmids": p.pmids,
        } for p in patterns if p.status == "promoted"],
        "month_summary": month_summary,   # e.g. {"log_days":26,"surges":[...]}
        "outputs_wanted": ["pattern_narrative", "unlock_headline", "weekly_digest"],
    }


_NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def _numbers_in(text: str) -> set[str]:
    return set(_NUM_RE.findall(text or ""))


def _allowed_numbers(packet: dict) -> set[str]:
    """All numerals present anywhere in the input packet, plus derived forms
    (percent of a match, 'H of E')."""
    allowed: set[str] = set()
    blob = json.dumps(packet)
    allowed |= set(_NUM_RE.findall(blob))
    for p in packet.get("patterns", []):
        allowed.add(str(p["E"]))
        allowed.add(str(p["H"]))
        allowed.add(str(round(p["match"] * 100)))   # "83" from 0.83
    return allowed


def validate_narration(output_text: str, packet: dict) -> bool:
    """BLOCKING check (spec §7): every numeral in the AI output must be present
    in / derivable from the input packet. Fail -> regenerate once -> fallback.
    Also: no medical claims beyond library text, run your voice lint here."""
    return _numbers_in(output_text).issubset(_allowed_numbers(packet))


def narration_fallback(p: Pattern) -> str:
    """Deterministic template used when AI is unavailable or fails validation.
    The screen must render fully with this — never block on the LLM."""
    dui = DRIVER_UI.get(p.driver, {})
    sui = SYMPTOM_UI.get(p.symptom, {})
    zone = f" on your {p.zones[0]}" if p.zones else ""
    return (f"{dui.get('label', p.driver)} matched your {sui.get('leg', p.symptom)} "
            f"{p.H} of {p.E} times{zone}.")


# ============================================================================
# 7. OLD -> NEW MAP  (for the FRONT-END developer)
# ============================================================================
#
# In hlhp-interactive.html, animSP() currently hardcodes:
#     const TL=[0,0,1,0,2,1,...];   // pattern-1 timeline   -> REMOVE
#     $("sp-fill").style.width="83%";                       -> REMOVE
#     const WK=[0,0,0,0,0,1,1];     // weekend grid          -> REMOVE
#     const HR=[30,85,78,...];      // hour chart            -> REMOVE
#
# Replace ALL of that with a fetch of THIS engine's output, exactly like EV loads:
#
#     fetch(`/v1/patterns?user=${uid}`)          // GET, returns build_patterns_payload()
#       .then(r => r.json())
#       .then(P => renderPatterns(P));           // P.state drives the screen
#     fetch(`/v2/patterns/narration?user=${uid}`) // cached AI text (never blocks)
#
# renderPatterns(P) should:
#   - switch on P.state: LOCKED / EARLY_SIGNALS / UNLOCKED_ACTIVE|FADING|PAUSED
#     -> the 8 screens already prototyped in patterns-lifecycle-ui-v4.html
#   - for each card in P.patterns, feed it straight into the v4 eqCard()/corrChart()
#     (the field names here match: color_var, w_icon, w_label, s_icon, s_label,
#      say, plain, cc_note, conf, chart:[{lvl,sym}], pmids, score_line).
#   - render P.meter into the ring/progress; P.freshness into the toolbar pill;
#     P.reactivation into the paused-state 3-of-5 dots.
#
# WHAT'S MISSING IN THE CURRENT BUILD (make these real):
#   1. Persist DailyLog server-side on HLHP.saveLog() (today it's state.logCount++ only).
#   2. Store first_log_date per user (the 30-day floor counts from it).
#   3. Nightly job: evaluate_state() + detect_patterns() + refresh narration cache.
#   4. Serve EV.master to this engine (same file the client fetches) so library
#      L1 text + PMIDs attach to each pattern.
#   5. Notifications: fire on state transitions with the rate limits in spec §8.
# ============================================================================


# ============================================================================
# 8. OPTIONAL Flask surface (mapped to the /v1 engine + /v2 engagement split).
#    Delete if you wire this engine into your existing framework instead.
# ============================================================================
def make_flask_app(repo):
    """`repo` is your persistence adapter exposing:
        repo.get_state(user_id)   -> PatternState
        repo.get_logs(user_id)    -> list[DailyLog]
        repo.get_env(city)        -> dict[date, EnvDay]
        repo.get_profile(user_id) -> dict{city,skin,concern,age,life}
        repo.ev_master()          -> dict  (from hlhp-evidence.json)
        repo.save_log(DailyLog)   -> None
        repo.narration(user_id)   -> dict  (cached AI text; may be {})
    """
    from flask import Flask, jsonify, request
    app = Flask(__name__)

    def _compute(user_id, today=None):
        today = today or date.today()
        ps = repo.get_state(user_id)
        logs = repo.get_logs(user_id)
        env = repo.get_env(repo.get_profile(user_id)["city"])
        evaluate_state(ps, logs, env, today)
        pats = detect_patterns(user_id, logs, env, repo.get_profile(user_id),
                               repo.ev_master(), today)
        stability = (ps.state == "EARLY_SIGNALS"
                     and ps.log_days_30 >= Config.UNLOCK_LOG_DAYS)
        return ps, pats, logs, build_patterns_payload(ps, pats, logs, today, stability)

    @app.get("/v1/patterns/state")
    def patterns_state(user_id=None):
        uid = request.args.get("user", "")
        _, _, _, payload = _compute(uid)
        return jsonify({k: payload[k] for k in ("state", "meter", "freshness",
                                                "stability_partial")})

    @app.get("/v1/patterns")
    def patterns(user_id=None):
        uid = request.args.get("user", "")
        _, _, _, payload = _compute(uid)
        return jsonify(payload)

    @app.get("/v2/patterns/narration")
    def narration(user_id=None):
        return jsonify(repo.narration(request.args.get("user", "")))

    @app.post("/v1/logs")
    def post_log():
        body = request.get_json(force=True)
        repo.save_log(DailyLog(
            user_id=body["user"], log_date=date.fromisoformat(body["date"]),
            city=body.get("city", ""), symptoms=body.get("symptoms", []),
            zones=body.get("zones", [])))
        _, _, _, payload = _compute(body["user"])
        return jsonify(payload)

    @app.post("/v2/patterns/alert")
    def toggle_alert():
        """"Warn me next time" toggle. Body: {user, pattern_id, on:bool}.
        Needs repo.get_alerts(user)/save_alerts(user, list) + repo.get_patterns(user)."""
        body = request.get_json(force=True)
        uid, pid, on = body["user"], body["pattern_id"], body.get("on", True)
        alerts = repo.get_alerts(uid)
        if on:
            pat = next((p for p in repo.get_patterns(uid)
                        if f"{p.driver}:{p.symptom}" == pid), None)
            if pat:
                subscribe_alert(uid, pat, alerts)
        else:
            unsubscribe_alert(uid, pid, alerts)
        repo.save_alerts(uid, alerts)
        return jsonify({"pattern_id": pid, "subscribed": is_subscribed(uid, pid, alerts)})

    return app


# ============================================================================
# 9. SELF-TEST / DEMO — run `python hlhp_patterns_engine.py` to see a payload.
#    Synthesises 30 days of logs + env so the dev can eyeball the output shape.
# ============================================================================
def _demo():
    today = date(2026, 7, 7)
    first = today - timedelta(days=32)

    # Fake env: humidity is 'high' on ~half the days; aqi 'high' on some mornings.
    env: dict[date, EnvDay] = {}
    for i in range(40):
        d = today - timedelta(days=i)
        band = {}
        band["humidity"] = "high" if i % 2 == 0 else "moderate"
        band["aqi"] = "high" if i % 3 == 0 else "low"
        band["temp"] = "moderate"
        band["uv"] = "moderate"
        env[d] = EnvDay(city="Pune", day=d, band_keys=band)

    # Fake logs: 26 of the last 30 days; breakouts tend to follow humid days.
    logs: list[DailyLog] = []
    for i in range(30):
        d = today - timedelta(days=i)
        if i in (4, 11, 19, 25):       # 4 skipped days -> 26 log-days
            continue
        syms = []
        if env[d].band_keys.get("humidity") == "high" and i % 2 == 0:
            syms.append("breakout")
        if env[d].band_keys.get("aqi") == "high" and i % 3 == 0:
            syms.append("dull")
        logs.append(DailyLog(user_id="u1", log_date=d, city="Pune", symptoms=syms))

    ps = PatternState(user_id="u1", state="LOCKED", first_log_date=first,
                      unlocked_at=None, log_days_30=0, exposure_days_30=0,
                      projected_unlock_date=None)
    profile = {"city": "Pune", "skin": "Combination", "concern": "Acne",
               "age": "Adult", "life": "Female"}
    ev_master = {}   # in prod: load hlhp-evidence.json -> EV["master"]

    evaluate_state(ps, logs, env, today)
    pats = detect_patterns("u1", logs, env, profile, ev_master, today)
    payload = build_patterns_payload(ps, pats, logs, today)

    print("STATE:", ps.state,
          "| log_days:", ps.log_days_30,
          "| exposure_days:", ps.exposure_days_30)
    print("PATTERNS FOUND:", len(payload["patterns"]))
    print(json.dumps(payload, indent=2, default=str)[:1800])


if __name__ == "__main__":
    _demo()
