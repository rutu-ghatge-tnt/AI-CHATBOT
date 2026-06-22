"""Headline quality gates — publishable L1, env-coherent copy, consumer did-you-know."""

from __future__ import annotations

import re

from app.hlhp.core.bands import EnvironmentBands
from app.hlhp.core.phase import DayPhase
from app.hlhp.evidence.models import EvidenceFinding
from app.hlhp.models.profile import UserProfile

_COLD_COPY = re.compile(
    r"\b(cold air|chilly|chill factor|frost|freezing|winter bite|icy)\b",
    re.I,
)
_HEAT_COPY = re.compile(
    r"\b(scorch|heat wave|blazing sun|sunburn risk|spf now)\b",
    re.I,
)
_PEDiatric = re.compile(
    r"\b(pediatric|teen skin|adolescent|school-age|child(?:ren)?'?s skin)\b",
    re.I,
)
_WARM_TEMP_BANDS = frozenset({"comfortable", "warm", "hot", "very_hot"})
_COLD_TEMP_BANDS = frozenset({"very_cold", "cold"})
_HEADLINE_EDUCATION_RE = re.compile(
    r"\b("
    r"varies hugely|on average|doesn't fully translate|measurably darker|"
    r"differs from west|prevalence (?:in|was)|constitutive melanin|"
    r"testing on caucasian|skin colour varies|skin color varies"
    r")\b",
    re.I,
)
_BROKEN_TEMPLATE_RE = re.compile(
    r"\babout much\b|\{[a-z_]+\}|,\s*ajit\b",
    re.I,
)
_TEEN_COPY = re.compile(
    r"\b(teens?|adolescent|neonatal|newborn|school-age)\b",
    re.I,
)


def effective_l1(finding: EvidenceFinding, *, guest_mode: bool, day_phase: DayPhase) -> str:
    return (finding.pick_l1(guest_mode=guest_mode, day_phase=day_phase) or "").strip()


def is_publishable_l1(text: str) -> bool:
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    if _BROKEN_TEMPLATE_RE.search(cleaned):
        return False
    words = cleaned.split()
    return len(words) >= 4 or len(cleaned) >= 18


def is_publishable_finding(
    finding: EvidenceFinding,
    *,
    guest_mode: bool,
    day_phase: DayPhase,
) -> bool:
    if not finding.is_surfaced_to_client():
        return False
    return is_publishable_l1(effective_l1(finding, guest_mode=guest_mode, day_phase=day_phase))


def _finding_text_blob(finding: EvidenceFinding) -> str:
    return " ".join(
        part
        for part in (
            finding.sub_effect,
            finding.alert_short,
            finding.product_implication,
            finding.mechanism,
            finding.symptom_keyword or "",
        )
        if part
    ).lower()


def pediatric_mismatch_penalty(finding: EvidenceFinding, profile: UserProfile | None) -> float:
    if profile is None:
        return 0.0
    blob = _finding_text_blob(finding)
    l1 = effective_l1(finding, guest_mode=False, day_phase="morning").lower()
    if not _PEDiatric.search(blob) and not _PEDiatric.search(l1):
        return 0.0
    # All captured v2 brackets are adult-facing (18+).
    return -180.0


def temp_copy_penalty(
    finding: EvidenceFinding,
    temp_band: str,
    *,
    guest_mode: bool,
    day_phase: DayPhase,
) -> float:
    l1 = effective_l1(finding, guest_mode=guest_mode, day_phase=day_phase)
    if not l1:
        return 0.0
    if temp_band in _WARM_TEMP_BANDS and _COLD_COPY.search(l1):
        return -200.0
    if temp_band in _COLD_TEMP_BANDS and _HEAT_COPY.search(l1):
        return -80.0
    return 0.0


def _env_trigger_specific(finding: EvidenceFinding, bands: EnvironmentBands) -> bool:
    """True when the row is tied to at least one of today's env bands (not all-any)."""
    from app.hlhp.evidence.matcher import _band_matches

    checks = (
        (finding.uvi_bands, bands.uvi),
        (finding.aqi_bands, bands.aqi),
        (finding.rh_bands, bands.humidity),
        (finding.temp_bands, bands.temperature),
    )
    return any(
        dims and dims != ("any",) and _band_matches(dims, current)
        for dims, current in checks
    )


def _is_background_physiology_row(finding: EvidenceFinding) -> bool:
    tag = (finding.outcome_tag or "").strip().lower()
    if tag == "physiology":
        return True
    return tag.startswith("physiology") and "concern" not in tag


def is_headline_eligible(
    finding: EvidenceFinding,
    *,
    profile: UserProfile | None,
    bands: EnvironmentBands | None,
    guest_mode: bool,
    day_phase: DayPhase,
) -> bool:
    """Hyper-local HLHP headline gate — personalised users need profile + today's env."""
    if not is_publishable_finding(finding, guest_mode=guest_mode, day_phase=day_phase):
        return False
    if guest_mode:
        return True
    if profile is None:
        return False
    if not finding.user_filter:
        return False
    if _is_background_physiology_row(finding):
        return False
    l1 = effective_l1(finding, guest_mode=False, day_phase=day_phase)
    if _HEADLINE_EDUCATION_RE.search(l1):
        return False
    if _TEEN_COPY.search(l1):
        return False
    if bands is not None and not _env_trigger_specific(finding, bands):
        return False
    return True


def headline_slot_penalty(
    finding: EvidenceFinding,
    profile: UserProfile | None,
    bands: EnvironmentBands | None,
    *,
    guest_mode: bool,
    day_phase: DayPhase,
) -> float:
    penalty = 0.0
    penalty += pediatric_mismatch_penalty(finding, profile)
    if bands is not None:
        penalty += temp_copy_penalty(
            finding, bands.temperature, guest_mode=guest_mode, day_phase=day_phase
        )
    return penalty


def _is_bullet_or_internal(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 24:
        return True
    if t.count(";") >= 2:
        return True
    if ";" in t and "." not in t:
        return True
    lowered = t.lower()
    if "rationalised" in lowered or "workbook" in lowered:
        return True
    return False


def is_consumer_copy(text: str) -> bool:
    t = (text or "").strip()
    if not t or _is_bullet_or_internal(t):
        return False
    return len(t.split()) >= 6


def pick_display_l2(finding: EvidenceFinding) -> str:
    if finding.alert_l2_explainer and is_consumer_copy(finding.alert_l2_explainer):
        return finding.alert_l2_explainer
    if finding.mechanism and is_consumer_copy(finding.mechanism):
        return finding.mechanism
    if finding.quantified and is_consumer_copy(finding.quantified):
        return finding.quantified
    raw = finding.pick_l2()
    return raw or ""


def pick_did_you_know(finding: EvidenceFinding, *, l2: str) -> str | None:
    l2_norm = (l2 or "").strip().lower()
    for candidate in (
        finding.physical_analogy,
        finding.body_sensation_decode,
        finding.alert_l2_explainer,
        finding.mechanism,
        finding.quantified,
    ):
        if not candidate or not is_consumer_copy(candidate):
            continue
        if candidate.strip().lower() == l2_norm:
            continue
        return candidate.strip()
    return None
