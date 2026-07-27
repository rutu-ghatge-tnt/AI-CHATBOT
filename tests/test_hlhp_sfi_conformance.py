"""HLHP engine conformance tests — code vs Scenario Library v3.7.

Run from repo root:
  pytest tests/test_hlhp_sfi_conformance.py -q
"""
from __future__ import annotations

import itertools
import json
import os
from pathlib import Path

import pytest

from app.hlhp.data.v4_scoring_data import (
    ARCHETYPES,
    CONCERN_ARCHETYPE,
    ENVIRONMENTAL_WEIGHTS,
    LIBRARY_CONCERN_SLUGS,
    SKIN_V4_KEYS,
    assert_weights_complete,
    load_concern_penalty,
    load_skin_band_penalty,
    unmapped_concern_slugs,
)
from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.services.v4_scoring_engine import (
    HAZARD_ZERO_BANDS,
    OVERRIDE_CEILING,
    _band_aqi,
    _band_humidity,
    _band_temp,
    _band_uv,
    band_map,
    environmental_sfi,
    personal_sfi,
)

_DATA_DIR = Path(__file__).resolve().parents[1] / "app" / "hlhp" / "data"
SNAPSHOT = Path(os.environ.get("HLHP_SNAPSHOT", str(_DATA_DIR / "scenario_snapshot_v3_7.json")))
_LIB = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
_LIB_BANDS = {f: {b["key"]: b["points"] for b in v} for f, v in _LIB["bands"].items()}

_SWEEP = list(
    itertools.product(
        range(-5, 50, 3),
        [0, 2, 4, 6, 8, 11, 13],
        range(5, 100, 7),
        [20, 75, 150, 260, 380, 450],
    )
)
_ENVS = [
    EnvironmentalData(
        temperature_c=float(t),
        uv_index=float(u),
        humidity_pct=float(rh),
        aqi=int(a),
        location_name="conformance",
    )
    for t, u, rh, a in _SWEEP
]


def _emitted(fn, values):
    return {(fn(v)["key"], fn(v)["points"]) for v in values}


def test_band_keys_and_points_match_library():
    checks = [
        ("Temperature", _band_temp, [x / 2 for x in range(-20, 110)]),
        ("Humidity", _band_humidity, [x / 2 for x in range(0, 201)]),
        ("UV", _band_uv, [x / 2 for x in range(0, 32)]),
        ("AQI", _band_aqi, list(range(0, 520, 5))),
    ]
    for factor, fn, values in checks:
        for key, points in _emitted(fn, values):
            assert key in _LIB_BANDS[factor], f"{factor}:{key} not in library"
            assert _LIB_BANDS[factor][key] == points, f"{factor}:{key} points differ"


def test_every_library_band_is_reachable():
    checks = [
        ("Temperature", _band_temp, [x / 2 for x in range(-20, 110)]),
        ("Humidity", _band_humidity, [x / 2 for x in range(0, 201)]),
        ("UV", _band_uv, [x / 2 for x in range(0, 32)]),
        ("AQI", _band_aqi, list(range(0, 520, 5))),
    ]
    for factor, fn, values in checks:
        emitted = {k for k, _ in _emitted(fn, values)}
        missing = set(_LIB_BANDS[factor]) - emitted
        assert not missing, f"{factor} bands unreachable: {sorted(missing)}"


def test_every_library_concern_is_mapped():
    assert unmapped_concern_slugs() == set()
    for slug in LIBRARY_CONCERN_SLUGS:
        assert CONCERN_ARCHETYPE[slug] in ARCHETYPES


def test_every_band_has_a_penalty_row():
    table = load_skin_band_penalty()
    for factor, bands in _LIB_BANDS.items():
        for key in bands:
            assert key in table.get(factor, {}), f"no penalty row for {factor}:{key}"


def test_personal_never_exceeds_environmental():
    for env in _ENVS:
        b = band_map(env)
        e = environmental_sfi(b)
        for c in ARCHETYPES:
            for s in sorted(SKIN_V4_KEYS):
                assert personal_sfi(b, c, s) <= e


def test_hazard_override_caps_the_score():
    for env in _ENVS:
        b = band_map(env)
        tripped = any(
            x.points == 0 and (f, x.key) in HAZARD_ZERO_BANDS for f, x in b.items()
        )
        if tripped:
            assert environmental_sfi(b) <= OVERRIDE_CEILING


def test_scores_stay_in_range():
    for env in _ENVS:
        b = band_map(env)
        assert 0 <= environmental_sfi(b) <= 100
        for c in ARCHETYPES:
            for s in sorted(SKIN_V4_KEYS):
                assert 0 <= personal_sfi(b, c, s) <= 100


def test_concern_penalties_are_one_sided():
    TAILS = {
        "Humidity": ({"critical_low", "very_low", "low"}, {"high", "very_high", "extreme"}),
        "Temperature": ({"extreme_cold", "cold", "cool"}, {"warm", "hot", "extreme_heat"}),
    }
    table = load_concern_penalty()
    for arch, factors in table.items():
        for factor, (dry_tail, wet_tail) in TAILS.items():
            rows = factors.get(factor, {})
            lo = any(rows.get(b, 0) for b in dry_tail)
            hi = any(rows.get(b, 0) for b in wet_tail)
            if factor == "Temperature" and arch == "barrier_led":
                continue
            assert not (lo and hi), f"{arch} penalised on both tails of {factor}"


def test_no_negative_penalty_entries():
    for table in (load_skin_band_penalty(), load_concern_penalty()):
        for factor, bands in table.items():
            for band, row in bands.items():
                vals = row.values() if isinstance(row, dict) else []
                for v in vals:
                    inner = v.values() if isinstance(v, dict) else [v]
                    for x in inner:
                        assert int(x) >= 0, f"negative penalty at {factor}/{band}"


def test_every_archetype_has_a_penalty_row():
    table = load_concern_penalty()
    for arch in ARCHETYPES:
        assert arch in table, f"no concern penalty table for {arch}"


def test_penalty_table_is_zero_referenced_on_normal_skin():
    table = load_skin_band_penalty()
    offenders = [
        f"{factor}:{band}"
        for factor, bands in table.items()
        for band, row in bands.items()
        if row.get("normal", 0)
    ]
    assert not offenders, f"normal skin penalised at: {offenders}"


def test_skin_type_moves_the_score_on_favourable_days():
    good = [e for e in _ENVS if environmental_sfi(band_map(e)) >= 70]
    assert good, "no favourable days in the sweep"
    moved = 0
    for env in good:
        b = band_map(env)
        for c in ARCHETYPES:
            scores = {personal_sfi(b, c, s) for s in sorted(SKIN_V4_KEYS)}
            if len(scores) > 1:
                moved += 1
    assert moved > 0, "skin type never moved the score on a favourable day"


def test_environmental_weight_set_is_complete():
    assert_weights_complete(ENVIRONMENTAL_WEIGHTS)


def test_uv_leads_the_environmental_weight_set():
    uv = ENVIRONMENTAL_WEIGHTS["UV"]
    rest = [ENVIRONMENTAL_WEIGHTS[f] for f in ("Humidity", "Temperature", "AQI")]
    assert all(uv > r for r in rest)
    assert len(set(rest)) == 1, "the three non-UV factors are meant to be equal"


def test_feeling_log_is_not_a_scoring_input():
    import app.hlhp.services.v4_scoring_engine as engine

    assert not hasattr(engine, "feeling_log_sfi_adjustment")


def test_life_stage_does_not_enter_the_score():
    import inspect

    params = set(inspect.signature(personal_sfi).parameters)
    assert not {"gender_risk_delta", "age_risk_delta"} & params
    assert set(params) == {"bands", "archetype", "skin"}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
