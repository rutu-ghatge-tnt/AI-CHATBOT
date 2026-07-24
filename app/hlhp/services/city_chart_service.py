"""Multi-city SFI board from WeatherAPI slot averages (not live polling).

Fixed board = 11 cities. Localities (e.g. Baner) map into their parent city.
If the user's place is outside the 11, it is added as a temporary 12th row.
Today / yesterday SFI come from averaging env metrics at SFI_SLOT_HOURS.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.hlhp.config import hl_settings
from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.services.sfi_unified import resolve_sfi
from app.hlhp.services import open_meteo_uv
from app.hlhp.services.weather_http import get_json
from app.hlhp.services.weather_quota import PROVIDER_WEATHERAPI
from app.hlhp.services.weatherapi_forecast import aqi_from_air_quality
from app.hlhp.services.weatherapi_timeline import SFI_SLOT_HOURS
from app.hlhp.utils.cache import get_cached, set_cached

logger = logging.getLogger(__name__)

_CACHE_BOARD = "hl:city-chart:board:v3"
_IST = ZoneInfo("Asia/Kolkata")
_BOARD_LOCKS: dict[str, asyncio.Lock] = {}

# Fixed 11-city board (same set as HelloCityChart / V7).
CITY_QUERIES: dict[str, str] = {
    "Pune": "Pune,India",
    "Bengaluru": "Bengaluru,India",
    "Hyderabad": "Hyderabad,India",
    "Delhi": "New Delhi,India",
    "Mumbai": "Mumbai,India",
    "Chennai": "Chennai,India",
    "Jaipur": "Jaipur,India",
    "Shimla": "Shimla,India",
    "Ahmedabad": "Ahmedabad,India",
    "Ooty": "Ooty,India",
    "Rajkot": "Rajkot,India",
}

# Locality / alias → board city (Baner is a Pune neighbourhood, not its own city).
_CITY_ALIASES: dict[str, str] = {
    "baner": "Pune",
    "hinjewadi": "Pune",
    "kothrud": "Pune",
    "wakad": "Pune",
    "hadapsar": "Pune",
    "kharadi": "Pune",
    "viman nagar": "Pune",
    "aundh": "Pune",
    "pimpri": "Pune",
    "chinchwad": "Pune",
    "pcmc": "Pune",
    "bangalore": "Bengaluru",
    "bengaluru": "Bengaluru",
    "blr": "Bengaluru",
    "new delhi": "Delhi",
    "delhi ncr": "Delhi",
    "ncr": "Delhi",
    "gurgaon": "Delhi",
    "gurugram": "Delhi",
    "noida": "Delhi",
    "bombay": "Mumbai",
    "navi mumbai": "Mumbai",
    "thane": "Mumbai",
    "madras": "Chennai",
    "udhagamandalam": "Ooty",
}


def _to_float(value: Any, default: float) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def resolve_chart_city(raw: str | None) -> tuple[str, bool]:
    """Map a user/locality label onto the board.

    Returns (canonical_name, is_fixed_board_city).
    Baner → Pune (in board). Nagpur → Nagpur (12th city for that user).
    """
    text = (raw or "Pune").strip()
    if not text:
        return "Pune", True

    lowered = text.lower().replace("·", ",")
    # Exact board match (whole string or comma-separated tokens).
    tokens = [p.strip() for p in lowered.replace(";", ",").split(",") if p.strip()]
    for city in CITY_QUERIES:
        cl = city.lower()
        if lowered == cl or cl in tokens:
            return city, True
        if cl in lowered and any(cl == t or t.endswith(f" {cl}") for t in tokens):
            return city, True

    # Alias / locality → parent board city.
    for alias, parent in _CITY_ALIASES.items():
        if alias == lowered or alias in tokens or alias in lowered:
            return parent, True

    # Prefer last recognizable city token ("Baner, Pune, Maharashtra" → Pune).
    for token in reversed(tokens):
        for city in CITY_QUERIES:
            if token == city.lower():
                return city, True
        if token in _CITY_ALIASES:
            return _CITY_ALIASES[token], True

    # Outside the 11 → keep as a 12th city label (title-case first token).
    label = tokens[0].title() if tokens else text.title()
    return label, False


def _env_from_metrics(city: str, metrics: dict[str, Any]) -> EnvironmentalData:
    return EnvironmentalData(
        uv_index=float(metrics["uv_index"]),
        temperature_c=float(metrics["temperature_c"]),
        aqi=int(metrics["aqi"]),
        humidity_pct=float(metrics["humidity_pct"]),
        wind_kmh=float(metrics.get("wind_kmh") or 0.0),
        wind_dir=str(metrics.get("wind_dir") or ""),
        gust_kmh=float(metrics.get("gust_kmh") or 0.0),
        location_name=city,
    )


def _sfi_for(city: str, metrics: dict[str, Any], *, surge: bool = False) -> tuple[int, str, str]:
    m = dict(metrics)
    if surge:
        m["temperature_c"] = max(float(m["temperature_c"]), 38.0)
        m["aqi"] = max(int(m["aqi"]), 380)
        m["uv_index"] = max(float(m["uv_index"]), 11.0)
    eval_ = resolve_sfi(_env_from_metrics(city, m), None, guest_mode=True, surge=surge)
    return eval_.environmental_sfi, eval_.mode, eval_.dominant_factor


def _pick_hour(hours: list[dict], date_iso: str, hour: int) -> dict | None:
    prefix = f"{date_iso} {hour:02d}:"
    for row in hours:
        if isinstance(row, dict) and str(row.get("time") or "").startswith(prefix):
            return row
    return None


def _average_slot_metrics(data: dict, date_iso: str) -> dict[str, Any] | None:
    """Average temp/humidity/UV/AQI/wind across SFI_SLOT_HOURS for one calendar day."""
    forecast = data.get("forecast") if isinstance(data.get("forecast"), dict) else {}
    days = forecast.get("forecastday") if isinstance(forecast.get("forecastday"), list) else []
    day_row = None
    for fd in days:
        if isinstance(fd, dict) and str(fd.get("date") or "") == date_iso:
            day_row = fd
            break
    if day_row is None and days and isinstance(days[0], dict):
        day_row = days[0]

    if not isinstance(day_row, dict):
        return None

    hours = day_row.get("hour") if isinstance(day_row.get("hour"), list) else []
    samples: list[dict[str, Any]] = []
    for slot in SFI_SLOT_HOURS:
        hour_row = _pick_hour(hours, date_iso, slot)
        if not isinstance(hour_row, dict):
            continue
        samples.append(
            {
                "temperature_c": _to_float(hour_row.get("temp_c"), 25.0),
                "humidity_pct": _to_float(hour_row.get("humidity"), 50.0),
                "uv_index": _to_float(hour_row.get("uv"), 5.0),
                "aqi": float(aqi_from_air_quality(hour_row.get("air_quality"), fallback=50)),
                "wind_kmh": _to_float(hour_row.get("wind_kph"), 0.0),
            }
        )

    # Fallback: WeatherAPI day averages if hourly slots missing.
    if not samples:
        day = day_row.get("day") if isinstance(day_row.get("day"), dict) else {}
        aq = day.get("air_quality") if isinstance(day.get("air_quality"), dict) else None
        return {
            "temperature_c": _to_float(day.get("avgtemp_c", day.get("maxtemp_c")), 25.0),
            "humidity_pct": _to_float(day.get("avghumidity"), 50.0),
            "uv_index": round(_to_float(day.get("uv"), 5.0), 1),
            "aqi": aqi_from_air_quality(aq, fallback=50),
            "wind_kmh": _to_float(day.get("maxwind_kph"), 0.0),
            "wind_dir": "",
            "gust_kmh": 0.0,
            "slots": 0,
        }

    n = len(samples)
    return {
        "temperature_c": round(sum(s["temperature_c"] for s in samples) / n, 1),
        "humidity_pct": round(sum(s["humidity_pct"] for s in samples) / n, 1),
        "uv_index": round(sum(s["uv_index"] for s in samples) / n, 1),
        "aqi": int(round(sum(s["aqi"] for s in samples) / n)),
        "wind_kmh": round(sum(s["wind_kmh"] for s in samples) / n, 1),
        "wind_dir": "",
        "gust_kmh": 0.0,
        "slots": n,
    }


async def _fetch_day_payload(query: str, date_iso: str, *, today_iso: str) -> dict | None:
    key = hl_settings.WEATHERAPI_KEY
    if not key:
        return None
    # History for past days; forecast for today (includes hourly slots).
    if date_iso < today_iso:
        url = hl_settings.WEATHERAPI_HISTORY_URL
        params: dict[str, Any] = {"key": key, "q": query, "dt": date_iso, "aqi": "yes"}
    else:
        url = hl_settings.WEATHERAPI_FORECAST_URL
        params = {"key": key, "q": query, "days": 1, "aqi": "yes"}
    return await get_json(
        url, params=params, timeout=14, provider=PROVIDER_WEATHERAPI
    )

async def fetch_weatherapi_day_payload(query: str, date_iso: str, *, today_iso: str) -> dict | None:
    """Public WeatherAPI day fetch used by city chart + city-env jobs."""
    return await _fetch_day_payload(query, date_iso, today_iso=today_iso)


_FETCH_SEM = asyncio.Semaphore(4)


async def _with_open_meteo_slot_uv(
    metrics: dict[str, Any] | None,
    payload: dict | None,
    date_iso: str,
) -> dict[str, Any] | None:
    """Keep WeatherAPI temp/AQI/wind; replace slot-average UV with Open-Meteo CAMS."""
    if not isinstance(metrics, dict) or not isinstance(payload, dict):
        return metrics
    coords = open_meteo_uv.coords_from_weatherapi_payload(payload)
    if not coords:
        return metrics
    try:
        day = date.fromisoformat(date_iso)
    except ValueError:
        return metrics
    lat, lon = coords
    uv_map = await open_meteo_uv.fetch_hourly_uv_map(
        lat,
        lon,
        start=day,
        end=day,
        timezone_id="Asia/Kolkata",
    )
    avg = open_meteo_uv.slot_uv_average(uv_map, date_iso, SFI_SLOT_HOURS)
    if avg is None:
        return metrics
    updated = dict(metrics)
    updated["uv_index"] = avg
    return updated


async def _city_day_averages(
    city: str,
    query: str,
    *,
    today_iso: str,
    yesterday_iso: str,
    on_board: bool = True,
    persist: bool = True,
) -> dict[str, Any]:
    cache_key = f"hl:city-wx-avg:v2:{city}:{today_iso}:{yesterday_iso}"
    cached = await get_cached(cache_key)
    if cached and isinstance(cached, dict) and "today" in cached:
        return cached

    async with _FETCH_SEM:
        today_raw, yday_raw = await asyncio.gather(
            _fetch_day_payload(query, today_iso, today_iso=today_iso),
            _fetch_day_payload(query, yesterday_iso, today_iso=today_iso),
        )

    today = _average_slot_metrics(today_raw, today_iso) if isinstance(today_raw, dict) else None
    yesterday = (
        _average_slot_metrics(yday_raw, yesterday_iso) if isinstance(yday_raw, dict) else None
    )
    today = await _with_open_meteo_slot_uv(
        today, today_raw if isinstance(today_raw, dict) else None, today_iso
    )
    yesterday = await _with_open_meteo_slot_uv(
        yesterday, yday_raw if isinstance(yday_raw, dict) else None, yesterday_iso
    )
    result = {
        "city": city,
        "today": today,
        "yesterday": yesterday,
        "ok": today is not None,
    }
    if today is not None:
        await set_cached(cache_key, result, hl_settings.WEATHER_CACHE_TTL)

    if persist:
        try:
            from app.hlhp.services.city_env_collector import persist_city_env_day_pair

            await persist_city_env_day_pair(
                city_label=city,
                query=query,
                today_iso=today_iso,
                yesterday_iso=yesterday_iso,
                today_payload=today_raw if isinstance(today_raw, dict) else None,
                yesterday_payload=yday_raw if isinstance(yday_raw, dict) else None,
                on_board=on_board,
            )
        except Exception as exc:
            logger.warning("HLHP city env persist skipped for %s: %s", city, exc)

    return result


def _row_from_reading(
    city: str,
    reading: dict[str, Any],
    *,
    is_you: bool,
    surge: bool,
) -> dict[str, Any] | None:
    today = reading.get("today")
    if not isinstance(today, dict):
        return None
    sfi, mode, dominant = _sfi_for(city, today, surge=surge and is_you)
    yday = reading.get("yesterday")
    if isinstance(yday, dict):
        y_sfi, _, _ = _sfi_for(city, yday, surge=False)
    else:
        y_sfi = sfi
    return {
        "city": city,
        "sfi": sfi,
        "yesterday_sfi": y_sfi,
        "delta": sfi - y_sfi,
        "mode": mode,
        "dominant_driver": dominant,
        "moved": None,
        "is_you": is_you,
        "temperature_c": today.get("temperature_c"),
        "humidity_pct": today.get("humidity_pct"),
        "uv_index": today.get("uv_index"),
        "aqi": today.get("aqi"),
        "wind_kmh": today.get("wind_kmh"),
        "slots": today.get("slots"),
    }


async def build_city_chart(
    *,
    you_city: str = "Pune",
    surge: bool = False,
) -> dict[str, Any]:
    """Ranked SFI board from slot-averaged WeatherAPI readings."""
    you_canon, you_on_board = resolve_chart_city(you_city)
    board_key = f"{_CACHE_BOARD}:{you_canon.lower()}:{int(bool(surge))}"
    cached = await get_cached(board_key)
    if cached and isinstance(cached, dict) and isinstance(cached.get("cities"), list):
        return cached

    lock = _BOARD_LOCKS.setdefault(board_key, asyncio.Lock())
    async with lock:
        # Second look after winning the lock — another request may have filled cache.
        cached = await get_cached(board_key)
        if cached and isinstance(cached, dict) and isinstance(cached.get("cities"), list):
            return cached

        now = datetime.now(_IST)
        today_iso = now.date().isoformat()
        yesterday_iso = (now.date() - timedelta(days=1)).isoformat()

        readings = await asyncio.gather(
            *[
                _city_day_averages(
                    city,
                    query,
                    today_iso=today_iso,
                    yesterday_iso=yesterday_iso,
                    on_board=True,
                    persist=True,
                )
                for city, query in CITY_QUERIES.items()
            ]
        )

        rows: list[dict[str, Any]] = []
        for reading in readings:
            city = reading["city"]
            row = _row_from_reading(
                city,
                reading,
                is_you=(you_on_board and city == you_canon),
                surge=surge,
            )
            if row:
                rows.append(row)

        # 12th city only when the user's place is outside the fixed 11.
        if you_canon and not you_on_board and not any(r["is_you"] for r in rows):
            query = f"{you_canon},India"
            extra = await _city_day_averages(
                you_canon,
                query,
                today_iso=today_iso,
                yesterday_iso=yesterday_iso,
                on_board=False,
                persist=True,
            )
            row = _row_from_reading(you_canon, extra, is_you=True, surge=surge)
            if row:
                rows.append(row)

        rows.sort(key=lambda r: (-int(r["sfi"]), str(r["city"])))
        for i, r in enumerate(rows):
            r["rank"] = i + 1

        payload = {
            "cities": rows,
            "source": "weatherapi_slot_avg+open_meteo_uv",
            "slots": list(SFI_SLOT_HOURS),
            "you_city": you_canon,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        if rows:
            await set_cached(board_key, payload, hl_settings.WEATHER_CACHE_TTL)
        return payload
