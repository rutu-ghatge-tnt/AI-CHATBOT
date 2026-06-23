"""Alert card copy — title, body, HOW routine chain, did-you-know (template-only)."""

from __future__ import annotations

import re

from app.hlhp.composition.vocabulary import mood_headline
from app.hlhp.core.phase import DayPhase
from app.hlhp.evidence.alert_quality import is_consumer_copy, pick_did_you_know, texts_overlap
from app.hlhp.evidence.models import EvidenceFinding
from app.hlhp.models.profile import UserProfile

_CONCERN_ALIASES: dict[str, str] = {
    "teen_acne": "acne",
    "pigmentation_pih": "pigmentation_pih",
    "pigmentation": "pigmentation_pih",
    "open_pores": "open_pores",
    "pores": "open_pores",
    "texture": "open_pores",
    "dryness": "dryness",
    "dehydration": "dryness",
    "skin_tan": "skin_tan",
    "tan": "skin_tan",
    "oily_skin": "oily_skin",
    "oily": "oily_skin",
    "redness": "sensitivity",
}

_PROFILE_TO_ROUTINE_CONCERN: dict[str, str] = {
    "acne": "acne",
    "pigmentation": "pigmentation_pih",
    "melasma": "melasma",
    "tan": "skin_tan",
    "pores": "open_pores",
    "texture": "open_pores",
    "dullness": "dullness",
    "sensitivity": "sensitivity",
    "dehydration": "dryness",
    "redness": "sensitivity",
    "dark_circles": "dark_circles",
    "aging": "aging",
}

_GUEST_FACTOR_ROUTINE: dict[str, str] = {
    "UV": "skin_tan",
    "Pollution": "sensitivity",
    "Temperature": "oily_skin",
    "Humidity": "dryness",
    "Lifestyle": "acne",
    "Nutritional Status": "aging",
}

_OILY_LIKE_SKIN = frozenset({"oily", "combination"})
_HABIT_SUFFIX_ACTIONS = frozenset({"blot", "reapply_sunscreen", "cool_compress"})
_BARRIER_ROUTINE_ACTIONS = frozenset({"layer_barrier", "layer_hydration"})

# Concerns with no dedicated routine sheet — try related routines before a single label.
_ROUTINE_CONCERN_FALLBACKS: dict[str, tuple[str, ...]] = {
    "dullness": ("pigmentation_pih", "dryness", "aging"),
}

_MOOD_SHORT_TITLE: dict[str, str] = {
    "sebum_rush_day": "Sebum-rush day",
    "easy_day": "Easy day",
    "comfortable_day": "Comfortable day",
    "manageable_day": "Manageable day",
    "combo_stress_day": "Combo-stress day",
    "stack_day": "Stack day",
    "barrier_stress_day": "Barrier-stress day",
    "pigment_overdrive_day": "Pigment-overdrive day",
    "oxidative_load_day": "Oxidative-load day",
    "routine_day": "Routine-hold day",
    "transition_day": "Transition day",
    "transition_shock_day": "Transition-shock day",
    "surge_day": "Surge day",
    "festival_day": "Festival day",
    "habit_anchor_day": "Habit-anchor day",
    "recovery_day": "Recovery day",
    "cumulative_load_day": "Cumulative-load day",
}

_ACTION_SUFFIX: dict[str, str] = {
    "blot": "Blotting tissue through the day",
    "reapply_sunscreen": "Reapply sunscreen through outdoor hours",
    "cool_compress": "Cool compress after heat exposure",
    "double_cleanse": "Double cleanse in the evening on outdoor or makeup days",
}

_ROUTINE_LABELS: dict[str, str] = {
    "apply_sunscreen": "Broad-spectrum sunscreen as a daily habit",
    "reapply_sunscreen": "Reapply sunscreen through outdoor hours",
    "cleanse_gentle": "Gentle gel cleanser",
    "cleanse_oil": "Oil cleanse first, then gel cleanser",
    "double_cleanse": "Double cleanse in the evening",
    "layer_hydration": "Hydrating serum underneath moisturizer",
    "layer_barrier": "Barrier-repair moisturizer",
    "layer_antioxidant": "Antioxidant serum in the morning",
    "layer_brightening": "Brightening serum on marks",
    "apply_retinoid_pm": "Retinoid at night, built up slowly",
    "take_supplement": "Oral supplement per your clinician",
}


def resolve_concern_id(
    finding: EvidenceFinding,
    profile: UserProfile | None,
) -> str:
    if profile is not None:
        primary = profile.primary_concern.value
        return _PROFILE_TO_ROUTINE_CONCERN.get(primary, primary)
    for token in finding.user_filter:
        if token.class_name == "concern":
            raw = token.value.strip().lower()
            return _CONCERN_ALIASES.get(raw, raw)
    if not finding.user_filter:
        return _GUEST_FACTOR_ROUTINE.get(finding.factor, "acne")
    return "acne"


def _phase_key(day_phase: DayPhase) -> str:
    return "evening" if day_phase == "evening" else "morning"


def _short_mood_title(mood_tag: str) -> str:
    key = (mood_tag or "").strip().lower()
    if not key:
        return ""
    if key in _MOOD_SHORT_TITLE:
        return _MOOD_SHORT_TITLE[key]
    headline = mood_headline(key)
    if headline.startswith("Today is a "):
        inner = headline[len("Today is a ") :].rstrip(".")
        return inner[0].upper() + inner[1:] if inner else headline
    return headline.rstrip(".")


def _title_hook(finding: EvidenceFinding) -> str:
    decode = (finding.body_sensation_decode or "").strip()
    if decode:
        clause = re.split(r"[.;]", decode, maxsplit=1)[0].strip()
        if len(clause) >= 12:
            return clause[0].lower() + clause[1:] if clause else clause
    symptom = (finding.symptom_keyword or "").replace("_", " ").strip()
    if symptom:
        return f"watch for {symptom} signals today"
    return ""


def compose_alert_title(finding: EvidenceFinding) -> str:
    """Short card title — mood line only; full copy lives in l2 body."""
    mood = _short_mood_title(finding.mood_verdict_tag)
    if mood:
        return mood
    hook = _title_hook(finding)
    if hook:
        return hook[0].upper() + hook[1:] if hook else hook
    body = (finding.alert_l1_personalised or finding.alert_l1_guest or "").strip()
    if body:
        return _first_clause(body, max_len=72)
    return (finding.sub_effect or "Today's skin alert").strip()[:72]


def pick_alert_body(
    finding: EvidenceFinding,
    *,
    guest_mode: bool,
    day_phase: DayPhase,
) -> str:
    return (finding.pick_l1(guest_mode=guest_mode, day_phase=day_phase) or "").strip()


STRIP_MAX_LEN = 120
_STRIP_EXCLUDE_RE = re.compile(r"barrier[- ]?repair", re.I)


def _split_sentences(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?]) +", cleaned) if part.strip()]


def _strip_clauses(text: str, *, max_clauses: int = 2, max_len: int = STRIP_MAX_LEN) -> str:
    """Up to two strip sentences; drop barrier-repair product lines."""
    clauses = [c for c in _split_sentences(text) if not _STRIP_EXCLUDE_RE.search(c)]
    if not clauses:
        return _truncate_strip(text, max_len)
    out = " ".join(clauses[:max_clauses])
    if not out.endswith((".", "!", "?")):
        out += "."
    if len(out) > max_len:
        return _truncate_strip(out, max_len)
    return out


def _truncate_strip(text: str, max_len: int = STRIP_MAX_LEN) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        return ""
    if len(cleaned) <= max_len:
        return cleaned
    cut = cleaned[:max_len].rsplit(" ", 1)[0].rstrip(",;—")
    return f"{cut}…"


def _first_clause(text: str, max_len: int = STRIP_MAX_LEN) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        return ""
    for sep in (". ", "! ", "? "):
        idx = cleaned.find(sep)
        if 0 < idx <= max_len:
            return cleaned[: idx + 1].strip()
    em = cleaned.find(" — ")
    if 0 < em <= max_len:
        return cleaned[:em].strip()
    return _truncate_strip(cleaned, max_len)


def _how_tail_clause(how_text: str | None) -> str:
    """Actionable habit line after the routine chain (e.g. blot mid-day)."""
    if not how_text:
        return ""
    segments = [s.strip() for s in how_text.split(".") if s.strip()]
    if len(segments) >= 2:
        return segments[-1].rstrip(".")
    if "→" in how_text:
        last = how_text.split("→")[-1].split(".")[0].strip()
        if len(last) >= 8:
            return f"{last[0].upper()}{last[1:]} is what helps most"
    return ""


def compose_outlook_subline(
    *,
    forecast_oneliner: str | None,
    how_text: str | None,
    alert_l2: str | None = None,
    guest_mode: bool = False,
) -> str | None:
    """
    Rich personalised copy beside the SFI gauge (UI spec Screen 2 mood_sub).
    Combines forecast template + routine habit from HOW chain.
    """
    base = (forecast_oneliner or "").strip()
    if guest_mode:
        return base or None

    clauses: list[str] = []
    if base:
        clauses.append(base.rstrip("."))

    tail = _how_tail_clause(how_text)
    if tail and tail.lower() not in " ".join(clauses).lower():
        clauses.append(tail.rstrip("."))

    if not clauses and how_text and "→" in how_text:
        chain = how_text.split(".")[0].strip()
        plain = chain.replace(" → ", ", then ")
        if plain:
            clauses.append(f"{plain} really helps today")

    if not clauses and alert_l2:
        fallback = _first_clause(alert_l2, max_len=220)
        if fallback:
            clauses.append(fallback.rstrip("."))

    if not clauses:
        return None
    out = ". ".join(clauses)
    return out if out.endswith(".") else f"{out}."


def compose_strip_headline(
    finding: EvidenceFinding | None,
    *,
    mood_headline_text: str | None,
    forecast_oneliner: str | None,
    outdoor_band: str | None,
    guest_mode: bool,
    day_phase: DayPhase,
    personalised: bool = False,
) -> str:
    """One-line copy for the home weather strip — never the full alert body."""
    if personalised and not guest_mode:
        forecast = (forecast_oneliner or "").strip()
        if forecast:
            return _strip_clauses(forecast)

    if finding is not None and personalised and not guest_mode:
        title = compose_alert_title(finding)
        if title:
            return _truncate_strip(title)
        body = pick_alert_body(finding, guest_mode=False, day_phase=day_phase)
        if body:
            return _first_clause(body)

    mood = (mood_headline_text or "").strip()
    if mood:
        return _truncate_strip(mood)

    if finding is not None:
        title = compose_alert_title(finding)
        if title:
            return _truncate_strip(title)
        body = pick_alert_body(finding, guest_mode=guest_mode, day_phase=day_phase)
        if body:
            return _first_clause(body)

    forecast = (forecast_oneliner or "").strip()
    if forecast:
        return _truncate_strip(forecast)

    band = (outdoor_band or "").strip()
    if band:
        return _truncate_strip(band)

    return "Open for today's skin outlook"


def pick_did_you_know_for_tile(finding: EvidenceFinding, *, body: str) -> str | None:
    explainer = (finding.alert_l2_explainer or "").strip()
    if explainer and is_consumer_copy(explainer):
        if explainer.lower() != body.strip().lower() and not texts_overlap(explainer, body):
            return explainer
    dyk = pick_did_you_know(finding, l2=body)
    if dyk and texts_overlap(dyk, body):
        return None
    return dyk


def _skin_type_matches(row: dict, skin_type: str | None) -> bool:
    variant = str(row.get("variant_skin_type") or "any").strip().lower()
    if variant in ("", "any"):
        return True
    if not skin_type:
        return True
    st = skin_type.strip().lower()
    if variant == "oily" and st in _OILY_LIKE_SKIN:
        return True
    return variant == st


def _pick_routine_rows(rows: list[dict], skin_type: str | None) -> list[dict]:
    """One step per step_order — prefer skin-specific row over any."""
    by_order: dict[int, dict] = {}
    for row in rows:
        order = int(row.get("step_order") or 0)
        if not _skin_type_matches(row, skin_type):
            continue
        variant = str(row.get("variant_skin_type") or "any").strip().lower()
        existing = by_order.get(order)
        if existing is None:
            by_order[order] = row
            continue
        ex_variant = str(existing.get("variant_skin_type") or "any").strip().lower()
        if ex_variant == "any" and variant != "any":
            by_order[order] = row
    return [by_order[k] for k in sorted(by_order)]


def _clean_step_text(text: str) -> str:
    cleaned = text.strip().rstrip(".")
    if " — " in cleaned:
        cleaned = cleaned.split(" — ", 1)[0].strip()
    if cleaned.lower().startswith("a "):
        cleaned = cleaned[2:]
    elif cleaned.lower().startswith("an "):
        cleaned = cleaned[3:]
    return cleaned[0].upper() + cleaned[1:] if cleaned else cleaned


def _format_how_chain(main_steps: list[str], suffix: str | None = None) -> str:
    if not main_steps and not suffix:
        return ""
    chain = " → ".join(main_steps)
    if suffix:
        return f"{chain}. {suffix.rstrip('.')}." if chain else f"{suffix.rstrip('.')}."
    return chain


def _framework_steps(
    routine_framework: list[dict],
    *,
    concern_id: str,
    phase: str,
    skin_type: str | None,
) -> list[str]:
    rows = [
        r
        for r in routine_framework
        if str(r.get("concern_id", "")).strip().lower() == concern_id
        and str(r.get("phase", "")).strip().lower() == phase
    ]
    picked = _pick_routine_rows(rows, skin_type)
    if not picked:
        picked = _pick_routine_rows(rows, None)
    steps: list[str] = []
    for row in picked:
        text = str(row.get("step_text") or "").strip()
        if text:
            steps.append(_clean_step_text(text))
    return steps


def _routine_concern_candidates(
    finding: EvidenceFinding,
    profile: UserProfile | None,
) -> list[str]:
    """Routine concern ids to try — primary profile concern, siblings, action hints, fallbacks."""
    candidates: list[str] = []

    def add(raw: str | None) -> None:
        if not raw:
            return
        cid = raw.strip().lower()
        if cid and cid not in candidates:
            candidates.append(cid)

    if profile is not None:
        add(resolve_concern_id(finding, profile))
        for concern in profile.skin_concerns:
            add(_PROFILE_TO_ROUTINE_CONCERN.get(concern.value, concern.value))
    else:
        add(resolve_concern_id(finding, None))

    action = (finding.routine_action or "").strip()
    if action in _BARRIER_ROUTINE_ACTIONS:
        add("dryness")

    primary = candidates[0] if candidates else ""
    for fallback in _ROUTINE_CONCERN_FALLBACKS.get(primary, ()):
        add(fallback)

    return candidates


def _framework_steps_for_finding(
    routine_framework: list[dict],
    *,
    finding: EvidenceFinding,
    profile: UserProfile | None,
    phase: str,
    skin_type: str | None,
) -> list[str]:
    for concern_id in _routine_concern_candidates(finding, profile):
        steps = _framework_steps(
            routine_framework,
            concern_id=concern_id,
            phase=phase,
            skin_type=skin_type,
        )
        if steps:
            return steps
    return []


def compose_how_routine(
    routine_framework: list[dict],
    finding: EvidenceFinding,
    *,
    profile: UserProfile | None,
    day_phase: DayPhase,
) -> str | None:
    phase = _phase_key(day_phase)
    skin_type = profile.skin_type.value if profile else None

    steps = _framework_steps_for_finding(
        routine_framework,
        finding=finding,
        profile=profile,
        phase=phase,
        skin_type=skin_type,
    )
    if not steps and phase == "morning":
        steps = _framework_steps_for_finding(
            routine_framework,
            finding=finding,
            profile=profile,
            phase="evening",
            skin_type=skin_type,
        )

    action = (finding.routine_action or "").strip()
    suffix = _ACTION_SUFFIX.get(action) if action in _HABIT_SUFFIX_ACTIONS else None

    if action and action not in _HABIT_SUFFIX_ACTIONS:
        label = _ROUTINE_LABELS.get(action)
        if label:
            if not steps or not any(label.lower() in s.lower() for s in steps):
                steps.append(_clean_step_text(label))

    if steps:
        return _format_how_chain(steps, suffix)

    if action:
        label = _ROUTINE_LABELS.get(action)
        if label:
            return label
        if " " in action:
            return action
        return action.replace("_", " ").strip().capitalize()

    implication = (finding.product_implication or "").strip()
    if implication and is_consumer_copy(implication):
        return implication

    return None
