from __future__ import annotations

import pytest
from bson import ObjectId

from app.label_looker.core.errors import ScannerApiError
from app.label_looker.services.common_flow import (
    require_end_user_owns_scan,
    user_owned_scans_filter,
)


def test_user_owned_scans_filter_includes_profile_url():
    user = {"id": "uuid-1", "profileUrl": "rutu-ghatge-3cw6w"}
    filt = user_owned_scans_filter(user=user, user_id="uuid-1")
    assert {"$or": filt["$or"]} if isinstance(filt, dict) and "$or" in filt else filt
    clauses = filt["$or"] if "$or" in filt else [filt]
    assert {"userProfileUrl": "rutu-ghatge-3cw6w"} in clauses


def test_require_end_user_owns_scan_allows_owner():
    doc = {"userId": "u1", "userProfileUrl": "slug"}
    user = {"id": "u1", "profileUrl": "slug"}
    require_end_user_owns_scan(doc=doc, user=user, user_id="u1")


def test_require_end_user_owns_scan_blocks_other_user():
    doc = {"userId": "a", "userProfileUrl": "p1"}
    user = {"id": "b", "profileUrl": "p2"}
    with pytest.raises(ScannerApiError) as exc:
        require_end_user_owns_scan(doc=doc, user=user, user_id="b")
    assert exc.value.status_code == 403


def test_require_end_user_owns_scan_allows_unowned_legacy_scan():
    doc = {"extractedIngredients": ["aqua"]}
    require_end_user_owns_scan(doc=doc, user=None, user_id=None)


def test_external_id_matches_objectid_userid():
    oid = ObjectId("507f1f77bcf86cd799439011")
    doc = {"userId": oid, "userProfileUrl": "slug"}
    user = {"externalId": str(oid), "profileUrl": "slug"}
    require_end_user_owns_scan(doc=doc, user=user, user_id="other-uuid")
