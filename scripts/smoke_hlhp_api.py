"""Smoke test for HL legacy + HLHP v2 routes.

Run:
  python scripts/smoke_hlhp_api.py

Guest HLHP v2 calls use raw env fields (no weather API or Mongo required).
Legacy v1/v2 routes may call external weather services when lat/lng are used.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Allow `python scripts/smoke_hlhp_api.py` from repo root
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Windows consoles may default to cp1252; app.main prints unicode on import
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def _ok(label: str, status: int, detail: str = "") -> None:
    suffix = f" — {detail}" if detail else ""
    print(f"  OK  {label} ({status}){suffix}")


def _fail(label: str, status: int, body: str) -> None:
    print(f"  FAIL {label} ({status})")
    print(body[:1200])


async def _smoke_hlhp_v2(client) -> bool:
    """HLHP v2 — health, guest scan, symptom tap (no Mongo)."""
    ok = True

    r = await client.get("/api/hlhp/health")
    if r.status_code == 200 and r.json().get("ok"):
        body = r.json()
        _ok("GET /api/hlhp/health", r.status_code, f"{body['rule_count']} rules, v{body['snapshot_version']}")
    else:
        _fail("GET /api/hlhp/health", r.status_code, r.text)
        ok = False

    scan_body = {
        "user_id": None,
        "city": "Mumbai",
        "local_time": "2026-05-12T08:32:00+05:30",
        "raw_uvi": 8.0,
        "raw_aqi": 145,
        "raw_rh": 72.0,
        "raw_temp": 31.0,
    }
    r = await client.post("/api/hlhp/scan", json=scan_body)
    if r.status_code == 200:
        data = r.json()
        headline = (data["alerts"][0]["l1"][:100] + "…") if data.get("alerts") else "(no alerts)"
        _ok(
            "POST /api/hlhp/scan (guest)",
            r.status_code,
            f"mode={data['mode']}, outdoor_ok={data['outdoor_ok_score']}, alerts={len(data['alerts'])}, "
            f"first: {headline}",
        )
    else:
        _fail("POST /api/hlhp/scan (guest)", r.status_code, r.text)
        ok = False

    symptom_body = {
        "user_id": None,
        "symptom_keyword": "oily",
        "city": "Mumbai",
        "local_time": "2026-06-18T14:00:00+05:30",
        "raw_uvi": 8.0,
        "raw_aqi": 120,
        "raw_rh": 70.0,
        "raw_temp": 32.0,
    }
    r = await client.post("/api/hlhp/symptom_tap", json=symptom_body)
    if r.status_code == 200 and r.json().get("headline"):
        data = r.json()
        _ok("POST /api/hlhp/symptom_tap (guest)", r.status_code, data["headline"][:80])
    else:
        _fail("POST /api/hlhp/symptom_tap (guest)", r.status_code, r.text)
        ok = False

    if os.getenv("MONGO_URI") or os.getenv("PRODUCTION_MONGO_URI"):
        action_body = {
            "user_id": "smoke_test_user",
            "routine_action": "apply_sunscreen",
            "current_time": "2026-06-18T09:00:00+05:30",
            "location_city": "Mumbai",
            "raw_uvi": 8.0,
            "raw_aqi": 120,
            "raw_rh": 55.0,
            "raw_temp": 30.0,
        }
        r = await client.post("/api/hlhp/action_tap", json=action_body)
        if r.status_code == 200 and r.json().get("streak") is not None:
            data = r.json()
            _ok(
                "POST /api/hlhp/action_tap",
                r.status_code,
                f"streak={data['streak']}, longest={data['longest_ever']}",
            )
        else:
            _fail("POST /api/hlhp/action_tap", r.status_code, r.text)
            ok = False
    else:
        print("  SKIP POST /api/hlhp/action_tap (set MONGO_URI to exercise)")

    return ok


async def _smoke_legacy(client) -> bool:
    """HL v1/v2 legacy alert routes."""
    ok = True
    params = {"lat": 18.5628, "lng": 73.7700}

    r = await client.get("/api/hl/v1/alert", params=params)
    if r.status_code == 200:
        headline = (r.json().get("compact_headline") or "")[:100]
        _ok("GET /api/hl/v1/alert", r.status_code, headline or "(empty headline)")
    else:
        _fail("GET /api/hl/v1/alert", r.status_code, r.text)
        ok = False

    preview_params = {
        **params,
        "skin_type": "combination",
        "primary_concern": "acne",
        "gender": "female",
        "age_bracket": "25-30",
        "hair_type": "straight",
        "hair_concern": "dandruff",
    }
    r = await client.get("/api/hl/v2/alert/preview", params=preview_params)
    if r.status_code == 200:
        data = r.json()
        headline = (data.get("personalized_headline") or "")[:100]
        _ok(
            "GET /api/hl/v2/alert/preview",
            r.status_code,
            f"{headline or '(empty)'}; hair_alert={bool(data.get('hair_alert'))}",
        )
    else:
        _fail("GET /api/hl/v2/alert/preview", r.status_code, r.text)
        ok = False

    return ok


async def main_async() -> int:
    try:
        from httpx import ASGITransport, AsyncClient
    except ImportError:
        print("httpx is required: pip install httpx")
        return 1

    from app.main import app

    print("HLHP smoke test\n")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=120.0) as client:
        print("HLHP v2")
        v2_ok = await _smoke_hlhp_v2(client)
        print("\nLegacy HL")
        legacy_ok = await _smoke_legacy(client)

    if v2_ok and legacy_ok:
        print("\nAll smoke checks passed.")
        return 0
    print("\nSome smoke checks failed.")
    return 1


def main() -> None:
    raise SystemExit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
