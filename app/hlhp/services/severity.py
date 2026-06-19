"""Severity ladder per HLHP Engine Implementation Spec v2 §4."""

from __future__ import annotations

from typing import Literal

from app.hlhp.core.bands import EnvironmentBands
from app.hlhp.evidence.models import EvidenceFinding

Severity = Literal["BLOCK_ENV", "HARD_ENV", "SOFT_ENV", "NONE"]

_SEVERITY_RANK = {"BLOCK_ENV": 3, "HARD_ENV": 2, "SOFT_ENV": 1, "NONE": 0}


def _factor_strength(band: str, dimension: str) -> int:
    ladders = {
        "uvi": {"off": 0, "low": 0, "moderate": 1, "high": 2, "very_high": 3, "extreme": 4},
        "aqi": {
            "good": 0,
            "satisfactory": 0,
            "moderate": 1,
            "poor": 2,
            "very_poor": 3,
            "severe": 4,
        },
        "temp": {
            "very_cold": 3,
            "cold": 2,
            "comfortable": 0,
            "warm": 1,
            "hot": 2,
            "very_hot": 4,
        },
        "rh": {
            "very_low": 3,
            "low": 2,
            "comfortable": 0,
            "moderate": 1,
            "high": 2,
            "very_high": 3,
        },
    }
    return ladders.get(dimension, {}).get(band, 1)


def severity_for_finding(finding: EvidenceFinding, bands: EnvironmentBands) -> Severity:
    """Severity for a matched rule based on live env stress for its factor."""
    factor_map = {
        "UV": ("uvi", bands.uvi),
        "Pollution": ("aqi", bands.aqi),
        "Temperature": ("temp", bands.temperature),
        "Humidity": ("rh", bands.humidity),
    }
    dim, band = factor_map.get(finding.factor, ("uvi", bands.uvi))
    strength = _factor_strength(band, dim)
    if strength >= 4:
        return "BLOCK_ENV"
    if strength >= 3:
        return "HARD_ENV"
    if strength >= 1:
        return "SOFT_ENV"
    return "SOFT_ENV"


def max_severity(a: Severity, b: Severity) -> Severity:
    return a if _SEVERITY_RANK[a] >= _SEVERITY_RANK[b] else b
