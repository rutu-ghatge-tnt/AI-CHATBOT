"""HLHP daily selfie storage — S3 stable keys under HLHP-LOG/ + Mongo pointer."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from fastapi import HTTPException, UploadFile

from app.hlhp.core.hlhp_settings import get_hlhp_settings
from app.hlhp.db import hl_db

logger = logging.getLogger(__name__)

_COLLECTION = "hlhp_selfie_day"
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SAFE_USER = re.compile(r"[^a-zA-Z0-9_-]+")
_ALLOWED_MIME = {"image/jpeg", "image/jpg", "image/png", "image/webp"}


def _col():
    return hl_db[_COLLECTION]


def _s3():
    settings = get_hlhp_settings()
    try:
        return boto3.client("s3", region_name=settings.selfie_s3_region)
    except NoCredentialsError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "s3_unavailable", "message": "AWS credentials are not configured."},
        ) from exc


def _safe_user_id(user_id: str) -> str:
    cleaned = _SAFE_USER.sub("_", (user_id or "").strip())
    if not cleaned:
        raise HTTPException(status_code=400, detail={"code": "bad_user", "message": "Invalid user id."})
    return cleaned[:120]


def _validate_date(date_iso: str) -> str:
    d = (date_iso or "").strip()
    if not _DATE_RE.match(d):
        raise HTTPException(
            status_code=400,
            detail={"code": "bad_date", "message": "date must be YYYY-MM-DD (local calendar day)."},
        )
    return d


def selfie_object_key(user_id: str, date_iso: str) -> str:
    settings = get_hlhp_settings()
    return f"{settings.selfie_s3_prefix}/{_safe_user_id(user_id)}/{_validate_date(date_iso)}.jpg"


def public_selfie_url(key: str) -> str:
    settings = get_hlhp_settings()
    return f"https://{settings.selfie_s3_bucket}.s3.{settings.selfie_s3_region}.amazonaws.com/{key}"


async def _normalize_jpeg(upload: UploadFile) -> bytes:
    settings = get_hlhp_settings()
    raw = await upload.read()
    if not raw:
        raise HTTPException(status_code=400, detail={"code": "empty_file", "message": "Empty selfie file."})
    if len(raw) > settings.selfie_max_bytes:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "file_too_large",
                "message": f"Selfie must be under {settings.selfie_max_bytes // (1024 * 1024)} MB.",
            },
        )

    content_type = (upload.content_type or "").lower().split(";")[0].strip()
    if content_type and content_type not in _ALLOWED_MIME:
        raise HTTPException(
            status_code=400,
            detail={"code": "bad_type", "message": "Use JPEG or PNG for selfies."},
        )

    try:
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(raw))
        img = img.convert("RGB")
        # Cap long edge for skincare-quality stills without huge uploads
        max_edge = 1600
        w, h = img.size
        scale = min(1.0, max_edge / float(max(w, h)))
        if scale < 1.0:
            img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=88, optimize=True)
        data = out.getvalue()
        if len(data) > settings.selfie_max_bytes:
            raise HTTPException(
                status_code=400,
                detail={"code": "file_too_large", "message": "Compressed selfie still exceeds size limit."},
            )
        return data
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Selfie image normalize failed: %s", exc)
        # Fallback: accept raw jpeg bytes only
        if content_type in {"image/jpeg", "image/jpg"} or (upload.filename or "").lower().endswith((".jpg", ".jpeg")):
            return raw
        raise HTTPException(
            status_code=400,
            detail={"code": "bad_image", "message": "Could not read that image. Try a JPEG photo."},
        ) from exc


def _put_s3(key: str, body: bytes) -> None:
    settings = get_hlhp_settings()
    client = _s3()
    try:
        client.put_object(
            Bucket=settings.selfie_s3_bucket,
            Key=key,
            Body=body,
            ContentType="image/jpeg",
            CacheControl="private, max-age=3600",
        )
    except ClientError as exc:
        logger.exception("S3 put failed for %s", key)
        raise HTTPException(
            status_code=502,
            detail={"code": "s3_put_failed", "message": "Could not upload selfie to storage."},
        ) from exc


def _delete_s3(key: str) -> None:
    settings = get_hlhp_settings()
    client = _s3()
    try:
        client.delete_object(Bucket=settings.selfie_s3_bucket, Key=key)
    except ClientError as exc:
        logger.warning("S3 delete failed for %s: %s", key, exc)


async def upsert_daily_selfie(user_id: str, date_iso: str, upload: UploadFile) -> dict[str, Any]:
    """One selfie per user+day. Overwrites the stable S3 key (no clutter)."""
    date_iso = _validate_date(date_iso)
    key = selfie_object_key(user_id, date_iso)
    body = await _normalize_jpeg(upload)

    # Explicit delete then put so replace always clears any prior object version/orphan.
    _delete_s3(key)
    _put_s3(key, body)

    url = public_selfie_url(key)
    now = datetime.now(timezone.utc)
    doc = {
        "user_id": user_id,
        "date": date_iso,
        "s3_key": key,
        "url": url,
        "bytes": len(body),
        "content_type": "image/jpeg",
        "updated_at": now,
    }
    await _col().update_one(
        {"user_id": user_id, "date": date_iso},
        {"$set": doc, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    return {"date": date_iso, "url": url, "s3_key": key, "bytes": len(body)}


async def list_selfies(user_id: str, *, date_from: str | None = None, date_to: str | None = None) -> list[dict[str, Any]]:
    filt: dict[str, Any] = {"user_id": user_id}
    if date_from or date_to:
        date_q: dict[str, str] = {}
        if date_from:
            date_q["$gte"] = _validate_date(date_from)
        if date_to:
            date_q["$lte"] = _validate_date(date_to)
        filt["date"] = date_q
    cursor = _col().find(filt, {"_id": 0, "date": 1, "url": 1, "s3_key": 1, "updated_at": 1}).sort("date", 1)
    rows = []
    async for doc in cursor:
        url = doc.get("url") or public_selfie_url(doc["s3_key"])
        rows.append(
            {
                "date": doc["date"],
                "url": url,
                "updated_at": doc.get("updated_at").isoformat()
                if isinstance(doc.get("updated_at"), datetime)
                else doc.get("updated_at"),
            }
        )
    return rows


async def get_selfie_for_date(user_id: str, date_iso: str) -> dict[str, Any] | None:
    date_iso = _validate_date(date_iso)
    doc = await _col().find_one({"user_id": user_id, "date": date_iso}, {"_id": 0})
    if not doc:
        return None
    return {
        "date": doc["date"],
        "url": doc.get("url") or public_selfie_url(doc["s3_key"]),
        "s3_key": doc.get("s3_key"),
    }


async def delete_daily_selfie(user_id: str, date_iso: str) -> dict[str, Any]:
    date_iso = _validate_date(date_iso)
    key = selfie_object_key(user_id, date_iso)
    doc = await _col().find_one({"user_id": user_id, "date": date_iso})
    if doc and doc.get("s3_key"):
        key = doc["s3_key"]
    _delete_s3(key)
    result = await _col().delete_one({"user_id": user_id, "date": date_iso})
    return {"date": date_iso, "deleted": result.deleted_count > 0 or True}
