from app.hlhp.composition.alert_copy import label_routine_action
from app.hlhp.composition.symptom import assemble_symptom_explainer


def test_label_routine_action_maps_workbook_slugs():
    assert label_routine_action("cleanse_gentle") == "Gentle gel cleanser"
    assert label_routine_action("blot") == "Blotting tissue through the day"
    assert label_routine_action("") is None


def test_symptom_explainer_returns_routine_action_label():
    page = assemble_symptom_explainer("oily")
    assert page is not None
    with_action = [s for s in page["sections"] if s.get("routine_action")]
    assert with_action
    for section in with_action:
        assert section.get("routine_action_label")
        assert "_" not in (section["routine_action_label"] or "")
