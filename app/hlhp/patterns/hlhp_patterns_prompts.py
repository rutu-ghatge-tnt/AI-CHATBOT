"""
hlhp_patterns_prompts.py
========================
The AI-narration PROMPTS for the HLHP Patterns tab.

Kept separate from `hlhp_patterns_engine.py` so the copy team can iterate on
wording without touching engine logic. The engine imports `VOICE_RULES` and the
builder functions here.

GOLDEN RULE (enforced by the engine's validate_narration()):
    The model may ONLY narrate numbers already present in the input packet.
    It must NOT invent patterns, numbers, causes, product advice, or medical
    claims beyond the supplied library text. Detection is the algorithm's job.

Three outputs are produced from one packet:
    - pattern_narrative : the "say" + "plain" + "cc_note" lines for each card
    - unlock_headline   : the one-line identity + celebration copy at unlock
    - weekly_digest     : the post-unlock "what changed this week" strip

Usage (with any LLM client):
    from hlhp_patterns_prompts import VOICE_RULES, build_messages, OUTPUT_SCHEMA
    packet = build_narration_packet(..., voice_rules=VOICE_RULES)   # engine fn
    messages = build_messages(packet)
    resp = llm.chat(messages, response_format=OUTPUT_SCHEMA, temperature=0.4)
    # then engine.validate_narration(text, packet) on every string before caching
"""

from __future__ import annotations
import json


# ============================================================================
# 1. VOICE RULES — passed into the packet AND embedded in the system prompt.
#    Mirrors the Copy Bank "Voice & Rules" sheet.
# ============================================================================
VOICE_RULES = """\
VOICE (SkinBB HLHP):
- The SFI *reads* the weather; it never scores, grades, or judges the user.
- Warm, plain, second-person ("your skin", "you"). Like a knowledgeable friend.
- Short. One idea per sentence. No jargon, no hedging, no exclamation spam.
- Bands are proper nouns when named, but prefer plain words ("humid days").
- Frame bad days as the environment's doing, never the user's failure.
- Frame good days as the user's win.
- No product recommendations. No prescriptions. No medical claims beyond the
  supplied library text.
- Never use the words: "score", "grade", "fail", "should", "cure", "guarantee".
- Emoji: at most one, only in unlock/digest headlines, never in clinical lines.
"""


# ============================================================================
# 2. SYSTEM PROMPT — role + the hard grounding constraint.
# ============================================================================
SYSTEM_PROMPT = """\
You are the narration writer for SkinBB's HLHP Patterns feature. You turn
ALREADY-COMPUTED skin-pattern statistics into short, warm, plain-language copy.

CRITICAL GROUNDING RULES:
1. Use ONLY the facts in the JSON packet provided. Do not add patterns, numbers,
   drivers, symptoms, causes, or advice that are not in the packet.
2. Every number you write MUST appear in the packet (E, H, match as a %, log_days,
   dates, hours). If a number isn't in the packet, do not state it.
3. If you are unsure, say less. Never guess or embellish.
4. No medical claims beyond the packet's `library_l1` text. No product advice.
5. Follow the VOICE rules exactly.

You will be given VOICE rules and a DATA packet. Return ONLY valid JSON matching
the requested schema — no preamble, no markdown.
"""


# ============================================================================
# 3. OUTPUT SCHEMA — pass to a structured-output / JSON-mode capable model.
# ============================================================================
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "patterns": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},          # "humidity:breakout"
                    "say": {"type": "string"},         # ≤ 60 chars, the headline claim
                    "plain": {"type": "string"},       # ≤ 160 chars, the human detail
                    "cc_note": {"type": "string"},     # ≤ 90 chars, chart caption
                },
                "required": ["id", "say", "plain", "cc_note"],
            },
        },
        "unlock_headline": {"type": "string"},         # ≤ 120 chars
        "unlock_identity": {"type": "string"},         # ≤ 140 chars, "your skin in one line"
        "weekly_digest": {"type": "string"},           # ≤ 120 chars
    },
    "required": ["patterns"],
}


# ============================================================================
# 4. FEW-SHOT EXAMPLE — one grounded example so the model copies the register.
#    Every number here traces to the example packet. This teaches "narrate,
#    don't invent."
# ============================================================================
_EXAMPLE_PACKET = {
    "profile": {"skin": "Combination", "concern": "Acne"},
    "city": "Pune",
    "patterns": [{
        "driver": "humidity", "symptom": "breakout", "E": 12, "H": 10,
        "match": 0.83, "lag_hours": 24, "zones": ["cheeks"],
        "weekday_hits": 8, "weekend_hits": 2, "label": "HIGH",
        "library_l1": "High humidity increases sebum and occlusion, a known acne trigger.",
        "pmids": ["PMID 31284694"],
    }],
    "month_summary": {"log_days": 26, "surges": [
        {"date": "2026-06-12", "driver": "temp", "symptom_logged": True},
        {"date": "2026-06-24", "driver": "temp", "symptom_logged": False},
    ]},
}
_EXAMPLE_OUTPUT = {
    "patterns": [{
        "id": "humidity:breakout",
        "say": "Humid days → breakouts, usually the next day",
        "plain": "It happened 10 of 12 humid days — your cheeks first, and more on "
                 "workdays (8 of 10). Weekends with the same weather barely showed it.",
        "cc_note": "Your breakouts line up with the tall humid-day bars.",
    }],
    "unlock_headline": "Your skin has patterns. We found what sets it off.",
    "unlock_identity": "Humidity is your trigger — it caught you 10 of 12 humid days last month.",
    "weekly_digest": "Your humidity pattern held again this week — 26 logs keeping it sharp.",
}


# ============================================================================
# 5. USER-PROMPT BUILDERS
# ============================================================================
def _user_prompt(packet: dict, outputs_wanted: list[str]) -> str:
    return (
        f"{packet.get('voice_rules', VOICE_RULES)}\n\n"
        f"OUTPUTS WANTED: {', '.join(outputs_wanted)}\n\n"
        f"DATA PACKET (use only these facts and numbers):\n"
        f"{json.dumps({k: v for k, v in packet.items() if k != 'voice_rules'}, indent=2)}\n\n"
        f"Write the requested outputs as JSON matching the schema. "
        f"Every number you use must be in the packet above."
    )


def build_messages(packet: dict, include_example: bool = True) -> list[dict]:
    """Return a chat-style message list ready for an LLM call.
    `packet` is the output of engine.build_narration_packet()."""
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    if include_example:
        msgs.append({"role": "user",
                     "content": _user_prompt({**_EXAMPLE_PACKET, "voice_rules": VOICE_RULES},
                                             ["pattern_narrative", "unlock_headline", "weekly_digest"])})
        msgs.append({"role": "assistant", "content": json.dumps(_EXAMPLE_OUTPUT)})
    outputs = packet.get("outputs_wanted",
                         ["pattern_narrative", "unlock_headline", "weekly_digest"])
    msgs.append({"role": "user", "content": _user_prompt(packet, outputs)})
    return msgs


# ============================================================================
# 6. LIFECYCLE / NOTIFICATION COPY — templated (NOT AI). These are the strings
#    from patterns-tab-rules-v1.md §6, with {vars} the engine fills in. Kept here
#    so all Patterns copy lives in one place. These are deterministic on purpose:
#    growth-loop nudges must be predictable and rate-limited, not model-generated.
# ============================================================================
LIFECYCLE_COPY = {
    # new user (LOCKED, days 0-4)
    "locked.empty":    "This screen learns you. Log most days for a month — 25 of 30 — "
                       "and your personal skin patterns unlock.",
    "locked.coach":    "Patterns need history. Every log you save is a piece of the picture.",
    "locked.push_d2":  "Two logs in. Keep going — your skin starts explaining itself at 25.",
    # on track
    "ontrack.meter":   "{log_days} of 25 logs — ahead of pace. Your patterns unlock around {date}.",
    "ontrack.coach":   "You're logging like clockwork. {remaining} more and this tab comes alive.",
    "ontrack.push":    "One week to your patterns. Your streak is doing the heavy lifting.",
    "ontrack.ribbon":  "Early signal — it settles as your logs grow.",
    # behind pace (rate-limit push to max 1/week)
    "behind.tab":      "You're at {log_days} of 25 logs. No reset, no penalty — your window "
                       "moves with you. {remaining} more logging days and this unlocks.",
    "behind.coach":    "Missed days don't erase progress, they just stretch the wait. "
                       "Tonight's log counts the moment you save it.",
    "behind.push":     "Your patterns are {remaining} logs away — the window rolls with you, "
                       "so tonight still counts.",
    # calm-month (consistency met, exposure pending)
    "stability.wait":  "Calm month so far — patterns need a bit of rough weather.",
    # unlock
    "unlock.screen":   "Your skin has patterns.",
    "unlock.stats":    "30 days. {log_days} logs. {n} patterns found. "
                       "Most people never learn this about themselves.",
    "unlock.push":     "It's ready. Your skin's first patterns are in.",
    "unlock.coach":    "This is what a month of showing up looks like. "
                       "From here, every log makes these sharper.",
    # post-unlock sustain
    "active.digest":   "This week strengthened one pattern and put a new one on watch.",
    "active.newtease": "Something new is emerging in your logs. "
                       "Two more confirmations and we can name it.",
    "fading.banner":   "Patterns fade when logs stop — four logs this week keeps them live.",
    "paused.react":    "Your patterns are paused, not lost. Three logs in five days brings them back.",
    "demote.copy":     "This link is weakening — we're watching it.",
    # "Warn me next time" — confirmation toast + the pre-emptive push it enables
    "warn.on":         "Done — we'll warn you when {driver} climbs again.",
    "warn.off":        "Okay, we'll stop warning you about {driver}.",
    "warn.push":       "Heads up — {driver} is climbing {when}. It's tied to your "
                       "{symptom}, so keep your routine steady today.",
}


def lifecycle(key: str, **vars) -> str:
    """Fetch + fill a lifecycle string. e.g. lifecycle('behind.push', remaining=11)."""
    return LIFECYCLE_COPY[key].format(**vars)


def pattern_alert_copy(driver_leg: str, symptom_leg: str, when: str) -> str:
    """Render the pre-emptive 'Warn me next time' push from a fired alert
    (engine.check_pattern_alerts() output). Deterministic template — a short
    factual heads-up needs no LLM. Swap to AI only if you want copy variety."""
    return lifecycle("warn.push", driver=driver_leg, symptom=symptom_leg, when=when)


# ============================================================================
# 7. TRIGGER MAP — WHEN each prompt fires. Two clocks:
#    (a) AI prompts (LLM calls) fire ONLY on data-changing events, then cache.
#    (b) Lifecycle templates render on demand (free) or on scheduled pushes.
#    Never call the LLM on tab open — serve the cache.
# ============================================================================
# kind: "ai"  -> costs tokens, cache the result, regenerate only on the event
#       "tpl" -> string.format(), effectively free, render every time
TRIGGER_MAP = {
    # ---- AI (event-driven, cached in narration_cache) ----
    "unlock":            {"kind": "ai",  "on": "gates first met (one-time)",
                          "outputs": ["unlock_headline", "unlock_identity", "pattern_narrative"],
                          "scope": "all promoted patterns"},
    "weekly_digest":     {"kind": "ai",  "on": "weekly job, Sun 02:00 local, ACTIVE users only",
                          "outputs": ["weekly_digest"],
                          "scope": "digest line only (NOT the cards, unless dirty)"},
    "pattern_promoted":  {"kind": "ai",  "on": "detection promotes a NEW pattern",
                          "outputs": ["pattern_narrative"],
                          "scope": "the ONE new card"},
    "pattern_demoted":   {"kind": "ai",  "on": "lift < 1.2 for 14d",
                          "outputs": ["pattern_narrative"],
                          "scope": "the ONE demoted card"},
    "profile_change":    {"kind": "ai",  "on": "skin/concern changed",
                          "outputs": ["pattern_narrative"],
                          "scope": "affected cards only, marked recalibrating"},

    # ---- Templates (rendered on demand OR on a scheduled push) ----
    "locked_screen":     {"kind": "tpl", "on": "pre-unlock screen render",
                          "keys": ["locked.empty", "locked.coach"]},
    "ontrack_screen":    {"kind": "tpl", "on": "pre-unlock screen render (on pace)",
                          "keys": ["ontrack.meter", "ontrack.coach", "ontrack.ribbon"]},
    "behind_screen":     {"kind": "tpl", "on": "pre-unlock screen render (behind pace)",
                          "keys": ["behind.tab", "behind.coach"]},
    "push_d2":           {"kind": "tpl", "on": "scheduled, day 2, once ever",
                          "keys": ["locked.push_d2"]},
    "push_ontrack":      {"kind": "tpl", "on": "scheduled, 1/week if on pace",
                          "keys": ["ontrack.push"]},
    "push_behind":       {"kind": "tpl", "on": "scheduled, MAX 1/week",
                          "keys": ["behind.push"]},
    "push_unlock":       {"kind": "tpl", "on": "unlock transition, once ever",
                          "keys": ["unlock.push"]},
    "push_fading":       {"kind": "tpl", "on": "ACTIVE->FADING transition, 1/episode",
                          "keys": ["fading.banner"]},
    "push_paused":       {"kind": "tpl", "on": "FADING->PAUSED transition, 1/episode",
                          "keys": ["paused.react"]},
    "banner_fading":     {"kind": "tpl", "on": "ACTIVE->FADING transition, 1/episode",
                          "keys": ["fading.banner"]},
    "banner_paused":     {"kind": "tpl", "on": "FADING->PAUSED transition, 1/episode",
                          "keys": ["paused.react"]},
    "digest_render":     {"kind": "tpl", "on": "ACTIVE screen render",
                          "keys": ["active.digest", "active.newtease"]},
    # "Warn me next time" — subscription toggle + the pre-emptive push
    "warn_toggle":       {"kind": "tpl", "on": "user taps 'Warn me next time' on a card",
                          "keys": ["warn.on", "warn.off"]},
    "warn_push":         {"kind": "tpl", "on": "forecast job: subscribed driver forecast "
                                               "adverse within 2 days (once per episode)",
                          "keys": ["warn.push"]},
}


# ============================================================================
# 8. TOKEN / COST CONTROL — reduce spend WITHOUT weakening the output.
#    Principle: the algorithm is cheap and deterministic; only pay the LLM for
#    NEW meaning. Five levers, in order of impact:
#
#    (1) Dirty-check — never regenerate a card whose numbers didn't change.
#        Store a hash of each pattern's inputs; skip if unchanged. This alone
#        removes ~90% of would-be calls (weather is stable most days).
#
#    (2) Regenerate the DELTA, not the set — on promote/demote/profile change,
#        send ONLY the affected card(s). `select_outputs()` + `slim_packet()`
#        below trim the request to exactly what's needed.
#
#    (3) Amortize the fixed prefix — the system prompt + few-shot example are
#        identical every call. Use provider PROMPT CACHING (Anthropic/OpenAI)
#        on that static prefix so you pay for it once, not per card. After the
#        model is dialed in, you can also drop the few-shot (include_example=
#        False) to save ~250 tokens/call — keep it while tuning.
#
#    (4) Batch the weekly refresh — one call covering all of a user's active
#        cards shares the prefix once, instead of N calls. Cheaper than per-card
#        AND lets the model keep voice consistent across the set.
#
#    (5) Small model + tight caps — this is constrained, grounded narration, not
#        open reasoning. A small/cheap model (e.g. Haiku-class) with
#        max_tokens≈220 and temperature≈0.4 is plenty. Reserve a larger model
#        only for the once-in-a-lifetime unlock moment if you want extra polish.
#
#    Net effect: steady-state cost ≈ (new patterns/week) + (1 weekly digest) per
#    active user — a handful of small calls, not one-per-open.
# ============================================================================
def input_hash(pattern_stat: dict) -> str:
    """Stable hash of the numbers that drive a card's copy. If unchanged since
    last generation, DON'T call the LLM — reuse the cached narration.
    Feed the same fields you put in the packet (E,H,match,zones,weekday/weekend)."""
    import hashlib
    keys = ("driver", "symptom", "E", "H", "match", "zones",
            "weekday_hits", "weekend_hits", "label")
    basis = json.dumps({k: pattern_stat.get(k) for k in keys}, sort_keys=True)
    return hashlib.sha1(basis.encode()).hexdigest()[:16]


def should_regenerate(pattern_stat: dict, cached_hash: str | None) -> bool:
    """Lever (1): only pay the LLM when the inputs moved."""
    return cached_hash != input_hash(pattern_stat)


def slim_packet(packet: dict, only_pattern_ids: list[str] | None = None) -> dict:
    """Lever (2): shrink the request to just the card(s) being (re)generated and
    drop fields the copy never uses. Cuts input tokens on delta refreshes."""
    p = dict(packet)
    if only_pattern_ids is not None:
        p["patterns"] = [x for x in p.get("patterns", [])
                         if f"{x['driver']}:{x['symptom']}" in only_pattern_ids]
        # unlock/digest lines aren't needed on a single-card delta refresh
        p["outputs_wanted"] = ["pattern_narrative"]
    # library_l1 can be long; keep only if a card actually needs a mechanism line
    return p


def select_outputs(event: str) -> list[str]:
    """Map a trigger to the minimal output set to request (don't ask for copy
    you won't use — e.g. a weekly digest doesn't need the unlock headline)."""
    return TRIGGER_MAP.get(event, {}).get("outputs", ["pattern_narrative"])


# ============================================================================
# 9. DEMO
# ============================================================================
if __name__ == "__main__":
    print("=== SYSTEM PROMPT ===\n", SYSTEM_PROMPT)
    print("=== EXAMPLE messages (first 2) ===")
    for m in build_messages({**_EXAMPLE_PACKET, "voice_rules": VOICE_RULES,
                             "outputs_wanted": ["pattern_narrative"]})[:2]:
        print(f"\n[{m['role']}]\n{m['content'][:500]}")
    print("\n=== lifecycle() sample ===")
    print(lifecycle("behind.push", remaining=11))
    print(lifecycle("ontrack.meter", log_days=18, date="12 July"))
