"""Cached AI narration for Patterns v2 — templates now, LLM when configured."""

from __future__ import annotations

import logging
import os
from typing import Any

from app.hlhp.patterns.hlhp_patterns_engine import (
    Pattern,
    PatternState,
    build_narration_packet,
    narration_fallback,
    pattern_to_card,
    validate_narration,
)
from app.hlhp.patterns.hlhp_patterns_prompts import VOICE_RULES, build_messages, lifecycle
from app.hlhp.services.pattern_state_store import get_narration_cache, save_narration_entry

logger = logging.getLogger(__name__)


def _template_narration_for_patterns(patterns: list[Pattern]) -> dict[str, Any]:
    """Deterministic card copy from engine templates (always available)."""
    cards = []
    for p in patterns:
        if p.status != "promoted":
            continue
        card = pattern_to_card(p, subscribed=False)
        cards.append(
            {
                "id": f"{p.driver}:{p.symptom}",
                "say": card["say"],
                "plain": card["plain"],
                "cc_note": card["cc_note"],
            }
        )
    return {"patterns": cards}


async def get_patterns_narration(user_id: str) -> dict[str, Any]:
    cached = await get_narration_cache(user_id)
    if cached:
        return cached
    return {}


async def _call_llm(packet: dict) -> dict[str, Any] | None:
    """Optional Anthropic narration — skipped when API key absent."""
    api_key = (os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY") or "").strip()
    if not api_key:
        return None
    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=api_key)
        messages = build_messages(packet, include_example=True)
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        user_parts = [m for m in messages if m["role"] != "system"]
        resp = client.messages.create(
            model=os.getenv("HLHP_PATTERNS_NARRATION_MODEL", "claude-3-5-haiku-latest"),
            max_tokens=220,
            temperature=0.4,
            system=system,
            messages=[{"role": m["role"], "content": m["content"]} for m in user_parts],
        )
        text = ""
        for block in resp.content:
            if hasattr(block, "text"):
                text += block.text
        import json

        return json.loads(text)
    except Exception as exc:
        logger.warning("patterns LLM narration failed: %s", exc)
        return None


async def refresh_narration_on_unlock(
    user_id: str,
    ps: PatternState,
    patterns: list[Pattern],
    profile: dict,
) -> None:
    promoted = [p for p in patterns if p.status == "promoted"]
    month_summary = {"log_days": ps.log_days_30, "surges": []}
    packet = build_narration_packet(ps, promoted, profile, month_summary, {}, voice_rules=VOICE_RULES)
    packet["outputs_wanted"] = ["pattern_narrative", "unlock_headline", "unlock_identity"]

    llm_out = await _call_llm(packet)
    if llm_out and llm_out.get("patterns"):
        valid = True
        for card in llm_out["patterns"]:
            blob = " ".join(str(card.get(k, "")) for k in ("say", "plain", "cc_note"))
            if not validate_narration(blob, packet):
                valid = False
                break
        if valid:
            for card in llm_out["patterns"]:
                pid = card.get("id")
                await save_narration_entry(
                    user_id,
                    kind="pattern",
                    text=card.get("say", ""),
                    pattern_id=pid,
                    say=card.get("say"),
                    plain=card.get("plain"),
                    cc_note=card.get("cc_note"),
                    valid=True,
                )
            if llm_out.get("unlock_headline"):
                await save_narration_entry(
                    user_id,
                    kind="unlock_headline",
                    text=str(llm_out["unlock_headline"]),
                )
            if llm_out.get("unlock_identity"):
                await save_narration_entry(
                    user_id,
                    kind="unlock_identity",
                    text=str(llm_out["unlock_identity"]),
                )
            return

    # Template fallback
    templ = _template_narration_for_patterns(promoted)
    for card in templ.get("patterns", []):
        await save_narration_entry(
            user_id,
            kind="pattern",
            text=card.get("say", ""),
            pattern_id=card.get("id"),
            say=card.get("say"),
            plain=card.get("plain"),
            cc_note=card.get("cc_note"),
            valid=True,
        )
    await save_narration_entry(
        user_id,
        kind="unlock_headline",
        text="Your skin has patterns. We found what sets it off.",
    )
    await save_narration_entry(
        user_id,
        kind="unlock_identity",
        text=_unlock_identity_template(promoted),
    )


def _unlock_identity_template(patterns: list[Pattern]) -> str:
    if not patterns:
        return "Your first month of logs is in — keep going to sharpen what we find."
    top = patterns[0]
    return narration_fallback(top)


async def refresh_weekly_digest(
    user_id: str,
    ps: PatternState,
    patterns: list[Pattern],
    profile: dict,
) -> None:
    promoted = [p for p in patterns if p.status == "promoted"]
    month_summary = {"log_days": ps.log_days_30, "surges": []}
    packet = build_narration_packet(ps, promoted, profile, month_summary, {}, voice_rules=VOICE_RULES)
    packet["outputs_wanted"] = ["weekly_digest"]

    llm_out = await _call_llm(packet)
    text = None
    if llm_out and llm_out.get("weekly_digest"):
        candidate = str(llm_out["weekly_digest"])
        if validate_narration(candidate, packet):
            text = candidate

    if not text:
        text = lifecycle("active.digest")

    await save_narration_entry(user_id, kind="weekly_digest", text=text, valid=True)
