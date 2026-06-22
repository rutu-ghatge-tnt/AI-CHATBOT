from __future__ import annotations

import re

from app.hlhp.evidence.models import EvidenceFinding

_SUNSCREEN_RE = re.compile(r"\b(sunscreen|spf|outdoor protection)\b", re.I)


def mentions_sunscreen(text: str) -> bool:
    return bool(text and _SUNSCREEN_RE.search(text))


def night_gate_blocks(finding: EvidenceFinding, uvi_band: str) -> bool:
    if uvi_band != "off":
        return False
    texts = (
        finding.alert_l1_guest,
        finding.alert_l1_personalised,
        finding.alert_l1_evening_guest,
        finding.alert_l1_evening_personalised,
    )
    return any(mentions_sunscreen(t) for t in texts)


def guest_gate_blocks(finding: EvidenceFinding, guest_mode: bool) -> bool:
    if not guest_mode:
        return False
    return len(finding.user_filter) > 0


def internal_gate_blocks(finding: EvidenceFinding) -> bool:
    return not finding.is_surfaced_to_client()
