from __future__ import annotations

from app.hlhp.evidence.matcher import count_matched_tokens
from app.hlhp.evidence.models import EvidenceFinding

_PRIORITY_BONUS = {"P0": 100.0, "P1": 50.0, "P2": 20.0}
_INDIA_BONUS = 30.0
_SPECIFICITY_BONUS = 10.0


def rank_score(
    finding: EvidenceFinding,
    *,
    matched_filter_count: int,
) -> float:
    score = _PRIORITY_BONUS.get(finding.priority, 0.0)
    if finding.india_relevant:
        score += _INDIA_BONUS
    score += _SPECIFICITY_BONUS * matched_filter_count
    return score


def rank_findings(
    candidates: list[EvidenceFinding],
    *,
    profile,
    partial_personalised: bool = False,
) -> list[tuple[EvidenceFinding, float, int]]:
    ranked: list[tuple[EvidenceFinding, float, int]] = []
    for finding in candidates:
        matched = count_matched_tokens(finding, profile, partial_personalised)
        score = rank_score(finding, matched_filter_count=matched)
        ranked.append((finding, score, matched))
    ranked.sort(key=lambda item: (-item[1], item[0].row_number))
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
