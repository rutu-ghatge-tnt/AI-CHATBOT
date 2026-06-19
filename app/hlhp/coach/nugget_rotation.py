from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from app.hlhp.evidence.models import ScienceNugget


def pick_fresh_nugget(
    nuggets: list[ScienceNugget],
    *,
    seen_ids: set[int],
    mood_factor: str | None = None,
) -> ScienceNugget | None:
    pool = [n for n in nuggets if n.text and n.id not in seen_ids]
    if not pool:
        pool = [n for n in nuggets if n.text]
    if not pool:
        return None
    if mood_factor:
        aligned = [n for n in pool if n.factor == mood_factor]
        if aligned:
            pool = aligned
    return random.choice(pool)
