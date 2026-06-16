from __future__ import annotations

from typing import Optional

from app.hlhp.core.bands import EnvironmentBands
from app.hlhp.evidence.index import EvidenceIndex
from app.hlhp.evidence.gates import guest_gate_blocks, night_gate_blocks
from app.hlhp.evidence.models import EvidenceFinding, UserFilterToken
from app.hlhp.models.profile import (
    AgeBracket,
    SkinConcern,
    SkinGoal,
    SleepTime,
    SmokingStatus,
    StressLevel,
    UserProfile,
)

_CONCERN_ALIASES: dict[str, set[str]] = {
    "eczema": {"sensitivity", "eczema", "atopic-flare"},
    "sensitive": {"sensitivity", "sensitive", "eczema"},
    "dryness": {"dehydration", "dryness", "xerosis"},
    "photoaging": {"aging", "photoaging"},
    "pih": {"pigmentation", "pih"},
    "xerosis": {"dehydration", "xerosis"},
    "sensitive-acne-overlap": {"acne", "sensitivity"},
    "psoriasis": {"psoriasis", "eczema", "sensitivity"},
    "rosacea": {"rosacea", "redness", "sensitivity"},
    "large_pores": {"pores", "texture", "large_pores"},
    "hair_loss": {"hair_loss", "thinning"},
    "dehydration-oily-paradox": {"dehydration", "dehydration-oily-paradox"},
}

_AGE_BRACKET_RANGES: dict[AgeBracket, tuple[int, int]] = {
    AgeBracket.AGE_18_24: (18, 24),
    AgeBracket.AGE_25_30: (25, 30),
    AgeBracket.AGE_31_40: (31, 40),
    AgeBracket.AGE_41_50: (41, 50),
    AgeBracket.AGE_50_PLUS: (50, 120),
}

_SLEEP_BANDS: dict[SleepTime, str] = {
    SleepTime.LESS_THAN_5H: "severely_deprived",
    SleepTime.H5_6H: "deprived",
    SleepTime.H6_7H: "low",
    SleepTime.H7_9H: "optimal",
    SleepTime.MORE_THAN_9H: "excess",
}


def _band_matches(allowed: tuple[str, ...], current: str) -> bool:
    if not allowed or allowed == ("any",):
        return True
    return current in allowed


def _parse_age_range(value: str) -> tuple[int, int] | None:
    value = value.strip().lower()
    if value in {"all", "any"}:
        return None
    if value.endswith("+"):
        return int(value[:-1]), 120
    if "-" in value:
        lo, hi = value.split("-", 1)
        return int(lo), int(hi)
    return int(value), int(value)


def _age_overlaps(profile: UserProfile, filter_value: str) -> bool:
    parsed = _parse_age_range(filter_value)
    if parsed is None:
        return True
    p_lo, p_hi = _AGE_BRACKET_RANGES[profile.age_bracket]
    f_lo, f_hi = parsed
    return p_lo <= f_hi and f_lo <= p_hi


def _concern_values(profile: UserProfile) -> set[str]:
    return {c.value for c in profile.skin_concerns}


def _concern_matches(profile: UserProfile, filter_value: str) -> bool:
    concerns = _concern_values(profile)
    if filter_value in concerns:
        return True
    aliases = _CONCERN_ALIASES.get(filter_value, {filter_value})
    return bool(concerns & aliases)


def _token_matches(
    token: UserFilterToken,
    profile: Optional[UserProfile],
    partial_personalised: bool,
) -> bool:
    if token.class_name == "flag":
        return True

    if profile is None:
        return False

    if token.class_name == "concern":
        return _concern_matches(profile, token.value)

    if token.class_name == "skin_type":
        if token.value in {"iii-v", "iii", "iv", "v", "iii-vi", "all", "any"}:
            return True
        return profile.skin_type.value == token.value

    if token.class_name == "gender":
        if token.value == "female":
            return profile.gender.value in {"female", "non_binary"}
        if token.value == "male":
            return profile.gender.value == "male"
        return profile.gender.value == token.value

    if token.class_name == "age":
        return _age_overlaps(profile, token.value)

    if token.class_name == "smoking":
        if profile.smoking_status is None:
            return partial_personalised
        return profile.smoking_status.value == token.value

    if token.class_name == "stress":
        if profile.stress_level is None:
            return partial_personalised
        return profile.stress_level.value == token.value

    if token.class_name == "sleep":
        if profile.sleep_time is None:
            return partial_personalised
        return _SLEEP_BANDS.get(profile.sleep_time, "") == token.value

    if token.class_name == "goal":
        if profile.skin_goal is None:
            return partial_personalised
        return profile.skin_goal.value == token.value

    return partial_personalised


def count_matched_tokens(
    finding: EvidenceFinding,
    profile: Optional[UserProfile],
    partial_personalised: bool,
) -> int:
    if not finding.user_filter:
        return 0
    if profile is None:
        return 0
    return sum(
        1
        for token in finding.user_filter
        if _token_matches(token, profile, partial_personalised)
    )


def user_filter_matches(
    finding: EvidenceFinding,
    profile: Optional[UserProfile],
    *,
    guest_mode: bool,
    partial_personalised: bool = False,
) -> bool:
    if guest_mode:
        return len(finding.user_filter) == 0
    if not finding.user_filter:
        return True
    if profile is None:
        return False
    return all(
        _token_matches(token, profile, partial_personalised) for token in finding.user_filter
    )


def matches_finding(
    finding: EvidenceFinding,
    *,
    season: str,
    bands: EnvironmentBands,
    profile: Optional[UserProfile],
    guest_mode: bool,
    partial_personalised: bool = False,
) -> bool:
    if finding.never_fire:
        return False
    if night_gate_blocks(finding, bands.uvi):
        return False
    if guest_gate_blocks(finding, guest_mode):
        return False
    if not _band_matches(finding.season_bands, season):
        return False
    if not _band_matches(finding.uvi_bands, bands.uvi):
        return False
    if not _band_matches(finding.aqi_bands, bands.aqi):
        return False
    if not _band_matches(finding.rh_bands, bands.humidity):
        return False
    if not _band_matches(finding.temp_bands, bands.temperature):
        return False
    return user_filter_matches(
        finding,
        profile,
        guest_mode=guest_mode,
        partial_personalised=partial_personalised,
    )


def match_findings(
    findings: list[EvidenceFinding],
    *,
    season: str,
    bands: EnvironmentBands,
    profile: Optional[UserProfile] = None,
    guest_mode: bool = True,
    partial_personalised: bool = False,
    index: EvidenceIndex | None = None,
) -> list[EvidenceFinding]:
    if index is not None:
        candidate_ids = index.candidate_ids(
            season=season,
            uvi=bands.uvi,
            aqi=bands.aqi,
            humidity=bands.humidity,
            temperature=bands.temperature,
        )
        pool = [index.findings_by_id[i] for i in candidate_ids if i in index.findings_by_id]
    else:
        pool = findings
    return [
        row
        for row in pool
        if matches_finding(
            row,
            season=season,
            bands=bands,
            profile=profile,
            guest_mode=guest_mode,
            partial_personalised=partial_personalised,
        )
    ]
