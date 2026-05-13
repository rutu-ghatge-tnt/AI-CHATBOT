"""Ingredient list resolution for product analysis (PDP vs LLM / client payloads)."""

from __future__ import annotations

from app.label_looker.modules.product_analysis.analysis_service_impl import (
    _normalize_analysis_payload,
)


def test_normalize_prefers_fallback_when_model_returns_wrapped_ingredients():
    parsed = {
        "analyticDetail": {"opinion": "x"},
        "ingredients": [
            "A lightweight serum that targets pigmentation",
            "fine lines",
            "and barrier damage while boosting hydration and skin repair.",
        ],
    }
    fallback = ["Niacinamide", "Aqua", "Glycerin"]
    analytic, ing_out = _normalize_analysis_payload(parsed, fallback)
    assert analytic == {"opinion": "x"}
    assert ing_out == fallback


def test_normalize_uses_model_ingredients_when_fallback_empty():
    parsed = {
        "analyticDetail": {"opinion": "x"},
        "ingredients": ["Aqua", "Glycerin"],
    }
    analytic, ing_out = _normalize_analysis_payload(parsed, [])
    assert ing_out == ["Aqua", "Glycerin"]


def test_normalize_flat_prompt_shape_uses_fallback():
    parsed = {
        "opinion": "ok",
        "keyIngredients": [],
        "benefitsOffered": [],
        "importantConsiderations": [],
        "productUsageTips": [],
        "ingredientCategorization": {},
    }
    fb = ["Water", "Phenoxyethanol"]
    analytic, ing_out = _normalize_analysis_payload(parsed, fb)
    assert analytic == parsed
    assert ing_out == fb
