"""Canonical admin analytics service exports."""

from app.label_looker.modules.product_analysis.admin_service_impl import (
    analysis_by_id,
    analysis_list,
    analytics_summary,
    rating_counts,
    user_total_scan,
)

__all__ = ["analysis_list", "analysis_by_id", "analytics_summary", "user_total_scan", "rating_counts"]

