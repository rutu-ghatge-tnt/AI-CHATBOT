from __future__ import annotations

from app.label_looker.services.label_looker_quota import (
    _read_quota_used,
    _today_key,
)


def test_read_quota_used_resets_on_new_day():
    assert _read_quota_used({"labelLookerQuota": {"date": "1999-01-01", "used": 4}}) == 0
    assert _read_quota_used({"labelLookerQuota": {"date": _today_key(), "used": 3}}) == 3


def test_scan_ids_from_doc_unified_row():
    from app.label_looker.services.label_looker_scan_store import scan_ids_from_doc

    oid = "674a1b2c3d4e5f6789012345"
    user_scan_id, analysis_scan_id = scan_ids_from_doc({"_id": oid})
    assert user_scan_id == oid
    assert analysis_scan_id == oid


def test_scan_ids_from_doc_legacy_linked_analysis():
    from app.label_looker.services.label_looker_scan_store import scan_ids_from_doc

    user_scan_id, analysis_scan_id = scan_ids_from_doc(
        {"_id": "aaa", "analysisScanId": "bbb"},
    )
    assert user_scan_id == "aaa"
    assert analysis_scan_id == "bbb"
