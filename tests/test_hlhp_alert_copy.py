"""Template-based alert copy composition."""

from app.hlhp.composition.alert_copy import (
    compose_alert_title,
    compose_how_routine,
    compose_outlook_subline,
    compose_strip_headline,
    pick_alert_body,
    resolve_concern_id,
)
from app.hlhp.evidence.loader import get_evidence_store
from app.hlhp.models.profile import AgeBracket, Gender, SkinConcern, SkinType, UserProfile


def _acne_profile() -> UserProfile:
    return UserProfile(
        user_id="u1",
        skin_type=SkinType.OILY,
        skin_concerns=[SkinConcern.ACNE],
        gender=Gender.FEMALE,
        age_bracket=AgeBracket.AGE_25_30,
    )


def test_compose_how_routine_acne_morning_chain():
    store = get_evidence_store()
    framework = (store.composition or {}).get("concern_routine_framework") or []
    finding = next(f for f in store.findings if f.mood_verdict_tag == "sebum_rush_day" and f.id.startswith("TEM"))
    how = compose_how_routine(
        framework,
        finding,
        profile=_acne_profile(),
        day_phase="morning",
    )
    assert how
    assert how.count("→") >= 3
    assert "cleanser" in how.lower()
    assert "sunscreen" in how.lower()
    assert "never harsh" not in how.lower()


def test_compose_how_routine_dehydration_maps_to_dryness_framework():
    store = get_evidence_store()
    framework = (store.composition or {}).get("concern_routine_framework") or []
    finding = next(f for f in store.findings if f.routine_action == "layer_barrier")
    profile = UserProfile(
        user_id="u2",
        skin_type=SkinType.DRY,
        skin_concerns=[SkinConcern.DEHYDRATION],
        gender=Gender.FEMALE,
        age_bracket=AgeBracket.AGE_25_30,
    )
    how = compose_how_routine(framework, finding, profile=profile, day_phase="morning")
    assert how
    assert how.count("→") >= 2
    assert how != "Barrier-repair moisturizer"


def test_compose_how_routine_oily_dehydration_falls_back_to_dryness_framework():
    store = get_evidence_store()
    framework = (store.composition or {}).get("concern_routine_framework") or []
    finding = next(f for f in store.findings if f.routine_action == "layer_barrier")
    profile = UserProfile(
        user_id="u5",
        skin_type=SkinType.OILY,
        skin_concerns=[SkinConcern.DEHYDRATION],
        gender=Gender.FEMALE,
        age_bracket=AgeBracket.AGE_25_30,
    )
    how = compose_how_routine(framework, finding, profile=profile, day_phase="morning")
    assert how
    assert how.count("→") >= 2
    assert how != "Barrier-repair moisturizer"


def test_compose_how_routine_dullness_profile_barrier_finding_uses_dryness_chain():
    store = get_evidence_store()
    framework = (store.composition or {}).get("concern_routine_framework") or []
    finding = next(f for f in store.findings if f.routine_action == "layer_barrier")
    profile = UserProfile(
        user_id="u6",
        skin_type=SkinType.OILY,
        skin_concerns=[SkinConcern.DULLNESS],
        gender=Gender.FEMALE,
        age_bracket=AgeBracket.AGE_25_30,
    )
    how = compose_how_routine(framework, finding, profile=profile, day_phase="morning")
    assert how
    assert how.count("→") >= 2
    assert how != "Barrier-repair moisturizer"


def test_compose_how_routine_blot_suffix_after_chain():
    store = get_evidence_store()
    framework = (store.composition or {}).get("concern_routine_framework") or []
    finding = next(f for f in store.findings if f.id == "TEM-16")
    how = compose_how_routine(framework, finding, profile=_acne_profile(), day_phase="morning")
    assert how
    assert "→" in how


def test_compose_alert_title_uses_mood_and_sensation():
    store = get_evidence_store()
    finding = next(
        f
        for f in store.findings
        if f.mood_verdict_tag == "sebum_rush_day" and f.body_sensation_decode
    )
    title = compose_alert_title(finding)
    assert "sebum" in title.lower() or "Sebum" in title
    assert "—" in title or len(title) > 8


def test_pick_alert_body_from_l1():
    store = get_evidence_store()
    finding = next(f for f in store.findings if f.alert_l1_personalised)
    body = pick_alert_body(finding, guest_mode=False, day_phase="morning")
    assert len(body.split()) >= 4


def test_compose_outlook_subline_merges_forecast_and_how_tail():
    line = compose_outlook_subline(
        forecast_oneliner="Rulu, sebum will run hot today",
        how_text="Gel cleanser → Niacinamide → Moisturizer → Sunscreen. Blot mid-day as needed.",
        guest_mode=False,
    )
    assert line
    assert "sebum" in line.lower()
    assert "blot" in line.lower()


def test_compose_strip_headline_personalised_prefers_forecast_over_mood():
    store = get_evidence_store()
    finding = next(f for f in store.findings if "Skin colour varies hugely" in (f.alert_l1_personalised or ""))
    personalised = compose_strip_headline(
        finding,
        mood_headline_text="Today is a sebum-rush day.",
        forecast_oneliner="Rulu, heat plus muggy air pushes your jawline harder.",
        outdoor_band=None,
        guest_mode=False,
        day_phase="morning",
        personalised=True,
    )
    assert "Rulu" in personalised or "heat" in personalised.lower()
    assert len(personalised) <= 120

    enriched = "Rulu, comfortable warm day. Sunscreen plus gentle routine really helps. Barrier-repair moisturizer"
    strip_from_enriched = compose_strip_headline(
        finding,
        mood_headline_text="Today is a sebum-rush day.",
        forecast_oneliner=enriched,
        outdoor_band=None,
        guest_mode=False,
        day_phase="morning",
        personalised=True,
    )
    assert "Barrier" not in strip_from_enriched
    assert "Sunscreen" in strip_from_enriched
    assert strip_from_enriched.count(".") >= 2

    two_line_forecast = "Rulu, comfortable warm day. Sunscreen plus gentle routine really helps."
    strip_two = compose_strip_headline(
        finding,
        mood_headline_text="Today is a sebum-rush day.",
        forecast_oneliner=two_line_forecast,
        outdoor_band=None,
        guest_mode=False,
        day_phase="morning",
        personalised=True,
    )
    assert "Sunscreen" in strip_two
    assert "comfortable warm day" in strip_two.lower()

    guest = compose_strip_headline(
        finding,
        mood_headline_text="Today is a manageable day.",
        forecast_oneliner=None,
        outdoor_band=None,
        guest_mode=True,
        day_phase="morning",
        personalised=False,
    )
    assert guest == "Today is a manageable day."


def test_resolve_concern_from_profile():
    store = get_evidence_store()
    finding = store.findings[0]
    assert resolve_concern_id(finding, _acne_profile()) == "acne"
    dehydration = UserProfile(
        user_id="u3",
        skin_type=SkinType.DRY,
        skin_concerns=[SkinConcern.DEHYDRATION],
        gender=Gender.FEMALE,
        age_bracket=AgeBracket.AGE_25_30,
    )
    assert resolve_concern_id(finding, dehydration) == "dryness"
    dullness = UserProfile(
        user_id="u4",
        skin_type=SkinType.COMBINATION,
        skin_concerns=[SkinConcern.DULLNESS],
        gender=Gender.FEMALE,
        age_bracket=AgeBracket.AGE_25_30,
    )
    assert resolve_concern_id(finding, dullness) == "dullness"
