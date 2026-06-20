"""HLHP composition layer API routes (UI spec §10)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from app.hlhp.composition.concern import assemble_concern_deepdive
from app.hlhp.composition.explore import assemble_event_guides, assemble_explore
from app.hlhp.composition.forecast import assemble_week_ahead
from app.hlhp.composition.symptom import assemble_symptom_explainer
from app.hlhp.evidence.loader import get_evidence_store
from app.hlhp.models.scan import ScanRequest
from app.hlhp.services.scan_service import resolve_environment

router = APIRouter(prefix="/hlhp", tags=["HLHP v2 — Composition"])


@router.get("/concern_deepdive/{concern_id}")
async def concern_deepdive(concern_id: str):
    page = assemble_concern_deepdive(concern_id)
    if not page:
        raise HTTPException(status_code=404, detail=f"Unknown concern: {concern_id}")
    return page


@router.get("/symptom_explainer/{symptom_keyword}")
async def symptom_explainer(symptom_keyword: str):
    page = assemble_symptom_explainer(symptom_keyword)
    if not page:
        raise HTTPException(status_code=404, detail=f"No explainer for: {symptom_keyword}")
    return page


@router.get("/event_guides")
async def event_guides(city: str = Query(...)):
    return {"city": city, "guides": assemble_event_guides(city)}


@router.get("/explore")
async def explore_lane(
    city: str = Query(...),
    concern_id: str | None = Query(None),
):
    return assemble_explore(city, concern_id)


@router.get("/week_ahead")
async def week_ahead(
    city: str = Query(...),
    concern_id: str | None = Query(None),
    raw_uvi: float = Query(5.0, ge=0),
    raw_aqi: int = Query(50, ge=0),
    raw_rh: float = Query(50.0, ge=0, le=100),
    raw_temp: float = Query(25.0),
):
    req = ScanRequest(
        user_id=None,
        city=city,
        local_time=datetime.now().astimezone(),
        raw_uvi=raw_uvi,
        raw_aqi=raw_aqi,
        raw_rh=raw_rh,
        raw_temp=raw_temp,
    )
    env = await resolve_environment(req)
    days = assemble_week_ahead(base_env=env, concern_id=concern_id, mood_today="")
    return {
        "city": city,
        "concern_id": concern_id,
        "days": days,
        "workbook_version": get_evidence_store().workbook_version,
    }


@router.get("/history")
async def history_lane(user_id: str = Query(...), days: int = Query(30, ge=1, le=90)):
    """Placeholder — requires scan_log collection (Phase 1.5)."""
    return {
        "user_id": user_id,
        "days": days,
        "sfi_average": None,
        "sudden_events": [],
        "message": "History builds after scan_log is wired.",
        "workbook_version": get_evidence_store().workbook_version,
    }
