from __future__ import annotations

from app.label_looker.engines import profile_match as profile_match_engines
from app.label_looker.services.expected_benefit_options import build_expected_benefit_options
from app.label_looker.services.product_marketing_signals import (
    build_product_benefit_signals,
    match_benefit_labels_from_marketing,
)


def test_enagenbio_tags_map_to_frizz_and_repair_benefits():
    product = {
        "productType": "Shampoo",
        "productName": "EnagenBio Hair Cleanser",
        "description": (
            "<p>EnagenBio Hair Cleanser is a sulphate-free damage repair shampoo "
            "formulated with hydrolyzed keratin, pro-vitamin B5, and wheat germ oil "
            "to gently cleanse, strengthen, and nourish dry, damaged, and frizzy hair.</p>"
        ),
        "benefit": [{"label": "Frizz Control"}, {"label": "Repair"}],
        "tags": [],
    }
    tag_names = [
        "Sulphate Free Shampoo",
        "Damage Repair Shampoo",
        "Hair Cleanser",
        "Keratin Shampoo",
        "Frizz Control Shampoo",
    ]
    labels = match_benefit_labels_from_marketing(product=product, tag_names=tag_names, mode="haircare")
    assert "Frizz Control" in labels
    assert "Repair" in labels

    options = build_expected_benefit_options(product=product, mode="haircare", tag_names=tag_names)
    option_labels = [row["label"] for row in options["expectedBenefitOptions"]]
    assert option_labels == ["Frizz Control", "Repair"]
    assert all(row["source"] == "product" for row in options["expectedBenefitOptions"])


def test_tag_backed_product_scores_partial_for_frizz_goal():
    product = {
        "productType": "Shampoo",
        "productName": "EnagenBio Hair Cleanser",
        "description": "sulphate-free damage repair shampoo with keratin for frizzy hair",
        "hairTypes": ["dry"],
        "benefit": [],
    }
    tag_names = ["Frizz Control Shampoo", "Damage Repair Shampoo"]
    signals = build_product_benefit_signals(product=product, tile_product={}, tag_names=tag_names, mode="haircare")
    result = profile_match_engines.evaluate_suitability(
        skin_type="dry",
        concerns=["frizz"],
        benefits=["Frizz Control", "Anti-Dandruff"],
        declared_types=["dry"],
        product_primary="",
        product_benefits=signals,
        mode="haircare",
    )
    assert result["matched_desired_benefits"] == ["frizz control"]
    assert "anti-dandruff" in result["unmatched_desired_benefits"]
    assert result["final_score"] >= 30
