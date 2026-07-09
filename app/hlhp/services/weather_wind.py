"""Extract wind fields from Skintruth / WeatherAPI weather payloads."""

from __future__ import annotations

from typing import Any


def _pick_first(data: dict, keys: list[str], default=None):
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return default


def _to_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def extract_wind_fields(payload: dict[str, Any] | None) -> dict[str, float | str]:
    """
    Normalise wind from nested API shapes.

    WeatherAPI ``current`` object::
        wind_kph, wind_mph, wind_degree, wind_dir, gust_kph, gust_mph
        or nested ``wind``: {kph, mph, degree, dir}
    """
    if not payload or not isinstance(payload, dict):
        return {"wind_kmh": 0.0, "wind_dir": "", "gust_kmh": 0.0}

    current = payload.get("current") if isinstance(payload.get("current"), dict) else {}
    if not current:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        weather = data.get("weather") if isinstance(data.get("weather"), dict) else {}
        current = weather.get("current") if isinstance(weather.get("current"), dict) else {}
    if not current and isinstance(payload.get("weather"), dict):
        nested = payload["weather"]
        current = nested.get("current") if isinstance(nested.get("current"), dict) else nested

    wind_block = current.get("wind") if isinstance(current.get("wind"), dict) else {}

    kph = _pick_first(
        current,
        ["wind_kph", "windKph", "wind_kmh", "windKmh", "windSpeed", "wind_speed"],
    )
    if kph is None:
        kph = _pick_first(wind_block, ["kph", "kmh", "speed"])
    if kph is None:
        mph = _pick_first(current, ["wind_mph", "windMph"]) or _pick_first(wind_block, ["mph"])
        if mph is not None:
            kph = _to_float(mph) * 1.60934

    gust = _pick_first(current, ["gust_kph", "gustKph", "gust_kmh"])
    if gust is None:
        gust_mph = _pick_first(current, ["gust_mph", "gustMph"])
        if gust_mph is not None:
            gust = _to_float(gust_mph) * 1.60934

    direction = _pick_first(current, ["wind_dir", "windDir", "wind_direction"])
    if not direction:
        deg = _pick_first(current, ["wind_degree", "windDegree"]) or _pick_first(
            wind_block, ["degree", "dir"]
        )
        if deg is not None and not isinstance(deg, str):
            direction = str(int(_to_float(deg)))
        elif isinstance(deg, str):
            direction = deg.strip()

    return {
        "wind_kmh": round(max(0.0, _to_float(kph)), 1),
        "wind_dir": str(direction or "").strip()[:8],
        "gust_kmh": round(max(0.0, _to_float(gust)), 1),
    }
