from __future__ import annotations

import os
import re
import time
import uuid
from pathlib import Path
from typing import Final

from app.label_looker.errors import ScannerApiError
from app.label_looker.settings import get_label_looker_settings

# Mirrors typical productScanMulter allowlist (README §5).
_ALLOWED_MIMES: Final[frozenset[str]] = frozenset(
    {
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/gif",
        "image/webp",
        "image/bmp",
        "image/x-ms-bmp",
        "image/tiff",
        "image/tif",
        "image/x-tiff",
        "image/heic",
        "image/heif",
        "image/svg+xml",
        "image/x-icon",
        "image/vnd.microsoft.icon",
        "image/avif",
        "image/x-adobe-dng",
        "image/dng",
    }
)

_EXT_BY_MIME: Final[dict[str, str]] = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/x-ms-bmp": ".bmp",
    "image/tiff": ".tiff",
    "image/tif": ".tif",
    "image/x-tiff": ".tiff",
    "image/heic": ".heic",
    "image/heif": ".heif",
    "image/svg+xml": ".svg",
    "image/x-icon": ".ico",
    "image/vnd.microsoft.icon": ".ico",
    "image/avif": ".avif",
    "image/x-adobe-dng": ".dng",
    "image/dng": ".dng",
}

_MAX_BYTES = 5 * 1024 * 1024


def validate_upload(content_type: str | None, size: int) -> str:
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct not in _ALLOWED_MIMES:
        raise ScannerApiError(400, "Unsupported image type")
    if size > _MAX_BYTES:
        raise ScannerApiError(400, "File too large")
    return ct


def save_scan_image(original_filename: str | None, mime: str, data: bytes) -> str:
    """Save under ./public/product-scan-images; return basename only."""
    base = Path(os.getcwd()) / "public" / "product-scan-images"
    base.mkdir(parents=True, exist_ok=True)
    raw = (original_filename or "upload").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", raw)[:80] or "upload"
    ext = _EXT_BY_MIME.get(mime, ".bin")
    stamp = int(time.time() * 1000)
    name = f"{safe}-{stamp}-{uuid.uuid4().hex[:8]}{ext}"
    path = base / name
    path.write_bytes(data)
    _upload_to_s3_if_configured(name=name, mime=mime, data=data)
    return name


def public_relative_url(basename: str) -> str:
    return f"/product-scan-images/{basename}"


def _upload_to_s3_if_configured(*, name: str, mime: str, data: bytes) -> None:
    """Best-effort S3 sync; local disk path remains source of truth."""
    try:
        import boto3  # type: ignore
    except Exception:
        return
    s = get_label_looker_settings()
    if not s.aws_bucket_name:
        return
    key_prefix = s.aws_scan_images_prefix or "product-scan-images/"
    if not key_prefix.endswith("/"):
        key_prefix += "/"
    key = f"{key_prefix}{name}"
    try:
        client = boto3.client("s3", region_name=s.aws_region or None)
        client.put_object(
            Bucket=s.aws_bucket_name,
            Key=key,
            Body=data,
            ContentType=mime,
        )
    except Exception:
        # Keep Node-parity behavior (successful local save should not fail request).
        return
