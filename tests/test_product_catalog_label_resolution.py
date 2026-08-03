"""ObjectId / extended-JSON catalog fields must resolve for match scoring inputs."""

from __future__ import annotations

from bson import ObjectId

from app.label_looker.engines import profile_match as profile_match_engines
from app.label_looker.services.product_marketing_signals import build_product_benefit_signals
from app.label_looker.services.profile_taxonomy_resolver import _resolve_list_values


def test_resolve_list_values_maps_extended_json_oid_dicts():
    oid = ObjectId("681b224610e9409e12c03ace")
    resolved = {oid: "Nourishing"}
    labels = _resolve_list_values([{"$oid": str(oid)}, "Sun Protection"], resolved)
    assert labels == ["Nourishing", "Sun Protection"]


def test_resolved_skin_types_drive_exact_type_fit():
    """Without resolution, ObjectId skinTypes → unknown; with labels → exact."""
    result_unknown = profile_match_engines.evaluate_suitability(
        skin_type="combination",
        concerns=["Dryness"],
        benefits=["Sun Protection"],
        declared_types=[],  # ObjectIds dropped by string-only extractors
        product_primary="",
        product_benefits=["Sun Protection", "Nourishing"],
        mode="skincare",
    )
    assert result_unknown["type_match"] == "unknown"

    result = profile_match_engines.evaluate_suitability(
        skin_type="combination",
        concerns=["Dryness"],
        benefits=["Sun Protection"],
        declared_types=["dry", "normal", "oily", "combination", "sensitive"],
        product_primary="Dryness",
        product_benefits=["Sun Protection", "Nourishing", "Dryness"],
        mode="skincare",
    )
    assert result["type_match"] == "exact"
    assert result["matched_desired_benefits"] == ["sun protection"]


def test_product_concern_labels_feed_benefit_signals():
    signals = build_product_benefit_signals(
        product={"productType": "Serum", "benefit": [], "skinConcerns": []},
        tile_product={},
        mode="skincare",
        benefit_labels=["Brightening"],
        concern_labels=["Uneven Skin Tone", "Dryness"],
    )
    lowered = {s.lower() for s in signals}
    assert "brightening" in lowered
    assert "uneven skin tone" in lowered or "dryness" in lowered
    result = profile_match_engines.evaluate_suitability(
        skin_type="dry",
        concerns=["Dryness", "Uneven Skin Tone"],
        benefits=["Brightening"],
        declared_types=["dry"],
        product_primary="Dryness",
        product_benefits=signals,
        mode="skincare",
    )
    assert "brightening" in result["matched_desired_benefits"]
    assert result["unmatched_desired_benefits"] == []
