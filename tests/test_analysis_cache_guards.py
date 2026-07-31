"""Tests for analysis cache freshness + invented categorization guards."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.label_looker.services.analysis_cache_guards import (
    analysis_cache_time,
    coerce_to_utc,
    filter_names_to_allowed,
    is_analysis_fresh_for_product,
    normalize_ingredient_name,
    product_updated_at,
    sanitize_ingredient_categorization,
)


def test_normalize_ingredient_name_collapses_case_and_space():
    assert normalize_ingredient_name("  Tocopheryl   Acetate ") == "tocopheryl acetate"


def test_coerce_naive_and_aware_to_utc():
    naive = datetime(2026, 7, 1, 12, 0, 0)
    aware = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert coerce_to_utc(naive) == aware
    assert coerce_to_utc("2026-07-01T12:00:00Z") == aware


def test_product_updated_at_reads_updatedAt():
    ts = datetime(2026, 7, 30, 10, 0, 0, tzinfo=timezone.utc)
    assert product_updated_at({"updatedAt": ts}) == ts
    assert product_updated_at({}) is None
    assert product_updated_at(None) is None


def test_analysis_cache_time_prefers_updated_over_created():
    created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    updated = datetime(2026, 7, 1, tzinfo=timezone.utc)
    assert analysis_cache_time({"createdAt": created, "updatedAt": updated}) == updated
    assert analysis_cache_time({"createdAt": created}) == created


def test_fresh_when_analysis_at_or_after_product_update():
    product_ts = datetime(2026, 7, 30, 10, 0, 0, tzinfo=timezone.utc)
    doc = {"updatedAt": product_ts}
    assert is_analysis_fresh_for_product(doc, product_ts) is True
    doc_newer = {"updatedAt": product_ts + timedelta(minutes=5)}
    assert is_analysis_fresh_for_product(doc_newer, product_ts) is True


def test_stale_when_product_newer_than_analysis():
    product_ts = datetime(2026, 7, 31, 10, 0, 0, tzinfo=timezone.utc)
    doc = {"updatedAt": product_ts - timedelta(days=2)}
    assert is_analysis_fresh_for_product(doc, product_ts) is False


def test_keep_cache_when_product_has_no_updated_at():
    doc = {"updatedAt": datetime(2026, 1, 1, tzinfo=timezone.utc)}
    assert is_analysis_fresh_for_product(doc, None) is True


def test_stale_when_analysis_missing_timestamp():
    product_ts = datetime(2026, 7, 31, tzinfo=timezone.utc)
    assert is_analysis_fresh_for_product({"analyticDetail": {"opinion": "x"}}, product_ts) is False


def test_filter_drops_invented_names_keeps_canonical():
    allowed = ["Fragrance", "Tocopheryl Acetate", "Phenoxyethanol"]
    assert filter_names_to_allowed(["fragrance", "BHT", "Tocopheryl Acetate"], allowed) == [
        "Fragrance",
        "Tocopheryl Acetate",
    ]


def test_sanitize_removes_bht_from_synthetic():
    analytic = {
        "opinion": "ok",
        "ingredientCategorization": {
            "plant-derived": ["Caprylic/Capric Triglyceride"],
            "synthetic": [
                "Cyclopentasiloxane",
                "Fragrance",
                "BHT",
                "Phenoxyethanol",
            ],
        },
    }
    allowed = [
        "Caprylic/Capric Triglyceride",
        "Cyclopentasiloxane",
        "Fragrance",
        "Phenoxyethanol",
    ]
    cleaned, changed = sanitize_ingredient_categorization(analytic, allowed)
    assert changed is True
    assert cleaned["ingredientCategorization"]["synthetic"] == [
        "Cyclopentasiloxane",
        "Fragrance",
        "Phenoxyethanol",
    ]
    assert "BHT" not in cleaned["ingredientCategorization"]["synthetic"]
    assert cleaned["opinion"] == "ok"


def test_sanitize_noop_when_already_clean():
    analytic = {
        "ingredientCategorization": {
            "synthetic": ["Fragrance", "Phenoxyethanol"],
        }
    }
    cleaned, changed = sanitize_ingredient_categorization(
        analytic, ["Fragrance", "Phenoxyethanol"]
    )
    assert changed is False
    assert cleaned["ingredientCategorization"]["synthetic"] == ["Fragrance", "Phenoxyethanol"]
