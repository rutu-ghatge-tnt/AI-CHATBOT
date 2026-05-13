"""Parse SkinTruth GET /users/user-details auth responses."""

from __future__ import annotations

from app.label_looker.core.deps_auth import _parse_user_details_auth_response


def test_parse_user_details_array_shape_sets_id_from_external_id():
    body = {
        "statusCode": 200,
        "data": [
            {
                "firstName": "Rutu",
                "profileUrl": "rutu-ghatge-wphoe",
                "externalId": "a30fc9c3-95db-4b37-bf38-45c980258a65",
            }
        ],
        "success": True,
    }
    user = _parse_user_details_auth_response(body)
    assert user is not None
    assert user["firstName"] == "Rutu"
    assert user["id"] == "a30fc9c3-95db-4b37-bf38-45c980258a65"


def test_parse_legacy_nested_user():
    body = {
        "data": {"user": {"firstName": "A", "id": "507f1f77bcf86cd799439011"}, "role": "user"},
    }
    user = _parse_user_details_auth_response(body)
    assert user is not None
    assert user["firstName"] == "A"
    assert user["id"] == "507f1f77bcf86cd799439011"


def test_parse_sets_id_from_profile_url_when_no_external_id():
    body = {"data": [{"firstName": "A", "profileUrl": "my-profile-slug"}]}
    user = _parse_user_details_auth_response(body)
    assert user is not None
    assert user["id"] == "my-profile-slug"
