#!/usr/bin/env python3
"""Send a one-off HLHP ops test email via SES SMTP.

  python scripts/send_hlhp_ops_test_email.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = ROOT / ".env"
    if env_path.is_file():
        load_dotenv(env_path)


async def main() -> int:
    _load_env()
    from app.hlhp.services.ops_email import ops_alert_recipients, send_ops_email, ses_configured

    if not ses_configured():
        print("SES_* env vars missing — add them to .env first")
        return 1
    to = ops_alert_recipients()
    ok = await send_ops_email(
        subject="[HLHP] Ops email test — weather quota alerts ready",
        body=(
            "This is a test from AI-Tools HLHP.\n\n"
            "If you received this, SES SMTP ops alerts are configured.\n"
            "You will get emails at 70% / 90% of WeatherAPI monthly or "
            "Open-Meteo daily limits, and on HTTP 403/429.\n"
        ),
        to=to,
    )
    print("sent" if ok else "failed", "->", ", ".join(to))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
