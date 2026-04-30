from __future__ import annotations

from bson import ObjectId
import pytest

from app.label_looker import profile_match_engines
from app.label_looker import profile_match_service
from app.label_looker import tile_content_generator


def test_skin_type_match_exact_adjacent_opposite():
    assert profile_match_engines.skin_type_match("oily", ["oily"]) == "exact"
    assert profile_match_engines.skin_type_match("oily", ["combination"]) == "adjacent"
    assert profile_match_engines.skin_type_match("oily", ["dry"]) == "opposite"


def test_score_to_band_thresholds():
    assert profile_match_engines.score_to_band(85) == "great"
    assert profile_match_engines.score_to_band(60) == "good"
    assert profile_match_engines.score_to_band(59) == "low"


def test_suitability_worked_example_aligns_to_spec_shape():
    result = profile_match_engines.evaluate_suitability(
        skin_type="oily",
        concerns=["oiliness", "pigmentation", "dullness"],
        benefits=["less_oil", "spot_fading"],
        declared_types=["combination", "normal"],
        product_primary="dryness",
        product_benefits=["hydration", "dullness"],
    )
    assert result["type_match"] == "adjacent"
    assert result["type_ceiling"] == 80
    assert result["final_score"] == 28
    assert result["band"] == "low"
    assert "oiliness" in result["unmet_needs"]


def test_safety_block_for_pregnancy_retinoid():
    safety = profile_match_engines.evaluate_safety(
        age=30,
        life_stages=["pregnancy"],
        conditions=[],
        key_ingredients=[{"inci_name": "retinol"}],
    )
    assert safety["severity"] == "block"
    assert safety["triggers"][0]["rule_id"] == "S1.PREG_RETINOID"


def test_observations_prioritize_user_gap_in_low_state():
    observations = profile_match_engines.evaluate_observations(
        state="low",
        safety={"severity": "clear", "triggers": []},
        unmet_needs=["oiliness"],
        product_primary="dryness",
        claims=["hydration"],
    )
    assert observations
    assert observations[0]["id"] == "U03"
    assert len(observations) <= 2


class _FakeCursor:
    def __init__(self, docs):
        self._iter = iter(docs)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _FakeCollection:
    def __init__(self, docs):
        self.docs = docs

    def find(self, query, projection):
        ids = set(query["_id"]["$in"])
        matched = [{k: v for k, v in row.items() if k in projection or k == "_id"} for row in self.docs if row["_id"] in ids]
        return _FakeCursor(matched)


@pytest.mark.anyio
async def test_resolve_ingredients_supports_objectid_rows_for_both_fields():
    water_id = ObjectId()
    niacinamide_id = ObjectId()
    mushroom_id = ObjectId()

    branded_ingredient_coll = _FakeCollection(
        [
            {"_id": water_id, "ingredient_name": "Aqua"},
            {"_id": niacinamide_id, "ingredient_name": "Niacinamide"},
        ]
    )
    ingredient_coll = _FakeCollection(
        [
            {"_id": mushroom_id, "name": "Nameko Mushroom Extract"},
        ]
    )

    ingredients_rows = [{"$oid": str(water_id)}, {"$oid": str(mushroom_id)}]
    key_ingredients_rows = [{"$oid": str(niacinamide_id)}]

    ingredients = await profile_match_service._resolve_ingredients_from_rows(
        rows=ingredients_rows,
        branded_ingredients_coll=branded_ingredient_coll,
        ingredient_coll=ingredient_coll,
    )
    key_ingredients = await profile_match_service._resolve_ingredients_from_rows(
        rows=key_ingredients_rows,
        branded_ingredients_coll=branded_ingredient_coll,
        ingredient_coll=ingredient_coll,
    )

    assert [row["inci_name"] for row in ingredients] == ["Aqua", "Nameko Mushroom Extract"]
    assert [row["inci_name"] for row in key_ingredients] == ["Niacinamide"]


def test_extract_desired_benefits_prefers_request_then_db_fallback():
    from_body = profile_match_service._extract_desired_benefits(
        body={"desiredBenefits": ["oil control", "dark spots"]},
        details={"skinGoals": ["hydration"]},
        mode="skincare",
    )
    assert from_body == ["oil control", "dark spots"]

    fallback = profile_match_service._extract_desired_benefits(
        body={"mainBenefit": ""},
        details={"skinGoals": ["hydration"]},
        mode="skincare",
    )
    assert fallback == ["hydration"]


def test_normalize_mode_for_match_detects_haircare():
    mode = profile_match_service._normalize_mode_for_match(
        body={},
        product={"productType": "Hair Serum"},
    )
    assert mode == "haircare"


def test_tile_prompt_user_profile_is_mode_aware():
    prompt = tile_content_generator.build_prompt(
        user={
            "mode": "haircare",
            "age": 29,
            "gender": "female",
            "hair_type": "wavy",
            "concerns": ["frizz", "breakage"],
            "benefits": ["smoothness"],
            "life_stages": [],
        },
        product={
            "brand": "BrandX",
            "name": "Hair Serum",
            "category": "haircare",
            "declared_for_skin_types": [],
            "claims": ["anti-frizz"],
            "ingredients": [],
            "key_ingredients": [],
        },
        scoring={"state": "good", "score": 68, "band": "good", "breakdown": [], "unmet_needs": []},
        observations=[],
    )
    assert "Profile mode: haircare" in prompt
    assert "Hair type: wavy" in prompt
    assert "Hair concerns (priority order): frizz, breakage" in prompt
    assert "Desired benefits: smoothness" in prompt
