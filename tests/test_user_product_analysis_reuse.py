from __future__ import annotations

from bson import ObjectId

from app.label_looker.modules.product_analysis.analysis_service_impl import _user_product_scan_filter


def test_user_product_scan_filter_matches_profile_url_when_user_id_differs():
    oid = ObjectId("507f1f77bcf86cd799439011")
    product_ref = ObjectId("507f1f77bcf86cd799439012")
    user = {"id": "a30fc9c3-95db-4b37-bf38-45c980258a65", "profileUrl": "rutu-ghatge-wphoe"}
    filt = _user_product_scan_filter(
        user=user,
        user_id="a30fc9c3-95db-4b37-bf38-45c980258a65",
        product_ref=product_ref,
        extra={"analyticDetail": {"$exists": True}},
    )
    assert "$and" in filt
    owner, product = filt["$and"]
    assert product == {"productId": product_ref, "analyticDetail": {"$exists": True}}
    assert {"userProfileUrl": "rutu-ghatge-wphoe"} in owner["$or"]
    assert {"userId": oid} in owner["$or"] or {"userId": "a30fc9c3-95db-4b37-bf38-45c980258a65"} in owner["$or"]
