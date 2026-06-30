"""Handle HLHP action-tap — persist behaviour and update streaks."""

from __future__ import annotations

from app.hlhp.coach.state_store import record_action_tap
from app.hlhp.core.bands import bucketize_environment
from app.hlhp.core.phase import resolve_day_phase
from app.hlhp.coach.models import ActionTapRequest, ActionTapResponse
from app.hlhp.services.daily_log_store import upsert_user_log_day
from app.hlhp.services.scan_service import resolve_environment


async def run_action_tap(req: ActionTapRequest) -> ActionTapResponse:
    env = await resolve_environment(req)
    bands = bucketize_environment(env)
    streak, longest = await record_action_tap(
        req.user_id,
        routine_action=req.routine_action,
        uvi_band=bands.uvi,
        tapped_at=req.current_time,
        rule_id=req.rule_id,
    )
    await upsert_user_log_day(
        user_id=req.user_id,
        logged_at=req.current_time,
        outdoor_ok_score=req.outdoor_ok_score,
        mood_verdict=str(req.mood_verdict or ""),
        sudden_event_tags=req.sudden_event_tags,
        uvi=float(env.uvi),
        temp_c=float(env.temp_c),
        aqi=int(env.aqi),
        rh_pct=float(env.rh_pct),
        city=str(req.location_city or ""),
    )
    phase = resolve_day_phase(req.current_time)
    next_check = "this evening's routine" if phase == "morning" else "tomorrow morning"
    return ActionTapResponse(streak=streak, longest_ever=longest, next_check_in=next_check)
