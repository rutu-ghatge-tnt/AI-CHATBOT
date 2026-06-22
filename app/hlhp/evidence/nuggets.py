"""Science Nugget rotation per spec §10.1 habit drawer."""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Optional

from app.hlhp.evidence.models import ScienceNugget


def _rotation_seed(user_id: Optional[str], when: Optional[date] = None) -> int:
    day = (when or date.today()).isoformat()
    key = f"{user_id or 'guest'}:{day}"
    return int(hashlib.sha256(key.encode()).hexdigest()[:12], 16)


def rotate_nuggets(
    nuggets: list[ScienceNugget],
    *,
    count: int = 3,
    user_id: Optional[str] = None,
    factor: Optional[str] = None,
    when: Optional[date] = None,
) -> list[ScienceNugget]:
    pool = [n for n in nuggets if n.text]
    if factor:
        factor_pool = [n for n in pool if n.factor == factor]
        if factor_pool:
            pool = factor_pool
    if not pool:
        return []
    seed = _rotation_seed(user_id, when)
    ordered = sorted(pool, key=lambda n: (hash(f"{seed}:{n.id}") % 10_000, n.id))
    return ordered[:count]


def rotate_by_factor_diversity(
    nuggets: list[ScienceNugget],
    *,
    count: int = 3,
    user_id: Optional[str] = None,
    when: Optional[date] = None,
) -> list[ScienceNugget]:
    """Pick nuggets across factors for the habit/science drawer."""
    by_factor: dict[str, list[ScienceNugget]] = {}
    for n in nuggets:
        if n.text:
            by_factor.setdefault(n.factor, []).append(n)
    if not by_factor:
        return []
    seed = _rotation_seed(user_id, when)
    factors = sorted(by_factor.keys(), key=lambda f: hash(f"{seed}:factor:{f}") % 10_000)
    picked: list[ScienceNugget] = []
    idx = 0
    while len(picked) < count and factors:
        factor = factors[idx % len(factors)]
        bucket = sorted(
            by_factor[factor],
            key=lambda n: hash(f"{seed}:n:{n.id}") % 10_000,
        )
        for n in bucket:
            if n not in picked:
                picked.append(n)
                break
        idx += 1
        if idx > count * len(factors):
            break
    return picked[:count]
