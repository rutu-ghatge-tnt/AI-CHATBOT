from __future__ import annotations

from app.hlhp.evidence.matcher import count_matched_tokens
from app.hlhp.evidence.models import EvidenceFinding

_PRIORITY_BONUS = {"P0": 100.0, "P1": 50.0, "P2": 20.0}
_INDIA_BONUS = 30.0
_SPECIFICITY_BONUS = 10.0
_PRIMARY_CONCERN_BONUS = 25.0

_CONCERN_TEXT_HINTS: dict[str, tuple[str, ...]] = {
    "dark_circles": ("dark circle", "under-eye", "under eye", "periorbital"),
    "acne": ("acne", "breakout", "pimple", "comedone"),
    "pigmentation": ("pigment", "melasma", "pih", "spot"),
    "melasma": ("melasma", "patch"),
    "aging": ("wrinkle", "aging", "collagen", "fine line"),
    "dullness": ("dull", "glow", "radiance"),
    "dehydration": ("dehydr", "dryness", "xerosis", "tewl"),
    "sensitivity": ("sensitive", "barrier", "sting", "irritat"),
    "redness": ("redness", "rosacea", "flush"),
    "tan": ("tan", "photoprotect"),
    "pores": ("pore", "sebum"),
    "texture": ("texture", "rough"),
}


def _concern_content_bonus(finding: EvidenceFinding, profile) -> float:
    if profile is None or not profile.skin_concerns:
        return 0.0
    primary = profile.primary_concern.value
    haystack = " ".join(
        part
        for part in (
            finding.sub_effect,
            finding.symptom_keyword or "",
            finding.alert_short or "",
        )
        if part
    ).lower()
    l1_haystack = " ".join(
        part
        for part in (
            finding.alert_l1_personalised,
            finding.alert_l1_guest,
            finding.alert_l1_evening_personalised,
            finding.alert_l1_evening_guest,
        )
        if part
    ).lower()
    hints = _CONCERN_TEXT_HINTS.get(primary, (primary.replace("_", " "),))
    bonus = 0.0
    if any(hint in haystack for hint in hints):
        bonus += 80.0
    if any(hint in l1_haystack for hint in hints):
        bonus += 60.0
    if bonus:
        return bonus
    for token in finding.user_filter:
        if token.class_name == "concern" and token.value == primary:
            return _PRIMARY_CONCERN_BONUS
    return 0.0


def _concern_l1_priority(
    finding: EvidenceFinding,
    profile,
    *,
    day_phase,
    guest_mode: bool = False,
) -> int:
    """Tie-break: prefer the L1 headline the user will actually see."""
    if profile is None or not profile.skin_concerns:
        return 0
    primary = profile.primary_concern.value
    user_hints = tuple(
        h for h in _CONCERN_TEXT_HINTS.get(primary, (primary.replace("_", " "),))
        if h not in {"periorbital"}
    )
    l1 = finding.pick_l1(guest_mode=guest_mode, day_phase=day_phase).lower()
    if l1 and any(h in l1 for h in user_hints):
        return 1
    return 0


def rank_score(
    finding: EvidenceFinding,
    *,
    matched_filter_count: int,
    profile=None,
) -> float:
    score = _PRIORITY_BONUS.get(finding.priority, 0.0)
    if finding.india_relevant:
        score += _INDIA_BONUS
    score += _SPECIFICITY_BONUS * matched_filter_count
    score += _concern_content_bonus(finding, profile)
    return score


def rank_findings(
    candidates: list[EvidenceFinding],
    *,
    profile,
    partial_personalised: bool = False,
    day_phase="morning",
    guest_mode: bool = False,
) -> list[tuple[EvidenceFinding, float, int]]:
    ranked: list[tuple[EvidenceFinding, float, int]] = []
    for finding in candidates:
        matched = count_matched_tokens(finding, profile, partial_personalised)
        score = rank_score(finding, matched_filter_count=matched, profile=profile)
        ranked.append((finding, score, matched))
    ranked.sort(
        key=lambda item: (
            -item[1],
            -_concern_l1_priority(
                item[0], profile, day_phase=day_phase, guest_mode=guest_mode
            ),
            item[0].row_number,
        )
    )
    return ranked


def select_carousel(
    ranked: list[tuple[EvidenceFinding, float, int]],
    *,
    max_slots: int = 5,
) -> list[EvidenceFinding]:
    return _select_diverse(ranked, max_slots=max_slots)


def select_fire_budget(
    ranked: list[tuple[EvidenceFinding, float, int]],
    *,
    headline_slots: int = 3,
    candidate_slots: int = 5,
) -> tuple[list[EvidenceFinding], list[EvidenceFinding]]:
    """v2 §13: 3 surfaced headlines + up to 5 swipe candidates."""
    candidates = _select_diverse(ranked, max_slots=candidate_slots)
    headlines = candidates[:headline_slots]
    return headlines, candidates


def _select_diverse(
    ranked: list[tuple[EvidenceFinding, float, int]],
    *,
    max_slots: int,
) -> list[EvidenceFinding]:
    selected: list[EvidenceFinding] = []
    used_factors: set[str] = set()
    used_sub_effects: set[str] = set()

    for finding, _, _ in ranked:
        if finding.factor in used_factors:
            continue
        key = finding.sub_effect.lower().strip()
        if key and key in used_sub_effects:
            continue
        selected.append(finding)
        used_factors.add(finding.factor)
        if key:
            used_sub_effects.add(key)
        if len(selected) >= max_slots:
            break

    if len(selected) < max_slots:
        for finding, _, _ in ranked:
            if finding in selected:
                continue
            key = finding.sub_effect.lower().strip()
            if key and key in used_sub_effects:
                continue
            selected.append(finding)
            if key:
                used_sub_effects.add(key)
            if len(selected) >= max_slots:
                break
    return selected
