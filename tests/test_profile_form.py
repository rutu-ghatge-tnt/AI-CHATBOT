from app.label_looker.services.profile_form import (
    assess_profile_completeness,
    build_profile_form_values,
    profile_updates_from_form_body,
)


def test_build_profile_form_prefills_from_mongo_and_auth():
    details = {
        "skinType": "combination",
        "skinConcerns": ["dark-circles", "sleep-deprivation"],
        "skinGoals": ["glow", "eventone"],
        "hairType": "straight",
        "hairConcerns": ["hair-fall"],
        "hairGoals": ["hairfall-relief"],
        "scalpConcern": "dandruff",
        "environmentAssessment": "mixed",
        "screenTime": "between-8-to-12-hrs",
        "breakPattern": "few-breaks-during-the-day",
        "skinTone": "#F1BF9A",
        "city": "Pune",
        "state": "Maharashtra",
        "country": "India",
    }
    auth = {
        "firstName": "Rutu",
        "lastName": "Ghatge",
        "userName": "rutu-ghatge-3cw6w",
        "email": "rutu.ghatge@techsntomes.com",
        "mobile": "9822750477",
        "age": 22,
        "gender": "female",
        "bornOn": "10-03-2004",
        "weight": 70,
        "height": 169,
    }
    form = build_profile_form_values(details=details, auth_user=auth)
    assert form["account"]["firstName"] == "Rutu"
    assert form["account"]["city"] == "Pune"
    assert form["skin"]["skinType"] == "combination"
    assert "dark-circles" in form["skin"]["skinConcerns"]
    assert form["hair"]["hairType"] == "straight"
    assert form["analysis"]["scalpConcern"] == "dandruff"


def test_assess_highlights_missing_scan_fields_skincare():
    details = {"age": 22, "gender": "female", "skinType": "combination"}
    result = assess_profile_completeness(details=details, auth_user=None, mode="skincare")
    assert result["hasRequiredForScan"] is False
    assert "skinConcerns" in result["missingFields"]
    assert "skinConcerns" in result["highlightFields"]
    assert result["fieldStatus"]["skinConcerns"]["missing"] is True
    assert result["fieldStatus"]["skinGoals"]["missing"] is False


def test_assess_complete_skincare_profile():
    details = {
        "age": 22,
        "gender": "female",
        "skinType": "combination",
        "skinConcerns": ["dark-circles"],
    }
    result = assess_profile_completeness(details=details, auth_user=None, mode="skincare")
    assert result["hasRequiredForScan"] is True
    assert result["missingFields"] == []


def test_build_profile_form_mongo_array_scalars():
    details = {
        "skinType": "combination",
        "hairType": ["straight"],
        "skinTone": ["#F1BF9A"],
        "sleepDurations": "7",
        "stressLevel": "low",
    }
    form = build_profile_form_values(details=details, auth_user=None)
    assert form["hair"]["hairType"] == "straight"
    assert form["skin"]["skinTone"] == "#F1BF9A"
    assert form["analysis"]["screenTime"] == "7"
    assert form["analysis"]["stressLevel"] == "low"


def test_normalize_mongo_profile_and_users_merge():
    from app.label_looker.services.user_profile_flow import merge_auth_user_details, normalize_mongo_profile_shape

    details = normalize_mongo_profile_shape(
        {"hairType": ["wavy"], "skinConcerns": ["dark-circles"], "sleepDurations": "between-8-to-12-hrs", "bornOn": "10-03-2004"}
    )
    assert details["hairType"] == "wavy"
    assert isinstance(details.get("age"), int)
    merged = merge_auth_user_details(
        details,
        {
            "firstName": "Pooja",
            "lastName": "Mistry",
            "email": "pooja.mistry20@gmail.com",
            "phoneNumber": "9920999209",
            "profileUrl": "pooja-mistry-bln5q",
        },
    )
    assert merged["firstName"] == "Pooja"
    assert merged["mobile"] == "9920999209"
    assert merged["username"] == "pooja-mistry-bln5q"
    assert merged["screenTime"] == "between-8-to-12-hrs"


def test_profile_updates_from_nested_form():
    body = {
        "skin": {"skinConcerns": ["acne", "redness"], "skinType": "oily"},
        "hair": {"hairConcerns": ["hair-fall"]},
        "identity": {"age": 25, "gender": "female"},
    }
    updates = profile_updates_from_form_body(body)
    assert updates["skinType"] == "oily"
    assert updates["skinConcerns"] == ["acne", "redness"]
    assert updates["hairConcerns"] == ["hair-fall"]
    assert updates["age"] == 25
