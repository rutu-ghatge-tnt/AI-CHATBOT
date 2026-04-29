from __future__ import annotations

import traceback
from typing import Any, Optional

from app.label_looker.settings import get_label_looker_settings


class ScannerApiError(Exception):
    """Maps to Node ApiError + errorHandler JSON envelope."""

    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        errors: Optional[list[Any]] = None,
        stack: Optional[str] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.errors = errors
        self._stack_override = stack

    def to_body(self) -> dict[str, Any]:
        s = get_label_looker_settings()
        body: dict[str, Any] = {
            "status": "error",
            "success": False,
            "statusCode": self.status_code,
            "stack": self._stack_override
            if self._stack_override is not None
            else (traceback.format_exc() if s.include_error_stack else ""),
        }
        if self.errors is not None:
            body["errors"] = self.errors
        else:
            body["message"] = self.message
        return body
