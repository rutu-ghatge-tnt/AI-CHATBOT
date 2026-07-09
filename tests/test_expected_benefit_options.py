from __future__ import annotations

import pytest

from app.label_looker.core.errors import ScannerApiError
from app.label_looker.services.expected_benefit_options import (
    build_expected_benefit_options,
    validate_desired_benefits,
)


def test_skincare_product_offers_only_stored_benefits():
    product = {
        "productType": "Serum",
        "productName": "Vitamin C Face Serum",
        "benefit": [{"label": "Brightening"}, {"label": "Hydration"}],
        "skinTypes": ["oily"],
    }
    payload = build_expected_benefit_options(product=product)
    assert payload["mode"] == "skincare"
    labels = [row["label"] for row in payload["expectedBenefitOptions"]]
    assert labels == ["Brightening", "Hydration"]
    assert all(row["source"] == "product" for row in payload["expectedBenefitOptions"])


def test_haircare_product_offers_only_stored_benefits():
    product = {
        "productType": "Shampoo",
        "productName": "Moisturizing Hair Shampoo",
        "hairTypes": ["wavy"],
        "benefit": [{"label": "Moisturizing"}, {"label": "Frizz Control"}],
    }
    payload = build_expected_benefit_options(product=product)
    assert payload["mode"] == "haircare"
    labels = [row["label"] for row in payload["expectedBenefitOptions"]]
    assert labels == ["Moisturizing", "Frizz Control"]


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


def test_validate_accepts_stored_product_benefit_labels():
    product = {
        "productType": "Shampoo",
        "productName": "EnagenBio Hair Cleanser",
        "benefit": [{"label": "Frizz Control"}, {"label": "Repair"}],
    }
    options = build_expected_benefit_options(product=product, mode="haircare")
    cleaned = validate_desired_benefits(
        desired=["Frizz Control", "Repair"],
        options_payload=options,
        product=product,
    )
    assert cleaned == ["Frizz Control", "Repair"]


def test_hair_options_only_include_product_benefits():
    product = {
        "productType": "Shampoo",
        "productName": "EnagenBio Hair Cleanser",
        "benefit": [{"label": "Hair Fall Control"}, {"label": "Frizz Control"}],
    }
    options = build_expected_benefit_options(
        product=product,
        mode="haircare",
        tag_names=["Frizz Control Shampoo"],
    )
    labels = [row["label"] for row in options["expectedBenefitOptions"]]
    assert labels == ["Hair Fall Control", "Frizz Control"]


def test_taxonomy_snapshot_resolves_benefit_object_ids():
    from bson import ObjectId

    from app.label_looker.services.expected_benefit_options import _taxonomy_benefit_labels_by_id
    from app.label_looker.services.profile_taxonomy_resolver import _resolve_list_values

    oids = [ObjectId("681b224610e9409e12c03acd"), ObjectId("681b224610e9409e12c03ace")]
    snap = _taxonomy_benefit_labels_by_id()
    resolved = {oid: snap[str(oid)] for oid in oids}
    labels = _resolve_list_values(oids, resolved)
    assert labels == ["Restorative", "Nourishing"]
