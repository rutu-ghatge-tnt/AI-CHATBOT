"""India CPCB National Air Quality Index (NAQI) from pollutant concentrations.

Official method (CPCB):
  1. Compute a sub-index for each available pollutant via linear interpolation
     across health breakpoints.
  2. overall AQI = max(sub-indexes), rounded, clamped to 0..500.

WeatherAPI `air_quality` supplies instantaneous concentrations (not 24h / 8h
averages). We still apply the official breakpoint math so HLHP matches the
Skintruth / Node `overallAQI` scale used elsewhere in SkinBB.
"""

from __future__ import annotations

from typing import Any

# (concentration_low, concentration_high, index_low, index_high)
# Breakpoints from CPCB National Air Quality Index tables.
_BREAKPOINTS: dict[str, list[tuple[float, float, float, float]]] = {
    # µg/m³, 24h
    "pm25": [
        (0, 30, 0, 50),
        (31, 60, 51, 100),
        (61, 90, 101, 200),
        (91, 120, 201, 300),
        (121, 250, 301, 400),
        (251, 500, 401, 500),
    ],
    # µg/m³, 24h
    "pm10": [
        (0, 50, 0, 50),
        (51, 100, 51, 100),
        (101, 250, 101, 200),
        (251, 350, 201, 300),
        (351, 430, 301, 400),
        (431, 600, 401, 500),
    ],
    # µg/m³, 24h
    "no2": [
        (0, 40, 0, 50),
        (41, 80, 51, 100),
        (81, 180, 101, 200),
        (181, 280, 201, 300),
        (281, 400, 301, 400),
        (401, 600, 401, 500),
    ],
    # µg/m³, 24h
    "so2": [
        (0, 40, 0, 50),
        (41, 80, 51, 100),
        (81, 380, 101, 200),
        (381, 800, 201, 300),
        (801, 1600, 301, 400),
        (1601, 2100, 401, 500),
    ],
    # mg/m³, 8h  (WeatherAPI reports CO in µg/m³ → divide by 1000)
    "co": [
        (0, 1.0, 0, 50),
        (1.1, 2.0, 51, 100),
        (2.1, 10.0, 101, 200),
        (10.1, 17.0, 201, 300),
        (17.1, 34.0, 301, 400),
        (34.1, 50.0, 401, 500),
    ],
    # µg/m³ — 8h bands through Poor, then 1h bands for Very Poor / Severe
    "o3": [
        (0, 50, 0, 50),
        (51, 100, 51, 100),
        (101, 168, 101, 200),
        (169, 208, 201, 300),
        (209, 748, 301, 400),
        (749, 1000, 401, 500),
    ],
    # µg/m³, 24h (rarely present on WeatherAPI)
    "nh3": [
        (0, 200, 0, 50),
        (201, 400, 51, 100),
        (401, 800, 101, 200),
        (801, 1200, 201, 300),
        (1201, 1800, 301, 400),
        (1801, 2400, 401, 500),
    ],
    # µg/m³, 24h
    "pb": [
        (0, 0.5, 0, 50),
        (0.51, 1.0, 51, 100),
        (1.1, 2.0, 101, 200),
        (2.1, 3.0, 201, 300),
        (3.1, 3.5, 301, 400),
        (3.51, 5.0, 401, 500),
    ],
}

# WeatherAPI / Skintruth key → CPCB pollutant id
_FIELD_MAP: tuple[tuple[str, str, float], ...] = (
    ("pm2_5", "pm25", 1.0),
    ("pm10", "pm10", 1.0),
    ("no2", "no2", 1.0),
    ("so2", "so2", 1.0),
    ("o3", "o3", 1.0),
    ("co", "co", 0.001),  # µg/m³ → mg/m³
    ("nh3", "nh3", 1.0),
    ("pb", "pb", 1.0),
)

# us-epa-index (1–6) → representative CPCB-scale midpoints when concentrations missing
_EPA_FALLBACK = {1: 45, 2: 90, 3: 140, 4: 200, 5: 300, 6: 400}


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v:  # NaN
        return None
    return v


def calculate_sub_index(concentration: float, pollutant: str) -> float | None:
    """CPCB linear sub-index for one pollutant concentration, or None if out of range."""
    bands = _BREAKPOINTS.get(pollutant)
    if not bands or concentration < 0:
        return None

    last_bp_hi = bands[-1][1]
    last_i_hi = bands[-1][3]
    if concentration > last_bp_hi:
        return float(last_i_hi)

    for i, (bp_lo, bp_hi, i_lo, i_hi) in enumerate(bands):
        # Inclusive published bands; also absorb 1-unit integer gaps (30→31, etc.)
        in_band = bp_lo <= concentration <= bp_hi
        in_gap_before = i > 0 and bands[i - 1][1] < concentration < bp_lo
        if not (in_band or in_gap_before):
            continue
        use_lo = bp_lo if concentration >= bp_lo else bands[i - 1][1]
        use_i_lo = i_lo if concentration >= bp_lo else bands[i - 1][3]
        if bp_hi == use_lo:
            return float(i_hi)
        return ((i_hi - use_i_lo) / (bp_hi - use_lo)) * (concentration - use_lo) + use_i_lo

    return None


def cpcb_aqi_from_concentrations(
    *,
    pm25: float | None = None,
    pm10: float | None = None,
    no2: float | None = None,
    so2: float | None = None,
    o3: float | None = None,
    co_mg: float | None = None,
    nh3: float | None = None,
    pb: float | None = None,
) -> int | None:
    """Return max CPCB sub-index, or None if no usable pollutant."""
    values: dict[str, float | None] = {
        "pm25": pm25,
        "pm10": pm10,
        "no2": no2,
        "so2": so2,
        "o3": o3,
        "co": co_mg,
        "nh3": nh3,
        "pb": pb,
    }
    sub_indexes: list[float] = []
    for key, conc in values.items():
        if conc is None:
            continue
        sub = calculate_sub_index(float(conc), key)
        if sub is not None:
            sub_indexes.append(sub)
    if not sub_indexes:
        return None
    return int(round(min(500.0, max(0.0, max(sub_indexes)))))


def aqi_from_weatherapi_air_quality(aq: dict | None, *, fallback: int = 50) -> int:
    """Map a WeatherAPI / Skintruth-style air_quality dict to CPCB AQI."""
    if not isinstance(aq, dict) or not aq:
        return fallback

    kwargs: dict[str, float] = {}
    key_alias = {
        "pm25": "pm25",
        "pm10": "pm10",
        "no2": "no2",
        "so2": "so2",
        "o3": "o3",
        "co": "co_mg",
        "nh3": "nh3",
        "pb": "pb",
    }
    for field, pollutant, scale in _FIELD_MAP:
        raw = _to_float(aq.get(field))
        if raw is None:
            continue
        kwargs[key_alias[pollutant]] = raw * scale

    computed = cpcb_aqi_from_concentrations(**kwargs)
    if computed is not None:
        return computed

    epa = _to_float(aq.get("us-epa-index"))
    if epa is not None:
        return _EPA_FALLBACK.get(int(epa), fallback)
    return fallback
