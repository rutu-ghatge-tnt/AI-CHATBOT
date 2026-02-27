"""
Optional FastAPI routes for the ensemble skin analysis pipeline.
Mount under the same app as the existing face analysis API; does not replace /analyze.
"""

import base64
import logging
import os
from datetime import datetime
from typing import Optional

import cv2
import numpy as np
from fastapi import APIRouter, File, HTTPException, UploadFile

from ..core.config import settings
from .aggregation import EnsembleAnalyzer

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Ensemble Skin Analysis"])

# Lazy init so existing app starts even if ensemble deps (e.g. skimage) are missing
_ensemble: Optional[EnsembleAnalyzer] = None


def _get_ensemble() -> EnsembleAnalyzer:
    global _ensemble
    if _ensemble is None:
        _ensemble = EnsembleAnalyzer(
            claude_api_key=getattr(settings, "ANTHROPIC_API_KEY", None) or os.getenv("CLAUDE_API_KEY", ""),
            deep_model_path=os.getenv("ENSEMBLE_DEEP_MODEL_PATH", "").strip() or None,
        )
    return _ensemble


def _decode_image_from_request(
    file_contents: Optional[bytes],
    image_base64: Optional[str],
    body: Optional[dict],
) -> np.ndarray:
    """Decode image from raw file bytes, image_base64, or JSON body."""
    image = None
    if file_contents:
        nparr = np.frombuffer(file_contents, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    b64 = image_base64 or (body.get("image") if body else None)
    if image is None and b64:
        try:
            raw = base64.b64decode(b64)
            nparr = np.frombuffer(raw, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid base64 image: {e}")
    if image is None:
        raise HTTPException(status_code=400, detail="Provide either file upload or image (base64)")
    return image


@router.post("/analyze/ensemble")
async def analyze_ensemble(
    file: Optional[UploadFile] = File(None),
    image_base64: Optional[str] = None,
):
    """
    Run ensemble skin analysis (classical CV + optional deep + optional Claude).
    Supply either multipart file or form field image_base64.
    Existing POST /analyze is unchanged.
    """
    file_contents = None
    if file and file.filename:
        if not file.content_type or not file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="File must be an image")
        file_contents = await file.read()
    image = _decode_image_from_request(file_contents, image_base64, None)

    try:
        ensemble = _get_ensemble()
        result = ensemble.analyze(image, use_claude=bool(settings.ANTHROPIC_API_KEY), use_deep=True)
        return {
            "success": True,
            "analysis": result["scores"],
            "overall_score": float(
                sum(result["scores"].values()) / len(result["scores"]) if result["scores"] else 0
            ),
            "confidence": result["confidence"],
            "estimated_age": result.get("estimated_age"),
            "estimated_skintype": result.get("estimated_skintype"),
            "breakdown": result.get("breakdown"),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.exception("Ensemble analysis failed")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }


@router.post("/analyze/ensemble/json")
async def analyze_ensemble_json(request: dict):
    """Ensemble analysis from JSON body: {"image": "<base64>"}."""
    image = _decode_image_from_request(None, None, request)
    try:
        ensemble = _get_ensemble()
        result = ensemble.analyze(image, use_claude=bool(settings.ANTHROPIC_API_KEY), use_deep=True)
        return {
            "success": True,
            "analysis": result["scores"],
            "overall_score": float(
                sum(result["scores"].values()) / len(result["scores"]) if result["scores"] else 0
            ),
            "confidence": result["confidence"],
            "estimated_age": result.get("estimated_age"),
            "estimated_skintype": result.get("estimated_skintype"),
            "breakdown": result.get("breakdown"),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.exception("Ensemble analysis failed")
        return {"success": False, "error": str(e), "timestamp": datetime.now().isoformat()}


@router.get("/analyze/ensemble/config")
async def ensemble_config():
    """Return ensemble-specific config (parameters, weights)."""
    from .constants import SKIN_PARAMETERS, DEFAULT_ENSEMBLE_WEIGHTS
    return {
        "skin_parameters": SKIN_PARAMETERS,
        "default_weights": DEFAULT_ENSEMBLE_WEIGHTS,
        "claude_configured": bool(getattr(settings, "ANTHROPIC_API_KEY", None) or os.getenv("CLAUDE_API_KEY")),
    }
