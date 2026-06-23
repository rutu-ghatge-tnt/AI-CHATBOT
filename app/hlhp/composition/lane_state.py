"""Resolve lane nav CTA strings — evaluated triggers, not blind workbook overwrite."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.hlhp.composition.feeds import festival_on_date, nearest_skin_festival_prep

_DEFAULT_CTAS = {
    "today": "Check today's alerts",
    "your_skin": "7-day forecast",
    "explore": "12 guides + nuggets",
    "history": "Last 15 days",
    "plan_week": "Plan ahead",
}

_HEAVY_MOODS = frozenset({"stack_day", "manageable_day", "oxidative_load_day"})
_PIGMENT_MOODS = frozenset({"pigment_overdrive_day"})
_SEBUM_MOODS = frozenset({"sebum_rush_day"})
_BARRIER_MOODS = frozenset({"barrier_stress_day"})
_EASY_MOODS = frozenset({"easy_day", "comfortable_day"})


@dataclass(frozen=True)
class LaneStateContext:
    when: datetime = field(default_factory=lambda: datetime.now().astimezone())
    alert_count: int = 0
    sudden_event: bool = False
    mood_verdict: str = ""


def _pick_cta(candidates: list[tuple[int, str]]) -> str | None:
    """Lowest priority number wins (1 beats 4)."""
    if not candidates:
        return None
    return min(candidates, key=lambda item: item[0])[1]


def _today_ctas(ctx: LaneStateContext) -> list[tuple[int, str]]:
    mood = (ctx.mood_verdict or "").strip().lower()
    matches: list[tuple[int, str]] = []

    if festival_on_date(ctx.when):
        matches.append((2, "Festival day today"))
    if mood in _HEAVY_MOODS:
        matches.append((1, "Heavy day for skin"))
    if mood in _PIGMENT_MOODS:
        matches.append((1, "Pigment-overdrive day"))
    if mood in _SEBUM_MOODS:
        matches.append((1, "Sebum-rush day"))
    if mood in _BARRIER_MOODS:
        matches.append((1, "Barrier-stress day"))
    if ctx.sudden_event:
        matches.append((1, "Sudden event detected"))
    if ctx.alert_count > 0:
        label = "1 alert for today" if ctx.alert_count == 1 else f"{ctx.alert_count} alerts ready"
        matches.append((1, label))
    if mood in _EASY_MOODS:
        matches.append((3, "Easy day for skin"))
    matches.append((4, _DEFAULT_CTAS["today"]))
    return matches


def _explore_ctas(ctx: LaneStateContext) -> list[tuple[int, str]]:
    matches: list[tuple[int, str]] = []
    if ctx.sudden_event:
        matches.append((1, "Monsoon onset is up next"))
    fest = nearest_skin_festival_prep(ctx.when)
    if fest:
        cta = str(fest.get("explore_cta") or "Festival prep — 2 weeks out").strip()
        matches.append((1, cta))
    matches.append((4, _DEFAULT_CTAS["explore"]))
    return matches


def resolve_lane_states(
    *,
    alert_count: int = 0,
    sudden_event: bool = False,
    mood_verdict: str = "",
    when: datetime | None = None,
) -> dict[str, str]:
    ctx = LaneStateContext(
        when=when or datetime.now().astimezone(),
        alert_count=alert_count,
        sudden_event=sudden_event,
        mood_verdict=mood_verdict,
    )
    out = dict(_DEFAULT_CTAS)

    today = _pick_cta(_today_ctas(ctx))
    if today:
        out["today"] = today

    explore = _pick_cta(_explore_ctas(ctx))
    if explore:
        out["explore"] = explore

    return out
