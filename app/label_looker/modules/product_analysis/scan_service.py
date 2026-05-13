"""Canonical scan service exports."""

from app.label_looker.modules.product_analysis.scan_service_impl import number_of_scan_left, scan_image_to_text

__all__ = ["scan_image_to_text", "number_of_scan_left"]

