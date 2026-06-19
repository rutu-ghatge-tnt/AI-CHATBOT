from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

INTERNAL_SCIENCE_MARKER = "(internal science only)"

DayPhase = Literal["morning", "evening"]


@dataclass(frozen=True)
class UserFilterToken:
    class_name: str
    value: str


@dataclass(frozen=True)
class EvidenceFinding:
    id: str
    factor: str
    row_number: int
    sub_effect: str
    quantified: str
    mechanism: str
    product_implication: str
    outcome_tag: str
    confidence: str
    india_relevant: bool
    source_type: str
    source_title: str
    edition_year: str
    chapter_section: str
    pages_doi_pmid: str
    alert_short: str
    priority: str
    season_bands: tuple[str, ...]
    uvi_bands: tuple[str, ...]
    aqi_bands: tuple[str, ...]
    rh_bands: tuple[str, ...]
    temp_bands: tuple[str, ...]
    user_filter: tuple[UserFilterToken, ...]
    alert_l1_personalised: str
    alert_l1_guest: str
    never_fire: bool
    science_citation: str
    # v2 engagement + alert hierarchy
    alert_l1_evening_personalised: str = ""
    alert_l1_evening_guest: str = ""
    alert_l2_explainer: str = ""
    time_of_day_phase: str = "any_time"
    mood_verdict_tag: str = ""
    combination_stack: str = ""
    engagement_archetype: str = ""
    physical_analogy: str = ""
    body_sensation_decode: str = ""
    symptom_keyword: str = ""
    routine_action: str = ""
    visual_icon_hint: str = ""
    internal_only: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceFinding:
        triggers = data["triggers"]
        tokens = tuple(
            UserFilterToken(t["class"], t["value"]) for t in triggers.get("user_filter", [])
        )
        internal_only = bool(data.get("internal_only"))
        return cls(
            id=data["id"],
            factor=data["factor"],
            row_number=int(data["row_number"]),
            sub_effect=data.get("sub_effect", ""),
            quantified=data.get("quantified", ""),
            mechanism=data.get("mechanism", ""),
            product_implication=data.get("product_implication", ""),
            outcome_tag=data.get("outcome_tag", ""),
            confidence=data.get("confidence", ""),
            india_relevant=bool(data.get("india_relevant")),
            source_type=data.get("source_type", ""),
            source_title=data.get("source_title", ""),
            edition_year=data.get("edition_year", ""),
            chapter_section=data.get("chapter_section", ""),
            pages_doi_pmid=data.get("pages_doi_pmid", ""),
            alert_short=data.get("alert_short", ""),
            priority=data.get("priority", "P2"),
            season_bands=tuple(triggers.get("season", ["any"])),
            uvi_bands=tuple(triggers.get("uvi", ["any"])),
            aqi_bands=tuple(triggers.get("aqi", ["any"])),
            rh_bands=tuple(triggers.get("rh", ["any"])),
            temp_bands=tuple(triggers.get("temp", ["any"])),
            user_filter=tokens,
            alert_l1_personalised=data.get("alert_l1_personalised", ""),
            alert_l1_guest=data.get("alert_l1_guest", ""),
            never_fire=bool(data.get("never_fire")),
            science_citation=data.get("science_citation", ""),
            alert_l1_evening_personalised=data.get("alert_l1_evening_personalised", ""),
            alert_l1_evening_guest=data.get("alert_l1_evening_guest", ""),
            alert_l2_explainer=data.get("alert_l2_explainer", ""),
            time_of_day_phase=data.get("time_of_day_phase", "any_time") or "any_time",
            mood_verdict_tag=data.get("mood_verdict_tag", ""),
            combination_stack=data.get("combination_stack", ""),
            engagement_archetype=data.get("engagement_archetype", ""),
            physical_analogy=data.get("physical_analogy", ""),
            body_sensation_decode=data.get("body_sensation_decode", ""),
            symptom_keyword=data.get("symptom_keyword", ""),
            routine_action=data.get("routine_action", ""),
            visual_icon_hint=data.get("visual_icon_hint", ""),
            internal_only=internal_only,
        )

    def is_surfaced_to_client(self) -> bool:
        if self.never_fire or self.internal_only:
            return False
        for text in (
            self.alert_l1_personalised,
            self.alert_l1_guest,
            self.alert_l1_evening_personalised,
            self.alert_l1_evening_guest,
        ):
            if INTERNAL_SCIENCE_MARKER.lower() in (text or "").lower():
                return False
        return True

    def pick_l1(self, *, guest_mode: bool, day_phase: DayPhase) -> str:
        if day_phase == "evening":
            if guest_mode:
                return (
                    self.alert_l1_evening_guest
                    or self.alert_l1_guest
                    or self.alert_l1_personalised
                    or self.alert_short
                )
            return (
                self.alert_l1_evening_personalised
                or self.alert_l1_personalised
                or self.alert_l1_guest
                or self.alert_short
            )
        if guest_mode:
            return self.alert_l1_guest or self.alert_l1_personalised or self.alert_short
        return self.alert_l1_personalised or self.alert_l1_guest or self.alert_short

    def pick_l2(self) -> str:
        if self.alert_l2_explainer:
            return self.alert_l2_explainer
        return self.product_implication or self.mechanism


@dataclass(frozen=True)
class ScienceNugget:
    id: int
    text: str
    factor: str
    source_type: str
    source: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScienceNugget:
        return cls(
            id=int(data["id"]),
            text=data.get("text", ""),
            factor=data.get("factor", ""),
            source_type=data.get("source_type", ""),
            source=data.get("source", ""),
        )


@dataclass
class EvidenceSelection:
    finding: EvidenceFinding
    l1_text: str
    l2_text: str
    science_fact: str
    science_source: str
    matched_filter_count: int
    rank_score: float
    guest_mode: bool
    phase_used: str = "morning_prep"
    carousel: list[EvidenceFinding] = field(default_factory=list)


@dataclass
class EvidenceAlertSummary:
    id: str
    factor: str
    l1_text: str
    l2_text: str = ""
    priority: str = "P2"
    india_relevant: bool = False
    mood_verdict_tag: str = ""
    engagement_archetype: str = ""
    symptom_keyword: str = ""
    routine_action: str = ""
    visual_icon_hint: str = ""
    phase_used: str = "morning_prep"


@dataclass
class ScienceNuggetView:
    id: int
    text: str
    factor: str
    source: str


@dataclass
class GapConflictView:
    id: int
    type: str
    topic: str
    note: str


@dataclass
class EvidenceBundle:
    primary: EvidenceSelection | None
    carousel: list[EvidenceAlertSummary] = field(default_factory=list)
    habit_alerts: list[EvidenceAlertSummary] = field(default_factory=list)
    science_nuggets: list[ScienceNuggetView] = field(default_factory=list)
    gaps_conflicts: list[GapConflictView] = field(default_factory=list)
    evidence_version: int = 1
    coverage_thin_cells: list[dict] = field(default_factory=list)
    day_phase: str = "morning"
