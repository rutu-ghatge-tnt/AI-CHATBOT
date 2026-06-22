from __future__ import annotations

from bson import ObjectId

from app.label_looker.services.common_flow import end_user_owns_scan_document


def test_scan_owner_matches_legacy_objectid_when_profile_url_aligns():
    oid = ObjectId("507f1f77bcf86cd799439011")
    doc = {"userId": oid, "userProfileUrl": "rutu-ghatge-wphoe"}
    user = {"id": "a30fc9c3-95db-4b37-bf38-45c980258a65", "profileUrl": "rutu-ghatge-wphoe"}
    assert end_user_owns_scan_document(doc, user, "a30fc9c3-95db-4b37-bf38-45c980258a65") is True


def test_scan_owner_same_user_id():
    doc = {"userId": "same", "userProfileUrl": "x"}
    user = {"id": "other", "profileUrl": "y"}
    assert end_user_owns_scan_document(doc, user, "same") is True


def test_scan_owner_rejects_other():
    doc = {"userId": "a", "userProfileUrl": "p1"}
    user = {"id": "b", "profileUrl": "p2"}
    assert end_user_owns_scan_document(doc, user, "b") is False
