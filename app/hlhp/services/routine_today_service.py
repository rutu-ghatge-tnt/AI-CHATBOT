"""
What's Different Today — port of V7 `routineToday()` against evidence routine_rules.

Matches live V4 factor band keys + profile skin/concern filters; returns top 3.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.hlhp.models.profile import UserProfile
from app.hlhp.models.scan import WhatsDifferentItem
from app.hlhp.services.scenario_engine import (
    resolve_library_concerns,
    resolve_skin,
)
from app.hlhp.services.v4_scoring_engine import V4Evaluation

_DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "routine_rules_v1.json"

_ALLOWED_TYPES = frozenset(
    {"REINFORCE", "PROTECT", "SKIP", "ADD", "SWAP", "MANAGE", "KEEP"}
)


@lru_cache(maxsize=1)
def load_routine_rules() -> list[dict[str, Any]]:
    raw = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    rules = raw.get("rules") if isinstance(raw, dict) else raw
    if not isinstance(rules, list):
        return []
    out: list[dict[str, Any]] = []
    for r in rules:
        if not isinstance(r, dict):
            continue
        item = dict(r)
        t = str(item.get("type") or "").strip().upper()
        item["type"] = t if t in _ALLOWED_TYPES else "KEEP"
        out.append(item)
    return out


def _pass_filter(rule_val: str | None, actual: str | None) -> bool:
    """Match `any` / exact / `except:X`. Pipe-separated rule values OR-match."""
    f = str(rule_val or "any").strip().lower()
    if not f or f == "any":
        return True
    v = str(actual or "").strip().lower()
    if f.startswith("except:"):
        return f[7:].strip() != v
    if "|" in f:
        parts = [p.strip() for p in f.split("|") if p.strip()]
        return any(p == v for p in parts)
    return f == v


def _pass_concern(rule_val: str | None, concerns: list[str]) -> bool:
    if not concerns:
        return _pass_filter(rule_val, None)
    return any(_pass_filter(rule_val, c) for c in concerns)


def _live_bands(v4_eval: V4Evaluation) -> dict[str, str]:
    return {d.factor: d.key for d in v4_eval.drivers}


def select_routine_today(
    v4_eval: V4Evaluation,
    profile: UserProfile | None,
    *,
    guest_mode: bool = False,
    limit: int = 3,
) -> list[WhatsDifferentItem]:
    """
    Filter / sort evidence routine rules for today's live driver bands.

    Factor `any` rules match whenever any live band is present (always).
    Factor-specific rules require that factor's band key ∈ rule.bands.
    """
    live = _live_bands(v4_eval)
    skin = resolve_skin(profile, guest_mode)
    concerns = resolve_library_concerns(profile, guest_mode)
    # Guest path uses concern "None" — still allow `any` concern rules.
    if guest_mode:
        concerns = concerns or ["None"]

    matched: list[dict[str, Any]] = []
    for rule in load_routine_rules():
        factor = str(rule.get("factor") or "any").strip()
        bands = rule.get("bands") or []
        if not isinstance(bands, list):
            bands = []
        if factor.lower() == "any":
            band_ok = bool(live)
        else:
            live_band = live.get(factor)
            band_ok = bool(live_band and live_band in bands)
        if not band_ok:
            continue
        if not _pass_filter(rule.get("skin"), skin):
            continue
        if not _pass_concern(rule.get("concern"), concerns):
            continue
        matched.append(rule)

    matched.sort(key=lambda r: int(r.get("priority") or 9))

    seen: set[str] = set()
    out: list[WhatsDifferentItem] = []
    for rule in matched:
        headline = str(rule.get("headline") or "").strip()
        if not headline or headline in seen:
            continue
        seen.add(headline)
        out.append(
            WhatsDifferentItem(
                id=str(rule.get("id") or headline),
                type=str(rule.get("type") or "KEEP"),
                headline=headline,
                why=str(rule.get("why") or ""),
                timing=str(rule.get("timing") or ""),
                factor=str(rule.get("factor") or "any"),
                priority=int(rule.get("priority") or 9),
            )
        )
        if len(out) >= limit:
            break
    return out
