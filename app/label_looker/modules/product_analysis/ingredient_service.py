"""Canonical ingredient service exports."""

from app.label_looker.modules.product_analysis.ingredient_service_impl import (
    get_ingredient_detail_for_scanner,
    get_ingredient_detail_response,
    normalize_scanner_ingredient_name,
)

__all__ = [
    "normalize_scanner_ingredient_name",
    "get_ingredient_detail_for_scanner",
    "get_ingredient_detail_response",
]

