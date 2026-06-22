from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.label_looker.engines.base_formula.matrices import load_config
from app.label_looker.engines.base_formula.types import RuntimeContext, UserFlags


def resolve_runtime_context(user: dict, pin_code: Optional[str], scan_date: datetime) -> RuntimeContext:
    season = _resolve_season(scan_date)
    climate_zone = _resolve_climate_zone(pin_code, season)
    flags = _resolve_user_flags(user)
    return RuntimeContext(
        user_id=str(user.get("id", "")),
        skin_type=str(user.get("skin_type", "normal")).lower(),
        climate_zone=climate_zone,
        season=season,
        pin_code=pin_code,
        flags=flags,
        age=user.get("age"),
        concerns=list(user.get("concerns", [])),
        benefits=list(user.get("benefits", [])),
        life_stages=list(user.get("life_stages", [])),
    )


def _resolve_season(scan_date: datetime) -> str:
    month = scan_date.month
    if month in (4, 5, 6):
        return "apr_jun"
    if month in (7, 8, 9):
        return "jul_sep"
    if month in (11, 12, 1, 2):
        return "nov_feb"
    return "mar_oct_other"


def _resolve_climate_zone(pin_code: Optional[str], season: str) -> str:
    if not pin_code or len(pin_code) < 3:
        return "temperate"
    config = load_config("climate_zones.yaml")
    zones = config.get("zones", {})
    default_zone = config.get("default_zone", "temperate")
    return zones.get(pin_code[:3], {}).get(season, default_zone)


def _resolve_user_flags(user: dict) -> UserFlags:
    flags: UserFlags = {}
    declared = {str(x).strip().lower() for x in user.get("self_declared_flags", []) if str(x).strip()}
    concerns = {str(x).strip().lower() for x in user.get("concerns", []) if str(x).strip()}
    flags["sensitive_skin"] = "sensitive" in declared
    flags["eczema"] = "eczema" in declared
    flags["rosacea"] = "rosacea" in declared
    flags["retinoid_user"] = "retinoid_user" in declared or "active_retinoid_use" in declared
    flags["fungal_acne_prone"] = "fungal_acne" in declared
    flags["acne_prone"] = any(x in concerns for x in {"acne", "acne-prone", "breakouts", "pimples"})
    age = user.get("age")
    flags["mature_skin"] = (isinstance(age, int) and age > 40) or ("mature" in declared)
    has_dehydration = bool(concerns & {"tightness", "flaking", "dehydrated", "dry_patches"}) or ("dehydrated" in declared)
    flags["dehydrated_oily"] = str(user.get("skin_type", "")).lower() == "oily" and has_dehydration
    last_proc = user.get("last_procedure_date")
    post_procedure = False
    if isinstance(last_proc, str) and last_proc.strip():
        try:
            proc_dt = datetime.fromisoformat(last_proc.strip())
            post_procedure = (datetime.now() - proc_dt).days <= 14
        except (TypeError, ValueError):
            post_procedure = False
    flags["post_procedure"] = post_procedure
    flags["barrier_compromised"] = bool(
        flags.get("post_procedure") or flags.get("eczema") or flags.get("rosacea") or flags.get("retinoid_user")
    )
    return flags

