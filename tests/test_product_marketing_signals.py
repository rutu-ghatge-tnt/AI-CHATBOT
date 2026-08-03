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


def test_resolved_catalog_benefits_match_even_when_product_stores_object_ids():
    """PDP lists Nourishing + Sun Protection; catalog stores ObjectId refs only.

    Scoring must use resolved benefit_labels so a selected product benefit is
    never reported as Weak / needs-not-covered.
    """
    from bson import ObjectId

    product = {
        "productType": "Skincare",
        "productName": "Eclipse Solaire Active Sunscreen SPF 50 PA+++",
        "description": "Mineral sunscreen with zinc oxide and titanium dioxide.",
        "skinTypes": ["dry", "normal", "oily", "combination", "sensitive"],
        # Catalog shape: ObjectIds only — no embedded label strings.
        "benefit": [ObjectId("681b224610e9409e12c03ace"), ObjectId("681b224610e9409e12c03acf")],
        "claims": ["Non-comedogenic", "Paraben and mineral oil free"],
    }
    resolved_labels = ["Nourishing", "Sun Protection"]

    # Without resolved labels, ObjectId refs are invisible (historical bug).
    signals_without = build_product_benefit_signals(
        product=product,
        tile_product={},
        tag_names=[],
        mode="skincare",
    )
    result_without = profile_match_engines.evaluate_suitability(
        skin_type="combination",
        concerns=["Uneven Skin Tone", "Dark Circles", "Dryness"],
        benefits=resolved_labels,
        declared_types=product["skinTypes"],
        product_primary="",
        product_benefits=signals_without,
        mode="skincare",
    )
    assert "nourishing" in result_without["unmatched_desired_benefits"]

    signals = build_product_benefit_signals(
        product=product,
        tile_product={},
        tag_names=[],
        mode="skincare",
        benefit_labels=resolved_labels,
    )
    result = profile_match_engines.evaluate_suitability(
        skin_type="combination",
        concerns=["Uneven Skin Tone", "Dark Circles", "Dryness"],
        benefits=resolved_labels,
        declared_types=product["skinTypes"],
        product_primary="",
        product_benefits=signals,
        mode="skincare",
    )
    assert set(result["matched_desired_benefits"]) == {"nourishing", "sun protection"}
    assert result["unmatched_desired_benefits"] == []
    nourishing_axis = next(a for a in result["fit_axes"] if a["id"] == "goal_nourishing")
    assert nourishing_axis["status"] == "strong"
