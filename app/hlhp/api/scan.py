from fastapi import APIRouter, Depends, HTTPException, Query

from app.hlhp.api.deps_auth import (
    hlhp_authenticated_user,
    hlhp_optional_authenticated_user,
    resolve_scan_user_id,
    verify_client_user_id,
)
from app.hlhp.api.store_http import http_503_for_store_error
from app.hlhp.db_errors import HlhpStoreError

from app.hlhp.evidence.loader import get_evidence_store
from app.hlhp.evidence.scenario_store import get_scenario_store
from app.hlhp.coach.models import ActionTapRequest, ActionTapResponse
from app.hlhp.models.scan import (
    HealthResponse,
    ScanRequest,
    ScanResponse,
    SymptomFeelingRequest,
    SymptomFeelingResponse,
    SymptomSelectedResponse,
    SymptomTapRequest,
    SymptomTapResponse,
)
from app.hlhp.services.action_tap_service import run_action_tap
from app.hlhp.coach.state_store import fetch_selected_symptoms, record_symptom_feeling
from app.hlhp.core.local_date import calendar_date_key
from app.hlhp.services.daily_log_store import upsert_user_log_day
from app.hlhp.services.log_event_store import fetch_latest_log_for_date
from app.hlhp.services.scan_service import run_scan, run_symptom_tap

router = APIRouter(prefix="/hlhp", tags=["HLHP v2 — Flash Alerts"])


@router.post("/scan", response_model=ScanResponse)
async def hlhp_scan(
    req: ScanRequest,
    auth_user: dict | None = Depends(hlhp_optional_authenticated_user),
) -> ScanResponse:
    resolved_uid = resolve_scan_user_id(req.user_id, auth_user)
    if resolved_uid != req.user_id:
        req = req.model_copy(update={"user_id": resolved_uid})
    try:
        return await run_scan(req, auth_user=auth_user)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"HLHP scan failed: {exc}") from exc


@router.post("/symptom_tap", response_model=SymptomTapResponse)
async def hlhp_symptom_tap(
    req: SymptomTapRequest,
    auth_user: dict | None = Depends(hlhp_optional_authenticated_user),
) -> SymptomTapResponse:
    resolved_uid = resolve_scan_user_id(req.user_id, auth_user)
    if resolved_uid != req.user_id:
        req = req.model_copy(update={"user_id": resolved_uid})
    try:
        return await run_symptom_tap(req)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Symptom tap failed: {exc}") from exc


@router.post("/symptom_feeling", response_model=SymptomFeelingResponse)
async def hlhp_symptom_feeling(
    req: SymptomFeelingRequest,
    user: dict = Depends(hlhp_authenticated_user),
) -> SymptomFeelingResponse:
    """Log how the user feels today — only logged selections are highlighted in UI."""
    user_id = verify_client_user_id(user, req.user_id)
    keyword = req.symptom_keyword.strip().lower()
    if not keyword:
        raise HTTPException(status_code=400, detail="symptom_keyword required")
    try:
        await record_symptom_feeling(
            user_id,
            keyword,
            selected=req.selected,
            recorded_at=req.local_time,
        )
        if req.selected:
            await upsert_user_log_day(user_id=user_id, logged_at=req.local_time)
    except HlhpStoreError as exc:
        http_503_for_store_error(exc)
    active = sorted(await fetch_selected_symptoms(user_id))
    return SymptomFeelingResponse(
        symptom_keyword=keyword,
        selected=req.selected,
        selected_keywords=active,
    )


def _display_areas(slugs: list[str]) -> list[str]:
    out: list[str] = []
    for raw in slugs:
        s = str(raw).strip().lower().replace(" ", "_")
        if not s:
            continue
        if s == "full_face":
            out.append("Full face")
        else:
            out.append(s.replace("_", " ").title())
    return out


@router.get("/symptom_feeling/selected", response_model=SymptomSelectedResponse)
async def hlhp_selected_symptoms(
    user_id: str = Query(..., min_length=1),
    date: str | None = Query(None, description="Calendar date YYYY-MM-DD for today's areas"),
    user: dict = Depends(hlhp_authenticated_user),
) -> SymptomSelectedResponse:
    """Active symptom feelings for the user (last 30 days, latest toggle wins)."""
    uid = verify_client_user_id(user, user_id)
    active = sorted(await fetch_selected_symptoms(uid))
    areas: list[str] = []
    if date:
        latest = await fetch_latest_log_for_date(uid, date.strip())
        if latest:
            areas = _display_areas(list(latest.get("areas") or []))
    return SymptomSelectedResponse(user_id=uid, selected_keywords=active, areas=areas)


@router.post("/action_tap", response_model=ActionTapResponse)
async def hlhp_action_tap(
    req: ActionTapRequest,
    user: dict = Depends(hlhp_authenticated_user),
) -> ActionTapResponse:
    uid = verify_client_user_id(user, req.user_id)
    if uid != req.user_id:
        req = req.model_copy(update={"user_id": uid})
    try:
        return await run_action_tap(req)
    except HlhpStoreError as exc:
        http_503_for_store_error(exc)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Action tap failed: {exc}") from exc


@router.get("/health", response_model=HealthResponse)
async def hlhp_health() -> HealthResponse:
    scenario_store = None
    try:
        scenario_store = get_scenario_store()
    except FileNotFoundError:
        pass
    if scenario_store is None:
        return HealthResponse(
            ok=False,
            snapshot_version="missing",
            workbook_version=None,
            rule_count=0,
            composition_row_count=0,
            generated_at="",
            scenario_library_version=None,
            scenario_master_cells=0,
            scenario_compound_cells=0,
        )
    legacy_store = None
    try:
        legacy_store = get_evidence_store()
    except FileNotFoundError:
        pass
    return HealthResponse(
        ok=True,
        snapshot_version=scenario_store.version,
        workbook_version=scenario_store.source,
        rule_count=scenario_store.master_cell_count,
        composition_row_count=scenario_store.compound_cell_count,
        generated_at=legacy_store.generated_at if legacy_store else str(scenario_store.source),
        scenario_library_version=scenario_store.version,
        scenario_master_cells=scenario_store.master_cell_count,
        scenario_compound_cells=scenario_store.compound_cell_count,
    )
