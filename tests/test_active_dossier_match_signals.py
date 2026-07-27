"""Active dossiers must feed Match My Profile benefit signals."""

from __future__ import annotations

from app.label_looker.engines import profile_match as profile_match_engines
from app.label_looker.engines.profile_match_impl import _canonicalize_term
from app.label_looker.services.active_ingredient_dossiers import benefit_signals_from_active_dossiers
from app.label_looker.services.product_marketing_signals import build_product_benefit_signals


def test_brightens_goal_canonicalizes_to_brightening():
    assert _canonicalize_term("Brightens and evens skin tone") == "brightening"
    assert _canonicalize_term("uneven-skintone") == "brightening"


def test_glyteine_style_dossiers_unlock_brightening_goal():
    dossiers = [
        {
            "name": "Glyteine",
            "functionality": ["Antioxidant", "Skin Conditioning Agent"],
            "chemicalClasses": ["Peptides"],
            "description": (
                "Gamma-glutamylcysteine precursor supporting glutathione for brighter, "
                "more even-toned radiant skin."
            ),
        },
        {
            "name": "Tetrahydrocurcumin",
            "functionality": ["Antioxidant", "Skin Conditioning Agent"],
            "chemicalClasses": [],
            "description": "Helps brighten and even out skin tone.",
        },
    ]
    signals = benefit_signals_from_active_dossiers(dossiers, mode="skincare")
    assert "brightening" in {s.lower() for s in signals} or any("brighten" in s.lower() for s in signals)

    product = {
        "productType": "Serum",
        "name": "Continual-G Serum",
        "skinTypes": ["combination", "dry", "normal", "sensitive"],
        "benefit": [],
        "claims": ["Natural glow", "Anti-aging"],
    }
    tile_product = {
        "ingredients": [
            {"inci_name": "Gamma-Glutamylcysteine"},
            {"inci_name": "Tetrahydrocurcumin"},
            {"inci_name": "Tocopheryl Acetate"},
        ],
        "key_ingredients": [],
    }
    product_benefits = build_product_benefit_signals(
        product=product,
        tile_product=tile_product,
        tag_names=["Anti-Aging", "Radiant Skin"],
        mode="skincare",
        active_dossiers=dossiers,
    )
    result = profile_match_engines.evaluate_suitability(
        skin_type="combination",
        concerns=["uneven-skintone", "dark-circles", "Dryness"],
        benefits=["Brightens and evens skin tone"],
        declared_types=["combination", "dry", "normal", "sensitive"],
        product_primary="",
        product_benefits=product_benefits,
        mode="skincare",
    )
    assert "brightening" in result["matched_desired_benefits"]
    assert result["final_score"] >= 55
    assert result["band"] in ("good", "great", "mixed")
