"""Unit tests for active dossier prompt formatting / helpers."""

from __future__ import annotations

from app.label_looker.prompts_controller import ingredient_analysis_user_message
from app.label_looker.services.active_ingredient_dossiers import (
    _collect_candidates,
    _is_active_category,
    format_active_dossiers_for_prompt,
)


def test_format_active_dossiers_for_prompt():
    text = format_active_dossiers_for_prompt(
        [
            {
                "name": "Niacinamide",
                "functionality": ["Skin conditioning", "Brightening"],
                "chemicalClasses": ["Vitamin"],
                "description": "Supports barrier and tone.",
            }
        ]
    )
    assert "Niacinamide" in text
    assert "Skin conditioning, Brightening" in text
    assert "Vitamin" in text
    assert "Supports barrier and tone." in text


def test_ingredient_analysis_prompt_includes_active_dossiers():
    dossiers = format_active_dossiers_for_prompt(
        [
            {
                "name": "Carmine",
                "functionality": ["Colorant"],
                "chemicalClasses": [],
                "description": "Natural red pigment.",
            }
        ]
    )
    prompt = ingredient_analysis_user_message(
        ingredients_text="Aqua\nCarmine",
        specific_type="serum",
        main_benefit="brightening",
        langauge="English",
        active_dossiers_text=dossiers,
    )
    assert "Authoritative Active ingredient dossiers" in prompt
    assert "Carmine" in prompt
    assert "Functionality: Colorant" in prompt
    assert "Prefer Active dossiers when present" in prompt
    assert "Ingredient list:  Aqua\nCarmine" in prompt


def test_collect_candidates_prefers_product_rows():
    product = {
        "ingredients": [{"_id": "68a0761e09adfea92ed96912", "name": ""}],
        "keyIngredients": ["Niacinamide"],
    }
    rows = _collect_candidates(ingredient_names=["Glycerin"], product=product)
    assert len(rows) >= 2
    assert any(name == "Niacinamide" for _, name in rows)
    assert any(name == "Glycerin" for _, name in rows)


def test_is_active_category_case_insensitive():
    assert _is_active_category("Active")
    assert _is_active_category("active")
    assert not _is_active_category("Excipient")
