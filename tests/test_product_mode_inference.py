from __future__ import annotations

from app.label_looker.modules.product_analysis.analysis_service_impl import (
    _infer_mode_from_product,
    _resolve_analysis_mode,
)
from app.label_looker.services.profile_form import assess_profile_completeness


def test_hair_cleanser_slug_infers_haircare_not_skincare():
    product = {
        "productName": "Enagenbio Hair Cleanser",
        "slug": "enagenbio-hair-cleanser",
        "productType": "Cleanser",
    }
    assert _infer_mode_from_product(product) == "haircare"
    assert _resolve_analysis_mode(body={}, product=product, specific_type=None, main_benefit=None) == "haircare"


def test_face_cleanser_stays_skincare():
    product = {
        "productName": "Gentle Face Cleanser",
        "slug": "gentle-face-cleanser",
        "productType": "Cleanser",
    }
    assert _infer_mode_from_product(product) == "skincare"


def test_haircare_required_fields_for_hair_cleanser():
    product = {
        "productName": "Enagenbio Hair Cleanser",
        "slug": "enagenbio-hair-cleanser",
        "productType": "Cleanser",
    }
    mode = _resolve_analysis_mode(body={}, product=product, specific_type=None, main_benefit=None)
    completeness = assess_profile_completeness(details={}, auth_user=None, mode=mode)
    assert completeness["requiredFieldsForScan"] == ["age", "gender", "hairType", "hairConcerns"]
    assert "hairType" in completeness["fieldStatus"]
    assert completeness["fieldStatus"]["hairType"]["requiredForScan"] is True
    assert completeness["fieldStatus"]["skinType"]["requiredForScan"] is False
