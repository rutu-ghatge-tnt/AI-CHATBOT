"""User display name extraction tests."""

from app.hlhp.services.user_display import extract_first_name_from_doc


def test_extract_first_name_flat():
    assert extract_first_name_from_doc({"firstName": "Priya Sharma"}) == "Priya"


def test_extract_first_name_nested_account():
    assert extract_first_name_from_doc({"account": {"firstName": "Rutu"}}) == "Rutu"


def test_extract_first_name_from_name_field():
    assert extract_first_name_from_doc({"name": "Ananya Devi"}) == "Ananya"


def test_extract_first_name_front_name():
    assert extract_first_name_from_doc({"frontName": "Meera"}) == "Meera"
