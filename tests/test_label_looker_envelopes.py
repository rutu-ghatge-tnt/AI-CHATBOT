"""Parity checks for ApiResponse / errorHandler JSON shapes (migration-packet README §2)."""

from __future__ import annotations

from app.label_looker.core.errors import ScannerApiError


def test_error_envelope_uses_message_when_no_errors():
    err = ScannerApiError(404, "Not found")
    b = err.to_body()
    assert b["status"] == "error"
    assert b["success"] is False
    assert b["statusCode"] == 404
    assert b["message"] == "Not found"
    assert "errors" not in b
    assert "stack" in b


def test_error_envelope_uses_errors_array():
    err = ScannerApiError(422, "ignored", errors=[{"loc": ["body"], "msg": "x", "type": "value_error"}])
    b = err.to_body()
    assert b["errors"] == [{"loc": ["body"], "msg": "x", "type": "value_error"}]
    assert "message" not in b


def test_api_success_jsonable_objectid():
    from bson import ObjectId

    from app.label_looker.core.responses import api_success

    r = api_success({"_id": ObjectId("507f1f77bcf86cd799439011")})
    body = r.body.decode()
    assert '"_id":"507f1f77bcf86cd799439011"' in body
    assert '"success":true' in body
    assert '"statusCode":200' in body
