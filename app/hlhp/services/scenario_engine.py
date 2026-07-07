"""SFI scoring and Master-cell lookup from the scenario library."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from app.hlhp.evidence.scenario_store import ScenarioStore
from app.hlhp.evidence.scenario_workbook import slug
from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.models.profile import SkinConcern, SkinType, UserProfile, Gender

SeverityBandName = Literal[
    "Paradise Mode",
    "Smooth Sailing",
    "Guard Up",
    "Battle Stations",
    "Hostile Mode",
    "Code Red",
]

ImpactLevel = Literal["Low", "Medium", "High"]
TimeWindow = Literal["morning", "daytime", "evening"]

RISK_TO_SFI_SCALE = 4

DRIVER_DEFS = (
    {"factor": "Temperature", "key": "temp", "name": "Heat"},
    {"factor": "UV", "key": "uv", "name": "UV"},
    {"factor": "Humidity", "key": "humidity", "name": "Humidity"},
    {"factor": "AQI", "key": "aqi", "name": "Air (AQI)"},
)

DEFAULT_SKIN = "Combination"
DEFAULT_CONCERN = "Acne"
GUEST_CONCERN = "None"
GUEST_SKIN = "Normal"

COMPOUND_BAND_FIELDS = (
    ("temp_band", "Temperature"),
    ("uv_band", "UV"),
    ("aqi_band", "AQI"),
    ("rh_band", "Humidity"),
)

CONCERN_TO_LIBRARY: dict[SkinConcern, str] = {
    SkinConcern.ACNE: "Acne",
    SkinConcern.MELASMA: "Melasma",
    SkinConcern.PIGMENTATION: "Dark Marks (Post-Acne / PIH)",
    SkinConcern.DULLNESS: "Uneven Skin Tone / Tan",
    SkinConcern.TAN: "Uneven Skin Tone / Tan",
    SkinConcern.AGING: "Premature Aging / Sun Damage",
    SkinConcern.DEHYDRATION: "Dryness",
    SkinConcern.REDNESS: "Eczema",
    SkinConcern.SENSITIVITY: "Eczema",
    SkinConcern.DARK_CIRCLES: "Dark Circles (Periorbital)",
    SkinConcern.PORES: "Oily Skin",
    SkinConcern.TEXTURE: "Dark Marks (Post-Acne / PIH)",
    SkinConcern.FUNGAL: "Fungal Infection (Sweat & Folds)",
    SkinConcern.HEAT_RASH: "Heat Rash (Prickly Heat)",
}

SKIN_TO_LIBRARY: dict[SkinType, str] = {
    SkinType.COMBINATION: "Combination",
    SkinType.DRY: "Dry",
    SkinType.NORMAL: "Normal",
    SkinType.OILY: "Oily",
    SkinType.SENSITIVE: "Sensitive",
}

SUDDEN_TAG_BY_FACTOR = {
    "Temperature": "heat_surge",
    "Humidity": "humidity_surge",
    "AQI": "pollution_surge",
    "UV": "uv_surge",
}


@dataclass(frozen=True)
class DriverState:
    factor: str
    key: str
    name: str
    value: float
    band_label: str
    band_key: str
    band_range: str
    points: int


@dataclass(frozen=True)
class ImpactLine:
    driver: str
    name: str
    level: ImpactLevel
    value: float


@dataclass(frozen=True)
class FlashAlert:
    level: Literal["L0", "L1"]
    mode: SeverityBandName
    l0: str
    l1: str
    tip: str


@dataclass(frozen=True)
class EvidenceCellOut:
    id: str
    factor: str
    band: str
    evidence: str
    pmids: list[str]
    confidence: str
    action: str


@dataclass(frozen=True)
class ScenarioEvaluation:
    sfi: int
    band: SeverityBandName
    personal_sfi: int | None
    drivers: list[DriverState]
    dominant: DriverState
    impacts: list[ImpactLine]
    cell: dict[str, Any] | None
    flash_alert: FlashAlert
    evidence_cell: EvidenceCellOut | None
    action_cluster: str
    risk: int
    risk_label: str
    confidence: str
    zone: str | None
    skin: str
    concern: str
    sudden_event_tags: list[str]
    cell_kind: str = "master"
    compound_name: str | None = None
    time_window: TimeWindow | None = None
    life_stage: str | None = None


def value_in_band(range_str: str, val: float) -> bool:
    r = str(range_str).replace("°C", "").replace("%", "").replace("–", "-").replace("—", "-").strip()
    if r.startswith("<"):
        return val < float(r[1:])
    if r.endswith("+"):
        return val >= float(r[:-1])
    if r.startswith(">"):
        return val > float(r.replace(">", ""))
    if "-" in r:
        lo_s, hi_s = r.split("-", 1)
        return float(lo_s) <= val <= float(hi_s)
    return False


def band_for_value(store: ScenarioStore, factor: str, val: float) -> dict[str, Any]:
    rows = store.bands.get(factor, [])
    for row in rows:
        if value_in_band(str(row.get("range", "")), val):
            return row
    return rows[-1] if rows else {"label": "?", "range": "", "points": 0, "key": "unknown"}


def driver_states(store: ScenarioStore, env: EnvironmentalData) -> list[DriverState]:
    values = {
        "Temperature": env.temperature_c,
        "UV": env.uv_index,
        "Humidity": env.humidity_pct,
        "AQI": float(env.aqi),
    }
    out: list[DriverState] = []
    for d in DRIVER_DEFS:
        band = band_for_value(store, d["factor"], values[d["factor"]])
        pts = band.get("points")
        out.append(
            DriverState(
                factor=d["factor"],
                key=d["key"],
                name=d["name"],
                value=values[d["factor"]],
                band_label=str(band.get("label", "")),
                band_key=str(band.get("key", "")),
                band_range=str(band.get("range", "")),
                points=int(pts) if isinstance(pts, (int, float)) else 0,
            )
        )
    return out


def compute_sfi(store: ScenarioStore, env: EnvironmentalData) -> int:
    return sum(d.points for d in driver_states(store, env))


def band_for_sfi(sfi: int) -> SeverityBandName:
    if sfi >= 85:
        return "Paradise Mode"
    if sfi >= 70:
        return "Smooth Sailing"
    if sfi >= 55:
        return "Guard Up"
    if sfi >= 40:
        return "Battle Stations"
    if sfi >= 25:
        return "Hostile Mode"
    return "Code Red"


def points_to_level(points: int) -> ImpactLevel:
    if points >= 20:
        return "Low"
    if points >= 10:
        return "Medium"
    return "High"


def clamp_sfi(value: int) -> int:
    return max(0, min(100, value))


def time_window_for_datetime(when: datetime | None, tz: str = "Asia/Kolkata") -> TimeWindow:
    """3-window model from the Time Overlay sheet (hour < 9 / 9–16 / ≥16 local)."""
    dt = when or datetime.now(ZoneInfo(tz))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(tz))
    else:
        dt = dt.astimezone(ZoneInfo(tz))
    hour = dt.hour
    if hour < 9:
        return "morning"
    if hour < 16:
        return "daytime"
    return "evening"


def resolve_life_stage(profile: UserProfile | None) -> str | None:
    if profile is None:
        return None
    if profile.life_stage:
        return profile.life_stage
    if profile.gender == Gender.MALE:
        return "Male"
    if profile.gender in {Gender.FEMALE, Gender.NON_BINARY, Gender.OTHER, Gender.PREFER_NOT_TO_SAY}:
        return "Female"
    return None


def lookup_gender_rule(
    store: ScenarioStore,
    life_stage: str | None,
    concern: str,
) -> dict[str, Any] | None:
    if not life_stage or not concern or concern == GUEST_CONCERN:
        return None
    return store.gender_rules.get(f"{slug(life_stage)}|{slug(concern)}")


def time_overlay_clause(
    store: ScenarioStore,
    dom: DriverState,
    window: TimeWindow,
) -> str:
    if window == "daytime":
        return ""
    overlay = store.time_overlay.get(f"{slug(dom.factor)}|{dom.band_key}")
    if not overlay:
        return ""
    if window == "morning":
        return str(overlay.get("morning", "") or "")
    return str(overlay.get("evening", "") or "")


def apply_gender_rule_to_sfi(sfi: int, rule: dict[str, Any] | None) -> int:
    if not rule:
        return sfi
    delta = rule.get("risk_delta")
    if not isinstance(delta, (int, float)) or delta <= 0:
        return sfi
    return clamp_sfi(sfi - int(delta) * RISK_TO_SFI_SCALE)


def dominant_driver(drivers: list[DriverState]) -> DriverState:
    return sorted(drivers, key=lambda d: d.points)[0]


def resolve_skin(profile: UserProfile | None, guest_mode: bool) -> str:
    if guest_mode:
        if profile and profile.skin_type:
            return SKIN_TO_LIBRARY.get(profile.skin_type, GUEST_SKIN)
        return GUEST_SKIN
    if profile:
        return SKIN_TO_LIBRARY.get(profile.skin_type, DEFAULT_SKIN)
    return DEFAULT_SKIN


def resolve_library_concerns(profile: UserProfile | None, guest_mode: bool) -> list[str]:
    if guest_mode:
        return [GUEST_CONCERN]
    if not profile or not profile.skin_concerns:
        return [DEFAULT_CONCERN]
    seen: set[str] = set()
    out: list[str] = []
    for concern in profile.skin_concerns:
        mapped = CONCERN_TO_LIBRARY.get(concern)
        if mapped and mapped not in seen:
            seen.add(mapped)
            out.append(mapped)
    return out or [DEFAULT_CONCERN]


def resolve_concern(profile: UserProfile | None, guest_mode: bool) -> str:
    return resolve_library_concerns(profile, guest_mode)[0]


def _drivers_by_factor(drivers: list[DriverState]) -> dict[str, DriverState]:
    return {d.factor: d for d in drivers}


def match_compound_index(
    store: ScenarioStore,
    drivers: list[DriverState],
    *,
    zone: str | None,
) -> dict[str, Any] | None:
    by_factor = _drivers_by_factor(drivers)
    matches: list[dict[str, Any]] = []
    for row in store.compounds:
        if not _compound_index_matches(row, by_factor):
            continue
        if zone and row.get("zones"):
            zones = {z.strip().upper() for z in row.get("zones", []) if z}
            if zones and zone.upper() not in zones:
                continue
        matches.append(row)
    if not matches:
        return None
    matches.sort(key=lambda r: len(r.get("drivers") or []), reverse=True)
    return matches[0]


def _compound_index_matches(row: dict[str, Any], by_factor: dict[str, DriverState]) -> bool:
    for field, factor in COMPOUND_BAND_FIELDS:
        expected = norm_band_label(str(row.get(field, "")))
        if not expected or expected.lower() == "any":
            continue
        actual = norm_band_label(by_factor[factor].band_label)
        if expected != actual:
            return False
    return True


def norm_band_label(label: str) -> str:
    return label.split("(")[0].strip().lower()


def lookup_compound_cell(
    store: ScenarioStore,
    scenario_name: str,
    skin: str,
    concern: str,
) -> dict[str, Any] | None:
    keys = [
        f"{slug(scenario_name)}|{slug(skin)}|{slug(concern)}",
        f"{slug(scenario_name)}|{slug(skin)}|acne",
        f"{slug(scenario_name)}|normal|{slug(concern)}",
    ]
    for key in keys:
        cell = store.compound_cells.get(key)
        if cell:
            return cell
    return None


def lookup_guest_single_cell(
    store: ScenarioStore,
    drivers: list[DriverState],
    skin: str,
) -> dict[str, Any] | None:
    dom = dominant_driver(drivers)
    keys = [
        f"single|{slug(dom.factor)}|{dom.band_key}|{slug(skin)}|none",
        f"single|{slug(dom.factor)}|{dom.band_key}|normal|none",
        f"single|{slug(dom.factor)}|{dom.band_key}|combination|none",
    ]
    for key in keys:
        cell = store.guest.get(key)
        if cell:
            return cell
    return None


def lookup_guest_compound_cell(
    store: ScenarioStore,
    scenario_name: str,
    skin: str,
) -> dict[str, Any] | None:
    keys = [
        f"compound|{slug(scenario_name)}|{slug(skin)}|none",
        f"compound|{slug(scenario_name)}|normal|none",
    ]
    for key in keys:
        cell = store.guest.get(key)
        if cell:
            return cell
    return None


def resolve_alert_cell(
    store: ScenarioStore,
    drivers: list[DriverState],
    *,
    skin: str,
    concern: str,
    guest_mode: bool,
    zone: str | None,
    concern_candidates: list[str] | None = None,
) -> tuple[dict[str, Any] | None, str, str | None]:
    """Return (cell, cell_kind, compound_name)."""
    compound_index = match_compound_index(store, drivers, zone=zone)
    compound_name = str(compound_index.get("name", "")) if compound_index else None
    candidates = concern_candidates or [concern]

    if guest_mode:
        if compound_name:
            cell = lookup_guest_compound_cell(store, compound_name, skin)
            if cell:
                return cell, "guest_compound", compound_name
        cell = lookup_guest_single_cell(store, drivers, skin)
        if cell:
            return cell, "guest_single", None
        return None, "guest_single", None

    for concern_name in candidates:
        if compound_name:
            cell = lookup_compound_cell(store, compound_name, skin, concern_name)
            if cell:
                return cell, "compound", compound_name
        cell = lookup_master_cell(store, drivers, skin, concern_name)
        if cell:
            return cell, "master", compound_name
    return None, "master", compound_name


def lookup_master_cell(
    store: ScenarioStore,
    drivers: list[DriverState],
    skin: str,
    concern: str,
) -> dict[str, Any] | None:
    dom = dominant_driver(drivers)
    keys = [
        f"{slug(dom.factor)}|{dom.band_key}|{slug(skin)}|{slug(concern)}",
        f"{slug(dom.factor)}|{dom.band_key}|{slug(skin)}|acne",
        f"{slug(dom.factor)}|{dom.band_key}|normal|{slug(concern)}",
    ]
    for key in keys:
        cell = store.master.get(key)
        if cell:
            return cell
    return None


def _risk_int(cell: dict[str, Any] | None, *, surge: bool) -> int:
    if cell and isinstance(cell.get("risk"), (int, float)):
        return int(cell["risk"])
    return 3 if surge else 1


def build_flash_alert(
    cell: dict[str, Any] | None,
    *,
    band: SeverityBandName,
    surge: bool,
    time_clause: str = "",
    gender_rule: dict[str, Any] | None = None,
) -> FlashAlert:
    if cell:
        l1_base = str(cell.get("l2" if surge else "l1", ""))
        l1_parts = [part for part in (l1_base, time_clause, str(gender_rule.get("addendum", "")) if gender_rule else "") if part]
        l1 = " ".join(l1_parts)
        if gender_rule and gender_rule.get("action"):
            tip = str(gender_rule["action"])
        else:
            tip = f"Action focus: {cell.get('action', 'Maintain')}."
        return FlashAlert(
            level="L1" if surge else "L0",
            mode=band,
            l0=str(cell.get("l0", "")),
            l1=l1,
            tip=tip,
        )
    l1_parts = [part for part in ("Environmental stress is elevated for your area right now.", time_clause) if part]
    return FlashAlert(
        level="L1" if surge else "L0",
        mode=band,
        l0="Weather shift — check your skin today.",
        l1=" ".join(l1_parts),
        tip="Stay shaded, hydrated, and keep your routine light.",
    )


def evaluate_scenario(
    store: ScenarioStore,
    env: EnvironmentalData,
    *,
    city: str,
    profile: UserProfile | None = None,
    guest_mode: bool = True,
    force_surge: bool = False,
    local_time: datetime | None = None,
) -> ScenarioEvaluation:
    drivers = driver_states(store, env)
    sfi = sum(d.points for d in drivers)
    dom = dominant_driver(drivers)
    skin = resolve_skin(profile, guest_mode)
    library_concerns = resolve_library_concerns(profile, guest_mode)
    concern = library_concerns[0]
    zone = store.city_zone.get((city or "").lower())
    cell, cell_kind, compound_name = resolve_alert_cell(
        store,
        drivers,
        skin=skin,
        concern=concern,
        guest_mode=guest_mode,
        zone=zone,
        concern_candidates=library_concerns,
    )

    life_stage = None if guest_mode else resolve_life_stage(profile)
    gender_rule = lookup_gender_rule(store, life_stage, concern)
    sfi = apply_gender_rule_to_sfi(sfi, gender_rule)
    band = band_for_sfi(sfi)
    time_window = time_window_for_datetime(local_time)
    time_clause = time_overlay_clause(store, dom, time_window)

    risk = _risk_int(cell, surge=force_surge)
    personal_sfi = clamp_sfi(sfi - risk * RISK_TO_SFI_SCALE) if cell else None
    flash = build_flash_alert(
        cell,
        band=band,
        surge=force_surge,
        time_clause=time_clause,
        gender_rule=gender_rule,
    )
    impacts = [
        ImpactLine(driver=d.key, name=d.name, level=points_to_level(d.points), value=d.value)
        for d in drivers
    ]

    evidence_cell = None
    if cell:
        factor = str(cell.get("factor") or cell.get("scenario") or dom.factor)
        evidence_cell = EvidenceCellOut(
            id=str(cell.get("id", "")),
            factor=factor,
            band=str(cell.get("band", "")),
            evidence=str(cell.get("evidence", "")),
            pmids=list(cell.get("pmids") or []),
            confidence=str(cell.get("confidence", "")),
            action=str(cell.get("action", "")),
        )

    sudden: list[str] = []
    if force_surge:
        sudden.append(SUDDEN_TAG_BY_FACTOR.get(dom.factor, "heat_surge"))
    if cell_kind in {"compound", "guest_compound"} and compound_name:
        sudden.append(compound_name.lower().replace(" ", "_")[:32])

    return ScenarioEvaluation(
        sfi=sfi,
        band=band,
        personal_sfi=personal_sfi,
        drivers=drivers,
        dominant=dom,
        impacts=impacts,
        cell=cell,
        flash_alert=flash,
        evidence_cell=evidence_cell,
        action_cluster=str(cell.get("action", "Maintain")) if cell else "Maintain",
        risk=risk,
        risk_label=str(cell.get("risk_level", "High" if force_surge else "Low")) if cell else ("High" if force_surge else "Low"),
        confidence=str(cell.get("confidence", "Calibrated")) if cell else "Calibrated",
        zone=zone,
        skin=skin,
        concern=concern,
        sudden_event_tags=sudden,
        cell_kind=cell_kind,
        compound_name=compound_name,
        time_window=time_window,
        life_stage=life_stage,
    )


def severity_for_risk(risk: int) -> Literal["BLOCK_ENV", "HARD_ENV", "SOFT_ENV"]:
    if risk >= 4:
        return "BLOCK_ENV"
    if risk >= 2:
        return "HARD_ENV"
    return "SOFT_ENV"
