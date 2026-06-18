from __future__ import annotations

from app.label_looker.services.product_analysis_store import (
    is_successful_product_analysis,
    product_analysis_lookup_filter,
)


def test_is_successful_product_analysis_requires_analytic_detail():
    assert not is_successful_product_analysis(None)
    assert not is_successful_product_analysis({"ingredientAnalysisError": "x"})
    assert not is_successful_product_analysis({"analyticDetail": {}})
    assert is_successful_product_analysis({"analyticDetail": {"opinion": "ok"}})


def test_product_analysis_lookup_filter_object_id():
    filt = product_analysis_lookup_filter("507f1f77bcf86cd799439011")
    assert "$or" in filt
