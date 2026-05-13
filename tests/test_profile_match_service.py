from __future__ import annotations

from bson import ObjectId
import pytest

from app.label_looker.engines import profile_match as profile_match_engines
from app.label_looker.engines.base_formula.context import resolve_runtime_context
from app.label_looker.generation import tile_content as tile_content_generator
from app.label_looker.modules.match_my_profile import service_impl as profile_match_service
from app.label_looker.engines.base_formula.derive import derive_base_formula_record
from app.label_looker.engines.base_formula.overrides import apply_overrides


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
    assert result["final_score"] == 15
    assert result["band"] == "low"
    assert "less oil" in result["unmet_needs"]


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


def test_safety_gates_for_sensitive_fragrance_and_barrier_alcohol():
    safety = profile_match_engines.evaluate_safety(
        age=27,
        life_stages=[],
        conditions=["sensitive skin", "barrier_compromised"],
        key_ingredients=[{"inci_name": "Alcohol Denat"}, {"inci_name": "Parfum"}],
    )
    ids = {t["rule_id"] for t in safety["triggers"]}
    assert "S6.SENSITIVE_FRAGRANCE" in ids
    assert "S7.BARRIER_ALCOHOL" in ids
    assert safety["severity"] in {"hard", "block"}


def test_observations_include_comedogenic_and_fungal_notes_when_flagged():
    observations = profile_match_engines.evaluate_observations(
        state="good",
        safety={"severity": "clear", "triggers": []},
        unmet_needs=[],
        product_primary="oil control",
        claims=["anti-acne"],
        base_formula={"comedogenic_risk": "high", "fungal_acne_safe": "no"},
        user_flags={"fungal_acne_prone": True},
    )
    ids = [o["id"] for o in observations]
    assert "O10" in ids or "O11" in ids


def test_derive_base_formula_record_detects_risk_markers():
    base = derive_base_formula_record(
        inci_list=[
            {"position": 1, "inci_name": "Aqua"},
            {"position": 2, "inci_name": "Alcohol Denat"},
            {"position": 3, "inci_name": "Parfum"},
            {"position": 4, "inci_name": "Isopropyl Myristate"},
            {"position": 5, "inci_name": "Polysorbate 20"},
        ],
        brand_declared={"texture": "gel", "is_oilfree": True, "finish": "dewy"},
    )
    assert base["texture"] in {"gel", "gel_cream"}
    assert base["finish"] in {"dewy", "natural", "luminous", "matte"}
    assert base["alcohol_level"] in {"high", "medium"}
    assert base["fragrance_level"] in {"low", "standard", "heavy"}
    assert base["comedogenic_risk"] in {"high", "moderate"}
    assert base["fungal_acne_safe"] in {"no", "caution"}
    assert base["hydration_state"] == "hydrous"


def test_context_post_procedure_sets_barrier_compromised():
    ctx = resolve_runtime_context(
        {
            "id": "u1",
            "skin_type": "oily",
            "concerns": [],
            "benefits": [],
            "self_declared_flags": [],
            "last_procedure_date": "2099-01-01T00:00:00",
        },
        "411045",
        __import__("datetime").datetime(2099, 1, 5),
    )
    assert ctx["flags"]["post_procedure"] is True
    assert ctx["flags"]["barrier_compromised"] is True


def test_override_barrier_alcohol_block_and_mature_lipid_promote():
    result = apply_overrides(
        ctx={
            "user_id": "u1",
            "skin_type": "dry",
            "climate_zone": "temperate",
            "season": "nov_feb",
            "pin_code": None,
            "flags": {"barrier_compromised": True, "mature_skin": True},
            "age": 45,
            "concerns": [],
            "benefits": [],
            "life_stages": [],
        },
        base_formula={
            "texture": "cream",
            "continuous_phase": "lipidic",
            "alcohol_level": "high",
            "fragrance_level": "none",
        },
        suitability_score=70.0,
        base_formula_score={"total": 10.0, "details": [], "has_finish_axis": False, "rationale_strings": []},
    )
    actions = {(o["family"], o["action"]) for o in result["overrides_applied"]}
    assert ("barrier_compromised", "block") in actions
    assert ("mature_skin", "promote") in actions


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


def test_effective_user_details_fills_from_auth_when_mongo_empty():
    from app.label_looker.modules.match_my_profile.service_impl import _effective_user_details_for_match

    user = {
        "firstName": "Rutu",
        "lastName": "Ghatge",
        "age": 29,
        "gender": "female",
        "skinType": "normal",
        "skinConcerns": [],
        "skinGoals": ["hydration"],
        "hairType": "straight",
        "hairConcerns": [],
        "hairGoals": [],
    }
    merged = _effective_user_details_for_match({}, user)
    assert merged["age"] == 29
    assert merged["gender"] == "female"
    assert merged["skinType"] == "normal"
    assert merged["skinGoals"] == ["hydration"]
    assert merged["name"] == "Rutu Ghatge"


def test_effective_user_details_mongo_wins_when_set():
    from app.label_looker.modules.match_my_profile.service_impl import _effective_user_details_for_match

    details = {"age": 40, "gender": "male", "skinType": "oily", "skinConcerns": ["acne"], "skinGoals": [], "name": "DB Name"}
    user = {"firstName": "X", "age": 29, "gender": "female", "skinType": "normal"}
    merged = _effective_user_details_for_match(details, user)
    assert merged["age"] == 40
    assert merged["gender"] == "male"
    assert merged["skinType"] == "oily"
    assert merged["skinConcerns"] == ["acne"]


def test_as_string_list_keeps_nonempty_and_empty_list():
    from app.label_looker.modules.match_my_profile.service_impl import _as_string_list

    assert _as_string_list(["dullness", " "]) == ["dullness"]
    assert _as_string_list([]) == []
    assert _as_string_list("  hi  ") == ["hi"]
    assert _as_string_list(None) == []
