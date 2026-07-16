"""Unit tests for What's Different Today (routine_today_service)."""

from __future__ import annotations

from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.models.profile import AgeBracket, Gender, SkinConcern, SkinType, UserProfile
from app.hlhp.services.routine_today_service import (
    _pass_filter,
    load_routine_rules,
    select_routine_today,
)
from app.hlhp.services.v4_scoring_engine import evaluate_v4


def _env(**kwargs) -> EnvironmentalData:
    defaults = dict(
        uv_index=6.0,
        temperature_c=28.0,
        aqi=80,
        humidity_pct=52.0,
        wind_kmh=10.0,
        location_name="Pune",
    )
    defaults.update(kwargs)
    return EnvironmentalData(**defaults)


def _profile(*, skin: SkinType, concern: SkinConcern = SkinConcern.ACNE) -> UserProfile:
    return UserProfile(
        user_id="test-user",
        skin_type=skin,
        skin_concerns=[concern],
        gender=Gender.FEMALE,
        age_bracket=AgeBracket.AGE_25_30,
    )


def test_routine_rules_load():
    rules = load_routine_rules()
    assert len(rules) >= 20
    assert all(
        r.get("type")
        in {"REINFORCE", "PROTECT", "SKIP", "ADD", "SWAP", "MANAGE", "KEEP"}
        for r in rules
    )


def test_guest_high_uv_returns_uv_rules():
    eval_ = evaluate_v4(_env(uv_index=9.0), None, guest_mode=True)
    items = select_routine_today(eval_, None, guest_mode=True)
    assert 1 <= len(items) <= 3
    assert any(i.factor == "UV" for i in items)
    assert items[0].priority <= items[-1].priority


def test_max_three_and_dedupe_headlines():
    eval_ = evaluate_v4(
        _env(uv_index=11.0, temperature_c=40.0, humidity_pct=85.0, aqi=350),
        None,
        guest_mode=True,
    )
    items = select_routine_today(eval_, None, guest_mode=True, limit=3)
    assert len(items) <= 3
    headlines = [i.headline for i in items]
    assert len(headlines) == len(set(headlines))


def test_skin_except_filter_unit():
    assert _pass_filter("except:Dry", "Oily") is True
    assert _pass_filter("except:Dry", "Dry") is False
    assert _pass_filter("any", "Dry") is True
    assert _pass_filter("Melasma|Uneven Skin Tone / Tan", "Melasma") is True


def test_band_must_match_factor():
    eval_low = evaluate_v4(
        _env(uv_index=1.0, temperature_c=22.0, humidity_pct=50.0, aqi=40),
        None,
        guest_mode=True,
    )
    items = select_routine_today(eval_low, None, guest_mode=True)
    assert "UV-01" not in {i.id for i in items}


def test_dry_profile_vs_oily_except_rules():
    # Very dry air — humidity rules with except:Dry should skip Dry skin
    eval_ = evaluate_v4(
        _env(uv_index=3.0, temperature_c=22.0, humidity_pct=15.0, aqi=50),
        None,
        guest_mode=False,
    )
    dry = select_routine_today(eval_, _profile(skin=SkinType.DRY), guest_mode=False)
    oily = select_routine_today(eval_, _profile(skin=SkinType.OILY), guest_mode=False)
    assert len(dry) <= 3 and len(oily) <= 3
    # Oily may pick humidity SKIP/ADD that dry cannot
    except_dry_ids = {
        r["id"]
        for r in load_routine_rules()
        if str(r.get("skin") or "").lower().startswith("except:dry")
    }
    assert not ({i.id for i in dry} & except_dry_ids)
