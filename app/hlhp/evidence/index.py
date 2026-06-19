"""Inverted index for O(candidates) evidence matching."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.hlhp.core.trigger_bands import normalize_rh_band, season_match_tags

_ALL_SEASONS = (
    "winter_dry",
    "winter_humid",
    "pre_monsoon",
    "monsoon",
    "post_monsoon",
    "summer",
    "winter",
    "spring",
    "autumn",
)
_ALL_UVI = ("off", "low", "moderate", "high", "very_high", "extreme")
_ALL_AQI = ("good", "satisfactory", "moderate", "poor", "very_poor", "severe")
_ALL_RH = ("very_low", "low", "moderate", "comfortable", "high", "very_high")
_ALL_TEMP = ("very_cold", "cold", "comfortable", "warm", "hot", "very_hot")

_DIM_VALUES = {
    "season": _ALL_SEASONS,
    "uvi": _ALL_UVI,
    "aqi": _ALL_AQI,
    "rh": _ALL_RH,
    "temp": _ALL_TEMP,
}


def _expand(bands: tuple[str, ...] | list[str], dimension: str) -> set[str]:
    if not bands or bands == ("any",) or bands == ["any"]:
        return set(_DIM_VALUES[dimension])
    out: set[str] = set()
    for b in bands:
        if dimension == "rh":
            b = normalize_rh_band(b)
        if b in _DIM_VALUES[dimension]:
            out.add(b)
    return out or set(_DIM_VALUES[dimension])


def build_inverted_index(findings: list[dict[str, Any]]) -> dict[str, dict[str, list[str]]]:
    """Map each env band value -> finding ids that include that value (or any)."""
    index: dict[str, dict[str, list[str]]] = {
        dim: defaultdict(list) for dim in _DIM_VALUES
    }
    for row in findings:
        row_id = row["id"]
        triggers = row.get("triggers", {})
        for dim, key in (
            ("season", "season"),
            ("uvi", "uvi"),
            ("aqi", "aqi"),
            ("rh", "rh"),
            ("temp", "temp"),
        ):
            for band in _expand(tuple(triggers.get(key, ["any"])), dim):
                index[dim][band].append(row_id)
    return {dim: dict(buckets) for dim, buckets in index.items()}


class EvidenceIndex:
    def __init__(
        self,
        index: dict[str, dict[str, list[str]]],
        findings_by_id: dict[str, Any],
    ) -> None:
        self._index = index
        self.findings_by_id = findings_by_id

    def candidate_ids(
        self,
        *,
        season: str,
        uvi: str,
        aqi: str,
        humidity: str,
        temperature: str,
    ) -> set[str]:
        def ids_for(dim: str, band: str) -> set[str]:
            return set(self._index.get(dim, {}).get(band, []))

        season_ids: set[str] = set()
        for tag in season_match_tags(season):
            season_ids |= ids_for("season", tag)

        rh_band = normalize_rh_band(humidity)
        return (
            season_ids
            & ids_for("uvi", uvi)
            & ids_for("aqi", aqi)
            & ids_for("rh", rh_band)
            & ids_for("temp", temperature)
        )
