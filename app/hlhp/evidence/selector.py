from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.hlhp.core.bands import bucketize_environment
from app.hlhp.core.phase import DayPhase, phase_used_label, resolve_day_phase
from app.hlhp.core.profile_mode import resolve_mode
from app.hlhp.core.season import indian_season
from app.hlhp.evidence.loader import get_evidence_store
from app.hlhp.evidence.matcher import match_findings
from app.hlhp.evidence.models import (
    EvidenceAlertSummary,
    EvidenceBundle,
    EvidenceFinding,
    EvidenceSelection,
    GapConflictView,
    ScienceNuggetView,
)
from app.hlhp.evidence.nuggets import rotate_by_factor_diversity, rotate_nuggets
from app.hlhp.evidence.ranker import rank_findings, select_carousel
from app.hlhp.evidence.voice import apply_lay_voice
from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.models.profile import UserProfile

_HABIT_FACTORS = {"Nutritional Status", "Lifestyle"}


def _sanitize_l1(text: str, glossary: list[dict]) -> str:
    return apply_lay_voice(text, glossary)


def _to_summary(
    finding: EvidenceFinding,
    l1_text: str,
    *,
    phase_used: str,
) -> EvidenceAlertSummary:
    return EvidenceAlertSummary(
        id=finding.id,
        factor=finding.factor,
        l1_text=l1_text,
        l2_text=finding.pick_l2(),
        priority=finding.priority,
        india_relevant=finding.india_relevant,
        mood_verdict_tag=finding.mood_verdict_tag,
        engagement_archetype=finding.engagement_archetype,
        symptom_keyword=finding.symptom_keyword,
        routine_action=finding.routine_action,
        visual_icon_hint=finding.visual_icon_hint,
        phase_used=phase_used,
    )


def _pick_science_nugget(store, finding: EvidenceFinding, user_id: Optional[str]) -> tuple[str, str]:
    rotated = rotate_nuggets(
        store.nuggets,
        count=1,
        user_id=user_id,
        factor=finding.factor,
    )
    if rotated:
        return rotated[0].text, rotated[0].source
    if finding.mechanism:
        return finding.mechanism, finding.science_citation
    if finding.quantified:
        return finding.quantified, finding.science_citation
    return finding.alert_short or finding.sub_effect, finding.science_citation


def select_evidence_bundle(
    env: EnvironmentalData,
    *,
    profile: Optional[UserProfile] = None,
    guest_mode: Optional[bool] = None,
    user_id: Optional[str] = None,
    day_phase: Optional[DayPhase] = None,
    local_time: Optional[datetime] = None,
) -> EvidenceBundle:
    try:
        store = get_evidence_store()
    except FileNotFoundError:
        return EvidenceBundle(primary=None)

    if guest_mode is None:
        guest_mode = profile is None or resolve_mode(profile).value == "guest"

    partial = False
    if profile is not None and not guest_mode:
        partial = resolve_mode(profile).value == "partial_personalised"

    phase: DayPhase = day_phase or resolve_day_phase(local_time)
    bands = bucketize_environment(env)
    season = indian_season()
    candidates = match_findings(
        store.findings,
        season=season,
        bands=bands,
        profile=profile,
        guest_mode=guest_mode,
        partial_personalised=partial,
        index=store.index,
        day_phase=phase,
    )

    uid = user_id or (profile.user_id if profile else None)
    thin_cells = store.build_report.get("coverage_report", {}).get("thin_cells", [])
    gap_views = [
        GapConflictView(
            id=int(g["id"]),
            type=g.get("type", ""),
            topic=g.get("topic", ""),
            note=g.get("note", ""),
        )
        for g in store.gaps_conflicts[:5]
    ]
    nugget_views = [
        ScienceNuggetView(id=n.id, text=n.text, factor=n.factor, source=n.source)
        for n in rotate_by_factor_diversity(store.nuggets, count=3, user_id=uid)
    ]

    if not candidates:
        return EvidenceBundle(
            primary=None,
            science_nuggets=nugget_views,
            gaps_conflicts=gap_views,
            evidence_version=store.version,
            coverage_thin_cells=thin_cells[:5],
            day_phase=phase,
        )

    ranked = rank_findings(
        candidates,
        profile=profile,
        partial_personalised=partial,
        day_phase=phase,
        guest_mode=guest_mode,
    )
    finding, score, matched = ranked[0]
    phase_label = phase_used_label(finding.time_of_day_phase, phase)
    l1_text = _sanitize_l1(finding.pick_l1(guest_mode=guest_mode, day_phase=phase), store.glossary)
    science_fact, science_source = _pick_science_nugget(store, finding, uid)

    carousel_findings = select_carousel(ranked, max_slots=5)
    carousel = [
        _to_summary(
            f,
            _sanitize_l1(f.pick_l1(guest_mode=guest_mode, day_phase=phase), store.glossary),
            phase_used=phase_used_label(f.time_of_day_phase, phase),
        )
        for f in carousel_findings
    ]

    habit_ranked = [item for item in ranked if item[0].factor in _HABIT_FACTORS]
    habit_alerts = [
        _to_summary(
            f,
            _sanitize_l1(f.pick_l1(guest_mode=guest_mode, day_phase=phase), store.glossary),
            phase_used=phase_used_label(f.time_of_day_phase, phase),
        )
        for f, _, _ in habit_ranked[:3]
    ]

    primary = EvidenceSelection(
        finding=finding,
        l1_text=l1_text,
        l2_text=finding.pick_l2(),
        science_fact=science_fact,
        science_source=science_source,
        matched_filter_count=matched,
        rank_score=score,
        guest_mode=guest_mode,
        phase_used=phase_label,
        carousel=carousel_findings,
    )

    return EvidenceBundle(
        primary=primary,
        carousel=carousel,
        habit_alerts=habit_alerts,
        science_nuggets=nugget_views,
        gaps_conflicts=gap_views,
        evidence_version=store.version,
        coverage_thin_cells=thin_cells[:5],
        day_phase=phase,
    )


def select_primary_finding(
    env: EnvironmentalData,
    *,
    profile: Optional[UserProfile] = None,
    guest_mode: Optional[bool] = None,
    user_id: Optional[str] = None,
    day_phase: Optional[DayPhase] = None,
    local_time: Optional[datetime] = None,
) -> Optional[EvidenceSelection]:
    bundle = select_evidence_bundle(
        env,
        profile=profile,
        guest_mode=guest_mode,
        user_id=user_id,
        day_phase=day_phase,
        local_time=local_time,
    )
    return bundle.primary
