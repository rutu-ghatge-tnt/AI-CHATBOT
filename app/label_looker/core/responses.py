from __future__ import annotations

from datetime import datetime
from typing import Any

from bson import ObjectId
from fastapi import status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.label_looker.core.errors import ScannerApiError


def api_success(
    data: Any,
    *,
    status_code: int = status.HTTP_200_OK,
    message: str = "Success",
) -> JSONResponse:
    body = {
        "data": data,
        "statusCode": status_code,
        "message": message,
        "success": True,
    }
    encoded = jsonable_encoder(body, custom_encoder={ObjectId: str, datetime: lambda d: d.isoformat()})
    return JSONResponse(status_code=status_code, content=encoded)


def api_error_response(exc: ScannerApiError) -> JSONResponse:
    body = exc.to_body()
    return JSONResponse(status_code=exc.status_code, content=body)

