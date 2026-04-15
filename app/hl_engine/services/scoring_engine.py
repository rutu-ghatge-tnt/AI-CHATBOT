from app.hl_engine.data.thresholds import (
    AQI_THRESHOLDS,
    DEFAULT_FITZPATRICK,
    FITZPATRICK_MULTIPLIERS,
    HUMIDITY_THRESHOLDS,
    SEVERITY_BANDS,
    SPF_REAPPLY_INTERVALS,
    TEMP_THRESHOLDS,
    THREAT_PRIORITY,
    UV_THRESHOLDS,
)
from app.hl_engine.models.environmental import EnvironmentalData
from app.hl_engine.models.score import FactorScore, SeverityBand, SkinScore


def _score_factor(value: float, thresholds: list, factor_name: str) -> FactorScore:
    for min_val, max_val, points, label, alert_level, skin_impact in thresholds:
        if min_val <= value < max_val:
            return FactorScore(
                factor=factor_name,
                raw_value=value,
                points=points,
                label=label,
                alert_level=alert_level,
                skin_impact=skin_impact,
            )
    tail = thresholds[-1]
    return FactorScore(
        factor=factor_name,
        raw_value=value,
        points=tail[2],
        label=tail[3],
        alert_level=tail[4],
        skin_impact=tail[5],
    )


def _get_band(total: int) -> SeverityBand:
    for min_s, max_s, band_name, _, _ in SEVERITY_BANDS:
        if min_s <= total <= max_s:
            return SeverityBand(band_name)
    return SeverityBand.CODE_RED


def _apply_overrides(band: SeverityBand, factors: list[FactorScore], env: EnvironmentalData):
    zero_count = sum(1 for f in factors if f.points == 0)
    band_order = list(SeverityBand)
    override_applied = False
    reason = ""
    health_advisory = None

    if zero_count == 1:
        idx = band_order.index(band)
        if idx > 0:
            band = band_order[idx - 1]
            override_applied = True
            reason = "Escalated: one critical factor at zero."
    elif zero_count == 2:
        if band_order.index(band) > band_order.index(SeverityBand.HOSTILE):
            band = SeverityBand.HOSTILE
            override_applied = True
            reason = "Escalated: two critical factors at zero."
    elif zero_count >= 3:
        band = SeverityBand.CODE_RED
        override_applied = True
        reason = "Escalated: three or more critical factors at zero."

    if env.aqi > 250:
        health_advisory = "AQI is hazardous. Limit outdoor exposure and use an N95 mask."
    if env.uv_index > 11:
        msg = "UV is extreme. Avoid direct sun between 10am and 4pm."
        health_advisory = f"{health_advisory} {msg}" if health_advisory else msg

    if env.temperature_c > 42:
        health_advisory = "Medical alert: dangerous heat. Prioritize cooling and hydration."
    if env.aqi > 400:
        health_advisory = "Medical alert: hazardous air. Stay indoors and seek care if symptomatic."

    return band, override_applied, reason, health_advisory


def _identify_threats(factors: list[FactorScore]):
    sorted_factors = sorted(factors, key=lambda f: (f.points, THREAT_PRIORITY.index(f.factor)))
    return sorted_factors[0].factor, [f.factor for f in sorted_factors[1:] if f.points <= 12]


def calculate_burn_time(uvi: float, fitzpatrick: int = DEFAULT_FITZPATRICK):
    if uvi <= 0:
        return None
    multiplier = FITZPATRICK_MULTIPLIERS.get(fitzpatrick, 6.7)
    return round((200 * multiplier) / (3 * uvi))


def get_spf_reapply_interval(temp_c: float):
    if temp_c > 42:
        return SPF_REAPPLY_INTERVALS["extreme_heat"]
    if temp_c >= 35:
        return SPF_REAPPLY_INTERVALS["hot"]
    if temp_c >= 28:
        return SPF_REAPPLY_INTERVALS["warm"]
    return SPF_REAPPLY_INTERVALS["default"]


def calculate_skin_score(env: EnvironmentalData) -> SkinScore:
    factors = [
        _score_factor(env.uv_index, UV_THRESHOLDS, "uv_index"),
        _score_factor(env.temperature_c, TEMP_THRESHOLDS, "temperature"),
        _score_factor(env.aqi, AQI_THRESHOLDS, "aqi"),
        _score_factor(env.humidity_pct, HUMIDITY_THRESHOLDS, "humidity"),
    ]
    total = sum(f.points for f in factors)
    band_raw = _get_band(total)
    band, override_applied, override_reason, _ = _apply_overrides(band_raw, factors, env)
    dominant_threat, secondary_threats = _identify_threats(factors)

    return SkinScore(
        total=total,
        band=band,
        band_raw=band_raw,
        override_applied=override_applied,
        override_reason=override_reason,
        factors=factors,
        dominant_threat=dominant_threat,
        secondary_threats=secondary_threats,
    )

