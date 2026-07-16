"""Chat / image payload helpers for HLHP hub publishes."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

# Node rejects data URLs on the bus (400). Only http(s) image URLs are allowed.
_MAX_HTTP_URL_CHARS = 2_048
_HTTP_IMG = re.compile(r"^https?://", re.IGNORECASE)


class ChatPayloadError(ValueError):
    """Invalid chat message body (maps to HTTP 400)."""


def now_ms() -> int:
    return int(datetime.now().timestamp() * 1000)


def format_chat_time(ts_ms: int) -> str:
    return (
        datetime.fromtimestamp(ts_ms / 1000)
        .strftime("%I:%M %p")
        .lstrip("0")
        .lower()
    )


def normalize_img(img: str | None) -> str | None:
    """Validate image reference for ``hlhp_shared_chat_v1``.

    Accepts only ``https://…`` / ``http://…`` URLs.
    Upload via hub media (or S3/selfie) first — data URLs are rejected to match Node.
    """
    if img is None:
        return None
    value = img.strip()
    if not value:
        return None

    if value.lower().startswith("data:"):
        raise ChatPayloadError(
            "img data URLs are not allowed — upload the image and pass an HTTPS URL"
        )

    if _HTTP_IMG.match(value):
        if len(value) > _MAX_HTTP_URL_CHARS:
            raise ChatPayloadError("img URL is too long")
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ChatPayloadError("img must be a valid http(s) URL")
        return value

    raise ChatPayloadError("img must be an http(s) URL")


def normalize_doc(doc: dict[str, Any] | None) -> dict[str, str] | None:
    if not doc:
        return None
    name = str(doc.get("name") or "").strip()
    size = str(doc.get("size") or "").strip()
    if not name:
        raise ChatPayloadError("doc.name is required")
    if len(name) > 256:
        raise ChatPayloadError("doc.name is too long")
    return {"name": name, "size": size or "—"}


def build_chat_message(
    *,
    who: str,
    txt: str = "",
    photo: bool = False,
    img: str | None = None,
    doc: dict[str, Any] | None = None,
    ts_ms: int | None = None,
) -> dict[str, Any]:
    """Build a chat append payload. Server may overwrite ``who``."""
    ts = ts_ms if ts_ms is not None else now_ms()
    text = (txt or "").strip()
    image = normalize_img(img)
    attachment = normalize_doc(doc)
    is_photo = bool(photo) or bool(image)

    if not text and not is_photo and not attachment:
        raise ChatPayloadError("message requires txt, img/photo, or doc")

    msg: dict[str, Any] = {
        "who": who,
        "txt": text,
        "photo": is_photo,
        "time": format_chat_time(ts),
        "ts": ts,
    }
    if image:
        msg["img"] = image
    if attachment:
        msg["doc"] = attachment
    return msg
