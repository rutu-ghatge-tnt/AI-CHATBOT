from __future__ import annotations

import functools
from pathlib import Path

import yaml

from app.label_looker.engines.base_formula.types import MatrixScore

CONFIG_DIR = Path(__file__).parent / "configs"
_TIER_ORDER: list[MatrixScore] = ["avoid", "poor", "ok", "good", "excellent"]


@functools.lru_cache(maxsize=32)
def load_config(filename: str) -> dict:
    with (CONFIG_DIR / filename).open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _apply_tier_delta(score: MatrixScore, delta: int) -> MatrixScore:
    idx = _TIER_ORDER.index(score) if score in _TIER_ORDER else 2
    new_idx = max(0, min(len(_TIER_ORDER) - 1, idx + delta))
    return _TIER_ORDER[new_idx]


def lookup_texture_score(texture: str, skin_type: str, season: str) -> tuple[MatrixScore, str]:
    config = load_config("texture_x_skin.yaml")
    base = config.get("matrix", {}).get(texture, {}).get(skin_type, "ok")
    delta = config.get("climate_modifiers", {}).get(season, {}).get(texture)
    if isinstance(delta, int):
        adjusted = _apply_tier_delta(base, delta)
        if adjusted != base:
            direction = "promoted" if delta > 0 else "demoted"
            return adjusted, f"{texture} {direction} from {base} to {adjusted} for {season}"
    return base, f"{texture} × {skin_type} → {base}"


def lookup_carrier_score(carrier: str, skin_type: str, season: str, is_acne_prone: bool) -> tuple[MatrixScore, str]:
    config = load_config("carrier_x_skin.yaml")
    base = config.get("matrix", {}).get(carrier, {}).get(skin_type, "ok")
    if carrier == "silicone" and is_acne_prone and season in {"jul_sep", "apr_jun"}:
        delta_key = "monsoon_acne_prone" if season == "jul_sep" else "summer_hot_humid_acne_prone"
        delta = config.get("india_overrides", {}).get("silicone", {}).get(delta_key)
        if isinstance(delta, int):
            adjusted = _apply_tier_delta(base, delta)
            return adjusted, "silicone-continuous demoted for acne-prone humidity context"
    return base, f"{carrier} × {skin_type} → {base}"


def lookup_fragrance_score(fragrance_level: str, flags: dict) -> tuple[MatrixScore, str]:
    config = load_config("fragrance_x_sensitivity.yaml")
    if flags.get("barrier_compromised") or flags.get("post_procedure") or flags.get("retinoid_user"):
        col = "barrier_compromised"
    elif flags.get("eczema") or flags.get("rosacea"):
        col = "eczema_or_rosacea"
    elif flags.get("sensitive_skin"):
        col = "sensitive_self_report"
    else:
        col = "no_sensitivity"
    score = config.get("matrix", {}).get(fragrance_level, {}).get(col, "ok")
    return score, f"fragrance ({fragrance_level}) × sensitivity ({col}) → {score}"


def lookup_alcohol_score(alcohol_level: str, skin_type: str, flags: dict) -> tuple[MatrixScore, str]:
    config = load_config("alcohol_x_skin.yaml")
    if skin_type in ("dry", "very_dry") or flags.get("barrier_compromised"):
        col = "dry_or_compromised"
    elif skin_type == "oily" and flags.get("dehydrated_oily"):
        col = "oily_dehydrated"
    elif skin_type == "oily":
        col = "oily_hydrated"
    elif skin_type == "combination":
        col = "combination"
    else:
        col = "normal"
    score = config.get("matrix", {}).get(alcohol_level, {}).get(col, "ok")
    return score, f"alcohol ({alcohol_level}) × {col} → {score}"


def lookup_finish_score(finish: str, skin_type: str) -> tuple[MatrixScore, str]:
    config = load_config("finish_x_skin.yaml")
    score = config.get("matrix", {}).get(finish, {}).get(skin_type, "ok")
    return score, f"finish ({finish}) × {skin_type} → {score}"

