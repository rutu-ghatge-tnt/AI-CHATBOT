from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.label_looker.errors import ScannerApiError
from app.label_looker.responses import api_error_response
from app.label_looker.router import _scanner_routes, admin_router
from app.label_looker.settings import get_label_looker_settings


def _scanner_paths(path: str) -> bool:
    return path.startswith("/scanner") or path.startswith("/api/v1/scanner")


def install_label_looker(app: FastAPI) -> None:
    """Registers Label Looker routes, static uploads, and error envelopes for scanner paths."""
    try:
        get_label_looker_settings()
    except RuntimeError as e:
        print(f"Label Looker: skipped ({e})")
        return

    @app.exception_handler(ScannerApiError)
    async def _scanner_api_error_handler(_request: Request, exc: ScannerApiError):
        return api_error_response(exc)

    @app.exception_handler(RequestValidationError)
    async def _scanner_validation_handler(request: Request, exc: RequestValidationError):
        if not _scanner_paths(request.url.path):
            return JSONResponse(status_code=422, content={"detail": exc.errors()})
        err = ScannerApiError(422, "Validation error", errors=list(exc.errors()))
        return api_error_response(err)

    public_dir = Path(os.getcwd()) / "public" / "product-scan-images"
    public_dir.mkdir(parents=True, exist_ok=True)
    app.mount(
        "/product-scan-images",
        StaticFiles(directory=str(public_dir)),
        name="label_looker_product_scan_images",
    )

    from app.label_looker.deps_auth import authenticate_app_user, scanner_auth_sso

    app.include_router(
        _scanner_routes(scanner_auth_sso),
        prefix="/scanner",
        tags=["Label Looker — legacy /scanner"],
    )
    app.include_router(admin_router(), prefix="/scanner", tags=["Label Looker — panel /scanner"])
    app.include_router(
        _scanner_routes(authenticate_app_user),
        prefix="/api/v1/scanner",
        tags=["Label Looker — v1 /api/v1/scanner"],
    )
