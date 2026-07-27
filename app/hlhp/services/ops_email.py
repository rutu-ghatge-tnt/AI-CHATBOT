"""Ops email via Amazon SES SMTP (stdlib — no extra dependency)."""

from __future__ import annotations

import asyncio
import logging
import os
import smtplib
from email.message import EmailMessage
from typing import Sequence

logger = logging.getLogger(__name__)


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def ops_alert_recipients() -> list[str]:
    raw = _env(
        "HLHP_OPS_ALERT_EMAILS",
        "operations@skinbb.com,rutu.ghatge@techsntomes.com,ajit.m@techsntomes.com",
    )
    return [p.strip() for p in raw.split(",") if p.strip()]


def ses_configured() -> bool:
    return bool(
        _env("SES_HOST")
        and _env("SES_SMTP_USER")
        and _env("SES_SMTP_PASS")
        and _env("SES_FROM")
    )


def _send_sync(
    *,
    subject: str,
    body: str,
    to: Sequence[str],
) -> None:
    host = _env("SES_HOST", "email-smtp.ap-south-1.amazonaws.com")
    port = int(_env("SES_PORT", "587") or "587")
    user = _env("SES_SMTP_USER")
    password = _env("SES_SMTP_PASS")
    from_addr = _env("SES_FROM", "SkinBB <noreply@skinbb.com>")
    if not (user and password and to):
        raise RuntimeError("SES SMTP not configured or no recipients")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(to)
    msg.set_content(body)

    with smtplib.SMTP(host, port, timeout=20) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(user, password)
        smtp.send_message(msg)


async def send_ops_email(*, subject: str, body: str, to: Sequence[str] | None = None) -> bool:
    """Send an ops alert email. Returns True on success."""
    recipients = list(to) if to is not None else ops_alert_recipients()
    if not recipients:
        logger.warning("HLHP ops email skipped — no recipients")
        return False
    if not ses_configured():
        logger.warning("HLHP ops email skipped — SES_* env not set")
        return False
    try:
        await asyncio.to_thread(_send_sync, subject=subject, body=body, to=recipients)
        logger.info("HLHP ops email sent to %s subject=%s", recipients, subject)
        return True
    except Exception as exc:
        logger.warning("HLHP ops email failed: %s", exc)
        return False
