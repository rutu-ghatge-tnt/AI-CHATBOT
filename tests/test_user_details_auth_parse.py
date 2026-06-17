"""Parse SkinTruth GET /users/user-details auth responses."""

from __future__ import annotations

import pytest

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


def test_user_from_token_payload_flat_access_jwt():
    from app.label_looker.core.deps_auth import _user_from_token_payload

    user = _user_from_token_payload(
        {
            "_id": "6a2ba5898d454a49e9cd00e5",
            "externalId": "cbaf805d-4014-47cd-9dba-dc3f0928651b",
            "email": "rutu.ghatge@techsntomes.com",
            "firstName": "Rutu",
            "profileUrl": "rutu-ghatge-3cw6w",
        },
        "tok",
    )
    assert user["id"] == "cbaf805d-4014-47cd-9dba-dc3f0928651b"
    assert user["firstName"] == "Rutu"
    assert user["_label_looker_access_token"] == "tok"


@pytest.mark.anyio
async def test_authenticate_local_jwt_roundtrip():
    import os

    import jwt as pyjwt
    from dotenv import load_dotenv

    load_dotenv()
    from app.label_looker.core.deps_auth import authenticate_local_jwt

    secret = os.getenv("ACCESS_TOKEN_SECRET") or "SKINBBMAINSUPERSECRET"
    token = pyjwt.encode(
        {
            "_id": "6a2ba5898d454a49e9cd00e5",
            "externalId": "cbaf805d-4014-47cd-9dba-dc3f0928651b",
            "firstName": "Rutu",
            "profileUrl": "rutu-ghatge-3cw6w",
        },
        secret,
        algorithm="HS256",
    )
    user = await authenticate_local_jwt(authorization=f"Bearer {token}")
    assert user["firstName"] == "Rutu"
    assert user["id"] == "cbaf805d-4014-47cd-9dba-dc3f0928651b"
