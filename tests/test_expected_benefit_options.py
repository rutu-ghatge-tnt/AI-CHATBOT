from __future__ import annotations

import pytest

from app.label_looker.core.errors import ScannerApiError
from app.label_looker.services.expected_benefit_options import (
    build_expected_benefit_options,
    validate_desired_benefits,
)


def test_skincare_product_offers_skincare_benefits_not_hair():
    product = {
        "productType": "Serum",
        "productName": "Vitamin C Face Serum",
        "benefit": [{"label": "Brightening"}, {"label": "Hydration"}],
        "skinTypes": ["oily"],
    }
    payload = build_expected_benefit_options(product=product)
    assert payload["mode"] == "skincare"
    labels = [row["label"] for row in payload["expectedBenefitOptions"]]
    assert labels
    assert not any("hair" in label.lower() for label in labels)


def test_haircare_product_offers_hair_benefits():
    product = {
        "productType": "Shampoo",
        "productName": "Moisturizing Hair Shampoo",
        "hairTypes": ["wavy"],
        "benefit": [{"label": "Moisturizing"}],
    }
    payload = build_expected_benefit_options(product=product)
    assert payload["mode"] == "haircare"
    labels = [row["label"] for row in payload["expectedBenefitOptions"]]
    assert any("moistur" in label.lower() for label in labels)


def test_validate_desired_benefits_rejects_out_of_catalog():
    product = {
        "productType": "Serum",
        "benefit": [{"label": "Brightening"}],
    }
    options = build_expected_benefit_options(product=product)
    with pytest.raises(ScannerApiError):
        validate_desired_benefits(desired=["random hair volume boost"], options_payload=options)


def test_validate_desired_benefits_accepts_catalog_label():
    product = {
        "productType": "Serum",
        "benefit": [{"label": "Brightening"}],
    }
    options = build_expected_benefit_options(product=product)
    first = options["expectedBenefitOptions"][0]
    cleaned = validate_desired_benefits(desired=[first["label"]], options_payload=options)
    assert cleaned == [first["label"]]


def test_validate_accepts_pdp_tag_names_for_hair_product():
    product = {
        "productType": "Shampoo",
        "productName": "EnagenBio Hair Cleanser",
        "description": "sulphate-free damage repair shampoo with keratin for frizzy hair",
        "benefit": [],
    }
    tag_names = [
        "Sulphate Free Shampoo",
        "Damage Repair Shampoo",
        "Frizz Control Shampoo",
    ]
    options = build_expected_benefit_options(product=product, mode="haircare", tag_names=tag_names)
    cleaned = validate_desired_benefits(
        desired=["Frizz Control Shampoo", "Damage Repair Shampoo"],
        options_payload=options,
        product=product,
        tag_names=tag_names,
    )
    assert cleaned == ["Frizz Control", "Repair"]


def test_hair_options_include_hair_fall_control():
    product = {
        "productType": "Shampoo",
        "productName": "EnagenBio Hair Cleanser",
        "benefit": [],
    }
    options = build_expected_benefit_options(
        product=product,
        mode="haircare",
        tag_names=["Frizz Control Shampoo"],
    )
    labels = [row["label"] for row in options["expectedBenefitOptions"]]
    assert "Hair Fall Control" in labels
