"""Generic city-level pattern card for pre-unlock Patterns tab (spec §1.4)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.hlhp.composition.explore import pick_learn_nuggets
from app.hlhp.core.bands import EnvironmentBands
from app.hlhp.evidence.composition_store import get_composition_store
from app.hlhp.evidence.scenario_store import get_scenario_store
from app.hlhp.models.profile import UserProfile
from app.hlhp.patterns.hlhp_patterns_engine import DRIVER_UI
from app.hlhp.services.concern_resolver import resolve_concern_id

_FACTOR_COLOR = {
    "humidity": "--drv-humidity",
    "uv": "--drv-uv",
    "temperature": "--drv-temp",
    "temp": "--drv-temp",
    "heat": "--drv-temp",
    "pollution": "--drv-aqi",
    "aqi": "--drv-aqi",
    "air": "--drv-aqi",
}

_FACTOR_DRIVER_KEY = {
    "humidity": "humidity",
    "uv": "uv",
    "temperature": "temp",
    "temp": "temp",
    "heat": "temp",
    "pollution": "aqi",
    "aqi": "aqi",
    "air": "aqi",
}


def _city_label(city: str) -> str:
    parts = [p.strip() for p in re.split(r"[,·]", city or "") if p.strip()]
    if not parts:
        return "your city"
    for part in reversed(parts):
        if len(part) > 2 and part.lower() not in {"india", "maharashtra", "karnataka"}:
            return part.title()
    return parts[0].title()


def _factor_meta(factor: str) -> tuple[str, str, str]:
    key = (factor or "humidity").lower().replace(" ", "_")
    driver = _FACTOR_DRIVER_KEY.get(key, "humidity")
    dui = DRIVER_UI.get(driver, {})
    color = dui.get("color_var") or _FACTOR_COLOR.get(key, "--drv-humidity")
    icon = dui.get("w_icon", "ti-cloud")
    leg = dui.get("leg", factor or "weather")
    return color, icon, leg


def _body_intro(label: str, text: str) -> str:
    """Avoid 'Across Pune, North India winters…' when copy names another region."""
    lower = text.lower()
    label_l = label.lower()
    if "north india" in lower and label_l not in {"delhi", "ncr", "chandigarh", "shimla", "jaipur"}:
        return text
    return f"Across {label}, {text}"


def _guest_fallback(city: str) -> dict[str, Any] | None:
    store = get_scenario_store()
    cell = None
    for suffix in (
        "humidity|high|normal|none",
        "humidity|high|combination|none",
        "uv|high|normal|none",
        "aqi|high|normal|none",
    ):
        cell = store.guest.get(f"single|{suffix}")
        if cell:
            break
    if not cell:
        return None
    factor = str(cell.get("factor") or "Humidity")
    color, icon, leg = _factor_meta(factor)
    body = str(cell.get("l1") or cell.get("l0") or "").strip()
    if not body:
        return None
    label = _city_label(city)
    return {
        "city": label,
        "kick": f"{label} · general",
        "body": (
            f"{_body_intro(label, body)} "
            "We'll confirm whether your skin follows this pattern as you log."
        ),
        "factor": leg,
        "color_var": color,
        "w_icon": icon,
        "source": str((cell.get("pmids") or ["SkinBB scenario library"])[0]),
    }


def build_generic_city_pattern(
    *,
    user_id: str,
    city: str,
    profile: UserProfile | None,
    bands: EnvironmentBands | None = None,
    when: datetime | None = None,
) -> dict[str, Any] | None:
    """Pick one city-scoped insight so the LOCKED tab is never empty."""
    resolved_city = (city or "India").strip()
    label = _city_label(resolved_city)
    concern_id = resolve_concern_id(profile=profile) if profile else None
    now = when or datetime.now().astimezone()

    comp_store = get_composition_store()
    rotation_rows = comp_store.composition.get("daily_nuggets_rotation") or []
    scenario_store = get_scenario_store()
    rows = rotation_rows or scenario_store.nuggets or []

    ranked = pick_learn_nuggets(
        rows,
        city=resolved_city,
        concern_id=concern_id,
        profile=profile,
        user_id=user_id,
        when=now,
        bands=bands,
        limit=1,
    )
    if ranked:
        row = ranked[0]
        text = str(row.get("nugget_text") or "").strip()
        if text:
            factor = str(row.get("factor") or "Humidity")
            color, icon, leg = _factor_meta(factor)
            source = str(row.get("source") or row.get("pmid_anchor") or "SkinBB evidence base")
            return {
                "city": label,
                "kick": f"{label} · general",
                "body": (
                    f"{_body_intro(label, text)} "
                    "We'll confirm whether your skin does this as you log."
                ),
                "factor": leg,
                "color_var": color,
                "w_icon": icon,
                "source": source,
            }

    return _guest_fallback(resolved_city)
