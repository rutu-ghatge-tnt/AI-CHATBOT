from fastapi import APIRouter, HTTPException

from app.hlhp.evidence.loader import get_evidence_store
from app.hlhp.coach.models import ActionTapRequest, ActionTapResponse
from app.hlhp.models.scan import (
    HealthResponse,
    ScanRequest,
    ScanResponse,
    SymptomFeelingRequest,
    SymptomFeelingResponse,
    SymptomTapRequest,
    SymptomTapResponse,
)
from app.hlhp.services.action_tap_service import run_action_tap
from app.hlhp.coach.state_store import fetch_selected_symptoms, record_symptom_feeling
from app.hlhp.services.scan_service import run_scan, run_symptom_tap

router = APIRouter(prefix="/hlhp", tags=["HLHP v2 — Flash Alerts"])


@router.post("/scan", response_model=ScanResponse)
async def hlhp_scan(req: ScanRequest) -> ScanResponse:
    try:
        return await run_scan(req)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"HLHP scan failed: {exc}") from exc


@router.post("/symptom_tap", response_model=SymptomTapResponse)
async def hlhp_symptom_tap(req: SymptomTapRequest) -> SymptomTapResponse:
    try:
        return await run_symptom_tap(req)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Symptom tap failed: {exc}") from exc


@router.post("/symptom_feeling", response_model=SymptomFeelingResponse)
async def hlhp_symptom_feeling(req: SymptomFeelingRequest) -> SymptomFeelingResponse:
    """Log how the user feels today — only logged selections are highlighted in UI."""
    keyword = req.symptom_keyword.strip().lower()
    if not keyword:
        raise HTTPException(status_code=400, detail="symptom_keyword required")
    await record_symptom_feeling(
        req.user_id,
        keyword,
        selected=req.selected,
        recorded_at=req.local_time,
    )
    active = sorted(await fetch_selected_symptoms(req.user_id))
    return SymptomFeelingResponse(
        symptom_keyword=keyword,
        selected=req.selected,
        selected_keywords=active,
    )


@router.post("/action_tap", response_model=ActionTapResponse)
async def hlhp_action_tap(req: ActionTapRequest) -> ActionTapResponse:
    try:
        return await run_action_tap(req)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Action tap failed: {exc}") from exc


@router.get("/health", response_model=HealthResponse)
async def hlhp_health() -> HealthResponse:
    try:
        store = get_evidence_store()
    except FileNotFoundError:
        return HealthResponse(ok=False, snapshot_version="missing", workbook_version=None, rule_count=0, composition_row_count=0, generated_at="")
    return HealthResponse(
        ok=True,
        snapshot_version=str(store.version),
        workbook_version=store.workbook_version,
        rule_count=len(store.findings),
        composition_row_count=store.composition_row_count,
        generated_at=store.generated_at,
    )
