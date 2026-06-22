from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from app.hlhp.coach.forecast import ForecastSnapshot
from app.hlhp.coach.models import ActionRecord, CoachContext, CoachTemplate, CoachWrap, StreakMeta
from app.hlhp.coach.streak_engine import (
    actions_in_window,
    current_streak,
    missed_yesterday,
    streak_key,
)
from app.hlhp.coach.templates import load_coach_templates
from app.hlhp.evidence.models import EvidenceFinding


_ACTION_LABELS = {
    "apply_sunscreen": "I applied ✓",
    "reapply_sunscreen": "Reapplied ✓",
    "double_cleanse": "Cleansed ✓",
    "cleanse_gentle": "Cleansed ✓",
    "cleanse_oil": "Cleansed ✓",
    "layer_barrier": "Barrier done ✓",
    "layer_hydration": "Hydrated ✓",
    "improve_sleep": "Noted ✓",
    "reduce_stress": "Noted ✓",
}


def _format_template(template: str, fill: dict[str, Any]) -> str:
    try:
        return template.format(**fill)
    except KeyError:
        return template


def _conditions_met(
    template: CoachTemplate,
    *,
    ctx: CoachContext,
    finding: EvidenceFinding,
    streak: int,
    actions_7d: int,
    forecast: Optional[ForecastSnapshot],
    env_uvi: float,
    env_aqi: int,
    today: date,
) -> bool:
    cond = template.conditions or {}
    if cond.get("min_streak") and streak < int(cond["min_streak"]):
        return False
    if cond.get("max_streak") is not None and streak > int(cond["max_streak"]):
        return False
    if cond.get("factor") and finding.factor != cond["factor"]:
        return False
    if cond.get("min_actions_last_7d") and actions_7d < int(cond["min_actions_last_7d"]):
        return False
    if cond.get("missed_yesterday") and not missed_yesterday(
        ctx.recent_actions, finding.routine_action, today
    ):
        return False
    if cond.get("forecast_easier_next_day"):
        if not forecast or not forecast.eases_next_day(env_uvi, env_aqi):
            return False
    return True


def _pick_template(
    slot: str,
    *,
    ctx: CoachContext,
    finding: EvidenceFinding,
    streak: int,
    actions_7d: int,
    forecast: Optional[ForecastSnapshot],
    env_uvi: float,
    env_aqi: int,
    today: date,
    fill: dict[str, Any],
) -> Optional[str]:
    templates = load_coach_templates()
    eligible = [
        t
        for t in templates
        if t.slot == slot
        and t.tone == ctx.tone
        and _conditions_met(
            t,
            ctx=ctx,
            finding=finding,
            streak=streak,
            actions_7d=actions_7d,
            forecast=forecast,
            env_uvi=env_uvi,
            env_aqi=env_aqi,
            today=today,
        )
    ]
    if not eligible:
        eligible = [
            t
            for t in templates
            if t.slot == slot
            and _conditions_met(
                t,
                ctx=ctx,
                finding=finding,
                streak=streak,
                actions_7d=actions_7d,
                forecast=forecast,
                env_uvi=env_uvi,
                env_aqi=env_aqi,
                today=today,
            )
        ]
    if not eligible:
        return None
    picked = random.choices(eligible, weights=[max(1, t.weight) for t in eligible])[0]
    text = _format_template(picked.template, fill)
    return text if text.strip() else None


def assemble_coach_wrap(
    finding: EvidenceFinding,
    ctx: CoachContext,
    *,
    uvi_band: str,
    day_phase: str,
    mood_verdict: str,
    forecast: Optional[ForecastSnapshot],
    env_uvi: float,
    env_aqi: int,
    local_time: datetime,
) -> CoachWrap:
    today = local_time.date()
    action = finding.routine_action or "no_action_needed"
    skey = streak_key(uvi_band, action)
    streak_rec = ctx.streaks.get(skey)
    streak = current_streak(streak_rec, today)
    since_7d = local_time - timedelta(days=7)
    actions_7d = len(actions_in_window(ctx.recent_actions, routine_action=action, since=since_7d))

    band_label = (mood_verdict or "today").replace("_", " ")
    fill = {"name": ctx.name or "there", "n": streak, "m": 7, "band": uvi_band, "band_label": band_label}

    greeting_slot = f"greeting_{'morning' if day_phase == 'morning' else 'evening'}"
    greeting = None
    if ctx.name:
        greeting = _pick_template(
            greeting_slot,
            ctx=ctx,
            finding=finding,
            streak=streak,
            actions_7d=actions_7d,
            forecast=forecast,
            env_uvi=env_uvi,
            env_aqi=env_aqi,
            today=today,
            fill=fill,
        )

    continuity = None
    if streak >= 2:
        continuity = _pick_template(
            "continuity_streak",
            ctx=ctx,
            finding=finding,
            streak=streak,
            actions_7d=actions_7d,
            forecast=forecast,
            env_uvi=env_uvi,
            env_aqi=env_aqi,
            today=today,
            fill=fill,
        )

    effort = None
    if actions_7d >= 3:
        effort = _pick_template(
            "effort_recognition_positive",
            ctx=ctx,
            finding=finding,
            streak=streak,
            actions_7d=actions_7d,
            forecast=forecast,
            env_uvi=env_uvi,
            env_aqi=env_aqi,
            today=today,
            fill={**fill, "n": actions_7d},
        )
    elif actions_7d == 0 and ctx.recent_actions:
        effort = _pick_template(
            "effort_recognition_gentle",
            ctx=ctx,
            finding=finding,
            streak=streak,
            actions_7d=actions_7d,
            forecast=forecast,
            env_uvi=env_uvi,
            env_aqi=env_aqi,
            today=today,
            fill=fill,
        )

    forward = _pick_template(
        "forward_hook",
        ctx=ctx,
        finding=finding,
        streak=streak,
        actions_7d=actions_7d,
        forecast=forecast,
        env_uvi=env_uvi,
        env_aqi=env_aqi,
        today=today,
        fill=fill,
    )

    closer = _pick_template(
        "closer",
        ctx=ctx,
        finding=finding,
        streak=streak,
        actions_7d=actions_7d,
        forecast=forecast,
        env_uvi=env_uvi,
        env_aqi=env_aqi,
        today=today,
        fill=fill,
    )

    label = _ACTION_LABELS.get(action, "Done ✓")
    longest = streak_rec.longest_ever if streak_rec else 0

    return CoachWrap(
        greeting=greeting,
        continuity=continuity,
        effort_recognition=effort,
        forward_hook=forward,
        closer=closer,
        action_tap_label=label,
        streak_meta=StreakMeta(current=streak, longest=longest) if streak else None,
    )
