"""HLHP user consent (env logging + personalisation)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app.hlhp.db import hl_db
from app.hlhp.models.history import ConsentRequest, ConsentResponse, ConsentStatusResponse

logger = logging.getLogger(__name__)

_CONSENT = "hlhp_user_consent"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def upsert_consent(req: ConsentRequest) -> ConsentResponse:
    updated_at = _now_iso()
    doc = {
        "user_id": req.user_id,
        "env_logging_consent": req.env_logging_consent,
        "personalisation_consent": req.personalisation_consent,
        "consent_version": req.consent_version,
        "updated_at": updated_at,
    }
    try:
        await hl_db[_CONSENT].update_one(
            {"user_id": req.user_id},
            {"$set": doc},
            upsert=True,
        )
    except Exception as exc:
        logger.warning("HLHP consent upsert failed: %s", exc)
        raise
    return ConsentResponse(
        user_id=req.user_id,
        env_logging_consent=req.env_logging_consent,
        personalisation_consent=req.personalisation_consent,
        consent_version=req.consent_version,
        updated_at=updated_at,
    )


async def get_consent(user_id: str) -> ConsentStatusResponse:
    try:
        doc = await hl_db[_CONSENT].find_one({"user_id": user_id})
    except Exception as exc:
        logger.warning("HLHP consent read failed: %s", exc)
        doc = None
    if not doc:
        return ConsentStatusResponse(user_id=user_id)
    return ConsentStatusResponse(
        user_id=user_id,
        env_logging_consent=bool(doc.get("env_logging_consent")),
        personalisation_consent=bool(doc.get("personalisation_consent")),
        consent_version=doc.get("consent_version"),
        updated_at=doc.get("updated_at"),
    )


async def env_logging_allowed(user_id: Optional[str]) -> bool:
    if not user_id:
        return False
    try:
        doc = await hl_db[_CONSENT].find_one({"user_id": user_id})
    except Exception:
        return True
    if not doc:
        return True
    return bool(doc.get("env_logging_consent", True))
