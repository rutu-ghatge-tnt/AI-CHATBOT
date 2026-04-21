from __future__ import annotations

from datetime import datetime
from typing import Any

from anthropic import AsyncAnthropic
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection

from app.label_looker.constants import DEFAULT_LANGUAGE
from app.label_looker.errors import ScannerApiError
from app.label_looker.prompts_controller import ingredient_analysis_user_message
from app.label_looker.settings import get_label_looker_settings
from app.label_looker.text_extract import extract_first_json_object


GENERIC_ANALYSIS_FAIL = "There's no data available right now. Please try again later."
_VALID_MODES = {"skincare", "haircare", "lipcare"}


def _normalize_mode(*, product_for: Any, specific_type: Any, main_benefit: Any, mode_hint: Any = None) -> str:
    hint = str(mode_hint or "").strip().lower()
    if hint in _VALID_MODES:
        return hint
    text = " ".join([str(product_for or ""), str(specific_type or ""), str(main_benefit or "")]).lower()
    lip_keywords = ["lip", "lips", "lipcare", "lip care", "lip balm", "lip mask", "lip serum", "lip scrub"]
    if any(k in text for k in lip_keywords):
        return "lipcare"
    hair_keywords = ["hair", "scalp", "dandruff", "frizz", "fall", "strand", "follicle"]
    return "haircare" if any(k in text for k in hair_keywords) else "skincare"


def _infer_mode_from_product(product: dict[str, Any] | None) -> str | None:
    if not product:
        return None
    # lipcare first, because lip products can also carry generic skin fields.
    ptype = str(product.get("productType") or "").lower()
    pname = str(product.get("productName") or "").lower()
    if "lip" in ptype or "lip" in pname:
        return "lipcare"
    if isinstance(product.get("lipTypes"), list) and len(product.get("lipTypes") or []) > 0:
        return "lipcare"
    if isinstance(product.get("lipConcerns"), list) and len(product.get("lipConcerns") or []) > 0:
        return "lipcare"
    if isinstance(product.get("hairTypes"), list) and len(product.get("hairTypes") or []) > 0:
        return "haircare"
    if isinstance(product.get("hairConcerns"), list) and len(product.get("hairConcerns") or []) > 0:
        return "haircare"
    if isinstance(product.get("skinTypes"), list) and len(product.get("skinTypes") or []) > 0:
        return "skincare"
    if isinstance(product.get("skinConcerns"), list) and len(product.get("skinConcerns") or []) > 0:
        return "skincare"
    if "hair" in ptype or "scalp" in ptype:
        return "haircare"
    if "skin" in ptype or "face" in ptype:
        return "skincare"
    return None


async def _fetch_product_by_id(
    *,
    products_coll: AsyncIOMotorCollection,
    product_id: Any,
) -> dict[str, Any] | None:
    if not product_id:
        return None
    pid = str(product_id).strip()
    query: dict[str, Any]
    if ObjectId.is_valid(pid):
        query = {"_id": ObjectId(pid)}
    else:
        query = {"_id": pid}
    return await products_coll.find_one(query)


def _ingredients_from_product(product: dict[str, Any] | None) -> list[str]:
    if not product:
        return []
    rows = product.get("ingredients")
    if not isinstance(rows, list):
        return []
    out: list[str] = []
    for r in rows:
        if isinstance(r, dict):
            n = str(r.get("name") or "").strip()
            if n:
                out.append(n)
        elif isinstance(r, str) and r.strip():
            out.append(r.strip())
    return list(dict.fromkeys(out))


def _resolve_analysis_mode(
    *,
    body: dict[str, Any],
    product: dict[str, Any] | None,
    specific_type: Any,
    main_benefit: Any,
) -> str:
    by_product = _infer_mode_from_product(product)
    if by_product:
        return by_product
    return _normalize_mode(
        product_for=body.get("productFor"),
        specific_type=specific_type,
        main_benefit=main_benefit,
        mode_hint=body.get("mode"),
    )


def _required_fields_for_mode(mode: str) -> list[str]:
    if mode == "haircare":
        return ["age", "gender", "hairType", "hairConcerns"]
    if mode == "lipcare":
        # lipcare keeps away from hair fields; prioritize lip fields, fallback to skin fields.
        return ["age", "gender", "lipType", "lipConcerns"]
    return ["age", "gender", "skinType", "skinConcerns"]


def _current_field_value(details: dict[str, Any], mode: str, field: str) -> Any:
    if field in ("age", "gender"):
        return details.get(field)
    if mode == "lipcare":
        if field in ("lipType", "lipConcerns"):
            # Backward compatibility: if lip-specific data isn't stored yet, use skin profile.
            return details.get(field) or details.get("skinType" if field == "lipType" else "skinConcerns")
        return details.get(field)
    if mode == "skincare" and field in ("skinType", "skinConcerns"):
        return details.get(field)
    if mode == "haircare" and field in ("hairType", "hairConcerns"):
        return details.get(field)
    return None


def _pick_two_fields(required_fields: list[str], final_values: dict[str, Any], attempts: dict[str, list[Any]]) -> list[str]:
    ranked: list[tuple[int, str]] = []
    for f in required_fields:
        if f in final_values:
            continue
        a = attempts.get(f) or []
        ranked.append((len(a), f))
    ranked.sort(key=lambda x: (x[0], x[1]))
    return [f for _, f in ranked[:2]]


def _has_missing_required(details: dict[str, Any], mode: str, final_values: dict[str, Any]) -> bool:
    for f in _required_fields_for_mode(mode):
        if f in final_values:
            continue
        val = _current_field_value(details, mode, f)
        if val is None:
            return True
        if isinstance(val, str) and not val.strip():
            return True
        if isinstance(val, list) and len(val) == 0:
            return True
    return False


async def _upsert_validation_state(
    *,
    user_details_coll: AsyncIOMotorCollection,
    user_id: Any,
    mode: str,
    bump_scan_count: bool,
    details_doc: dict[str, Any] | None,
) -> dict[str, Any]:
    details = details_doc or {}
    llv = dict(details.get("labelLookerValidation") or {})
    mode_state = dict(llv.get(mode) or {})
    if bump_scan_count:
        mode_state["scanCount"] = int(mode_state.get("scanCount") or 0) + 1
    else:
        mode_state["scanCount"] = int(mode_state.get("scanCount") or 0)
    mode_state.setdefault("finalized", False)
    mode_state.setdefault("promptRounds", 0)
    mode_state.setdefault("attempts", {})
    mode_state.setdefault("finalValues", {})
    llv[mode] = mode_state
    await user_details_coll.update_one(
        {"userId": user_id},
        {"$set": {"userId": user_id, "labelLookerValidation": llv, "updatedAt": datetime.now()}},
        upsert=True,
    )
    return mode_state


def _build_prompt_payload(
    *,
    mode: str,
    mode_state: dict[str, Any],
    details: dict[str, Any],
) -> dict[str, Any]:
    required_fields = _required_fields_for_mode(mode)
    attempts = dict(mode_state.get("attempts") or {})
    final_values = dict(mode_state.get("finalValues") or {})
    if bool(mode_state.get("finalized")):
        return {"shouldPrompt": False, "mode": mode, "finalized": True, "fields": []}
    if int(mode_state.get("scanCount") or 0) % 2 != 0:
        return {"shouldPrompt": False, "mode": mode, "finalized": False, "fields": []}
    if not _has_missing_required(details, mode, final_values):
        return {"shouldPrompt": False, "mode": mode, "finalized": False, "fields": []}
    fields = _pick_two_fields(required_fields, final_values, attempts)
    if not fields:
        return {"shouldPrompt": False, "mode": mode, "finalized": False, "fields": []}
    return {
        "shouldPrompt": True,
        "mode": mode,
        "finalized": False,
        "fields": fields,
        "promptReason": "After every 2 scans, verify profile data for integrity.",
    }


def _apply_answers_to_state(mode: str, mode_state: dict[str, Any], answers: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    required = set(_required_fields_for_mode(mode))
    attempts = dict(mode_state.get("attempts") or {})
    final_values = dict(mode_state.get("finalValues") or {})
    updates_for_details: dict[str, Any] = {}

    for field, value in answers.items():
        if field not in required:
            continue
        if field in final_values:
            continue
        key = field
        arr = list(attempts.get(key) or [])
        arr.append(value)
        attempts[key] = arr
        if len(arr) >= 3:
            final_values[key] = arr[-1]
            updates_for_details[field] = arr[-1]
            continue
        if len(arr) == 2 and str(arr[0]).strip().lower() == str(arr[1]).strip().lower():
            final_values[key] = arr[1]
            updates_for_details[field] = arr[1]

    mode_state["attempts"] = attempts
    mode_state["finalValues"] = final_values
    mode_state["promptRounds"] = int(mode_state.get("promptRounds") or 0) + 1
    if all(f in final_values for f in _required_fields_for_mode(mode)):
        mode_state["finalized"] = True
    return mode_state, updates_for_details


def _normalize_analysis_payload(parsed: dict[str, Any], fallback_ingredients: Any) -> tuple[dict[str, Any], list[Any]]:
    """
    Accept both payload styles:
    1) { analyticDetail, ingredients } (older contract)
    2) prompt-driven object with keys like opinion/keyIngredients/.../ingredientCategorization
    """
    analytic = parsed.get("analyticDetail")
    ing_out = parsed.get("ingredients")
    if analytic is not None and ing_out is not None:
        return analytic, ing_out if isinstance(ing_out, list) else [ing_out]

    # New prompt shape: store full JSON as analyticDetail and keep ingredients list from request/scan.
    analytic = parsed
    if isinstance(fallback_ingredients, list):
        ing_list = fallback_ingredients
    elif fallback_ingredients is None:
        ing_list = []
    else:
        ing_list = [fallback_ingredients]
    return analytic, ing_list


def _ingredient_list_from_text(raw: str) -> list[str]:
    parts = []
    for token in raw.replace("\n", ",").replace(";", ",").split(","):
        t = token.strip()
        if t:
            parts.append(t)
    # de-dupe while preserving order
    return list(dict.fromkeys(parts))


def _extract_user_id(user: dict[str, Any]) -> Any:
    uid = user.get("_id") or user.get("id")
    if uid is None:
        return None
    s = str(uid)
    if ObjectId.is_valid(s):
        return ObjectId(s)
    return s


def _build_personalization_context(details: dict[str, Any]) -> str:
    keys = [
        "skinType",
        "skinConcerns",
        "skinGoals",
        "skinTone",
        "lipType",
        "lipConcerns",
        "lipGoals",
        "hairType",
        "hairConcerns",
        "hairGoals",
        "sleepDurations",
        "dietaryPreference",
        "stressLevel",
    ]
    lines = []
    for k in keys:
        if k in details:
            lines.append(f"- {k}: {details.get(k)}")
    return "\n".join(lines)


async def ingredient_analysis(*, body: dict[str, Any], user: dict[str, Any] | None) -> dict[str, Any]:
    scan_id = body.get("scanId")
    if not scan_id:
        raise ScannerApiError(400, "scanId is required")

    s = get_label_looker_settings()
    from app.label_looker.db import get_scanner_db

    db = get_scanner_db()
    scan_coll: AsyncIOMotorCollection = db[s.coll_scan_analysis]
    user_details_coll: AsyncIOMotorCollection = db[s.coll_user_details]
    products_coll: AsyncIOMotorCollection = db[s.coll_products]

    oid = ObjectId(str(scan_id)) if ObjectId.is_valid(str(scan_id)) else None
    if oid is None:
        raise ScannerApiError(400, "Invalid scanId")

    doc = await scan_coll.find_one({"_id": oid})
    if not doc:
        raise ScannerApiError(404, "Scan not found")

    ingredients = body.get("ingredients")
    if ingredients is None or (isinstance(ingredients, list) and len(ingredients) == 0):
        ingredients = doc.get("extractedIngredients") or []

    product = await _fetch_product_by_id(products_coll=products_coll, product_id=body.get("productId"))
    if (ingredients is None or (isinstance(ingredients, list) and len(ingredients) == 0)) and product:
        ingredients = _ingredients_from_product(product)

    specific_type = body.get("specificType")
    main_benefit = body.get("mainBenefit")
    if not specific_type and product:
        specific_type = product.get("productType")
    if not main_benefit and product and isinstance(product.get("benefit"), list):
        b = product.get("benefit") or []
        main_benefit = ", ".join(str(x) for x in b if str(x).strip()) if b else main_benefit
    language = body.get("langauge") or DEFAULT_LANGUAGE

    text_block = "\n".join(str(x) for x in ingredients) if isinstance(ingredients, list) else str(ingredients)
    user_msg = ingredient_analysis_user_message(
        ingredients_text=text_block,
        specific_type=specific_type,
        main_benefit=main_benefit,
        langauge=str(language),
    )

    client = AsyncAnthropic(api_key=s.anthropic_api_key)
    try:
        msg = await client.messages.create(
            model=s.anthropic_model,
            max_tokens=8192,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = "".join(getattr(b, "text", "") for b in msg.content)
        parsed = extract_first_json_object(raw)
        analytic, ing_out = _normalize_analysis_payload(parsed, ingredients)
        await scan_coll.update_one(
            {"_id": oid},
            {
                "$set": {
                    "analyticDetail": analytic,
                    "ingredients": ing_out,
                    "ingredientAnalysisError": None,
                    "updatedAt": datetime.now(),
                }
            },
        )
        profile_validation = None
        user_id = _extract_user_id(user or {})
        if user_id is not None:
            mode = _resolve_analysis_mode(
                body=body,
                product=product,
                specific_type=specific_type,
                main_benefit=main_benefit,
            )
            details_doc = await user_details_coll.find_one({"userId": user_id}) or {}
            mode_state = await _upsert_validation_state(
                user_details_coll=user_details_coll,
                user_id=user_id,
                mode=mode,
                bump_scan_count=True,
                details_doc=details_doc,
            )
            profile_validation = _build_prompt_payload(mode=mode, mode_state=mode_state, details=details_doc)
        return {
            "scanId": str(scan_id),
            "analyticDetail": analytic,
            "ingredients": ing_out,
            "profileValidation": profile_validation,
        }
    except Exception as e:
        await scan_coll.update_one(
            {"_id": oid},
            {"$set": {"ingredientAnalysisError": str(e), "updatedAt": datetime.now()}},
        )
        raise ScannerApiError(500, GENERIC_ANALYSIS_FAIL) from e


async def ingredient_analysis_from_text(
    *,
    body: dict[str, Any],
    user: dict[str, Any] | None,
) -> dict[str, Any]:
    s = get_label_looker_settings()
    from app.label_looker.db import get_scanner_db

    db = get_scanner_db()
    scan_coll: AsyncIOMotorCollection = db[s.coll_scan_analysis]
    scan_detail_coll: AsyncIOMotorCollection = db[s.coll_scan_detail]
    user_details_coll: AsyncIOMotorCollection = db[s.coll_user_details]
    products_coll: AsyncIOMotorCollection = db[s.coll_products]

    ingredients = body.get("ingredients")
    ingredients_text = body.get("ingredientsText")
    product = await _fetch_product_by_id(products_coll=products_coll, product_id=body.get("productId"))
    if isinstance(ingredients, list) and ingredients:
        ing_list = [str(x).strip() for x in ingredients if str(x).strip()]
    elif isinstance(ingredients_text, str) and ingredients_text.strip():
        ing_list = _ingredient_list_from_text(ingredients_text)
    elif product:
        ing_list = _ingredients_from_product(product)
    else:
        raise ScannerApiError(400, "ingredients or ingredientsText is required")

    personalized = bool(body.get("personalizedMatching"))
    if personalized and not user:
        raise ScannerApiError(401, "Please login to use personalized matching")

    personalization_context = None
    user_id = _extract_user_id(user or {})
    details = await user_details_coll.find_one({"userId": user_id}) if user_id is not None else None
    if personalized:
        if user_id is None:
            raise ScannerApiError(401, "Please login to use personalized matching")
        personalization_context = _build_personalization_context(details or {})

    now = datetime.now()
    scan_doc = {
        "userId": user_id,
        "firstName": (user or {}).get("firstName"),
        "lastName": (user or {}).get("lastName"),
        "userProfileUrl": (user or {}).get("profileUrl"),
        "extractedIngredients": ing_list,
        "scansLeft": None,
        "scanImageError": None,
        "ingredientAnalysisError": None,
        "sourceType": "text",
        "createdAt": now,
        "updatedAt": now,
    }
    ins = await scan_coll.insert_one(scan_doc)
    scan_id = ins.inserted_id
    await scan_detail_coll.insert_one(
        {
            "scanAnalysisId": scan_id,
            "sourceType": "text",
            "extractedIngredients": ing_list,
            "createdAt": now,
            "updatedAt": now,
        }
    )

    specific_type = body.get("specificType")
    main_benefit = body.get("mainBenefit")
    if not specific_type and product:
        specific_type = product.get("productType")
    if not main_benefit and product and isinstance(product.get("benefit"), list):
        b = product.get("benefit") or []
        main_benefit = ", ".join(str(x) for x in b if str(x).strip()) if b else main_benefit
    language = body.get("langauge") or DEFAULT_LANGUAGE
    text_block = "\n".join(ing_list)
    user_msg = ingredient_analysis_user_message(
        ingredients_text=text_block,
        specific_type=specific_type,
        main_benefit=main_benefit,
        langauge=str(language),
        personalization_context=personalization_context,
    )

    client = AsyncAnthropic(api_key=s.anthropic_api_key)
    try:
        msg = await client.messages.create(
            model=s.anthropic_model,
            max_tokens=8192,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = "".join(getattr(b, "text", "") for b in msg.content)
        parsed = extract_first_json_object(raw)
        analytic, ing_out = _normalize_analysis_payload(parsed, ing_list)
        await scan_coll.update_one(
            {"_id": scan_id},
            {
                "$set": {
                    "analyticDetail": analytic,
                    "ingredients": ing_out,
                    "personalizedMatching": personalized,
                    "ingredientAnalysisError": None,
                    "updatedAt": datetime.now(),
                }
            },
        )
        profile_validation = None
        if user_id is not None:
            mode = _resolve_analysis_mode(
                body=body,
                product=product,
                specific_type=specific_type,
                main_benefit=main_benefit,
            )
            mode_state = await _upsert_validation_state(
                user_details_coll=user_details_coll,
                user_id=user_id,
                mode=mode,
                bump_scan_count=True,
                details_doc=details,
            )
            profile_validation = _build_prompt_payload(mode=mode, mode_state=mode_state, details=details or {})
        return {
            "scanId": str(scan_id),
            "analyticDetail": analytic,
            "ingredients": ing_out,
            "profileValidation": profile_validation,
        }
    except Exception as e:
        await scan_coll.update_one(
            {"_id": scan_id},
            {"$set": {"ingredientAnalysisError": str(e), "updatedAt": datetime.now()}},
        )
        raise ScannerApiError(500, GENERIC_ANALYSIS_FAIL) from e


async def submit_profile_validation(*, body: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    user_id = _extract_user_id(user)
    if user_id is None:
        raise ScannerApiError(401, "Please login to submit profile validation")
    answers = body.get("answers")
    if not isinstance(answers, dict) or not answers:
        raise ScannerApiError(400, "answers object is required")
    mode = _normalize_mode(
        product_for=body.get("productFor"),
        specific_type=body.get("specificType"),
        main_benefit=body.get("mainBenefit"),
        mode_hint=body.get("mode"),
    )

    s = get_label_looker_settings()
    from app.label_looker.db import get_scanner_db

    db = get_scanner_db()
    user_details_coll: AsyncIOMotorCollection = db[s.coll_user_details]
    products_coll: AsyncIOMotorCollection = db[s.coll_products]
    details = await user_details_coll.find_one({"userId": user_id}) or {"userId": user_id}
    product = await _fetch_product_by_id(products_coll=products_coll, product_id=body.get("productId"))

    resolved_mode = _resolve_analysis_mode(
        body=body,
        product=product,
        specific_type=body.get("specificType"),
        main_benefit=body.get("mainBenefit"),
    )
    llv = dict(details.get("labelLookerValidation") or {})
    mode_state = dict(
        llv.get(resolved_mode) or {"scanCount": 0, "promptRounds": 0, "attempts": {}, "finalValues": {}, "finalized": False}
    )
    mode_state, updates_for_details = _apply_answers_to_state(resolved_mode, mode_state, answers)
    llv[resolved_mode] = mode_state

    set_doc = {"labelLookerValidation": llv, "updatedAt": datetime.now()}
    # keep skincare and haircare separate
    for k, v in updates_for_details.items():
        if k in ("skinType", "skinConcerns") and resolved_mode != "skincare":
            continue
        if k in ("lipType", "lipConcerns") and resolved_mode != "lipcare":
            continue
        if k in ("hairType", "hairConcerns") and resolved_mode != "haircare":
            continue
        set_doc[k] = v
    if "age" in updates_for_details:
        set_doc["age"] = updates_for_details["age"]
    if "gender" in updates_for_details:
        set_doc["gender"] = updates_for_details["gender"]

    await user_details_coll.update_one({"userId": user_id}, {"$set": set_doc}, upsert=True)
    prompt = _build_prompt_payload(mode=resolved_mode, mode_state=mode_state, details={**details, **set_doc})
    return {
        "mode": resolved_mode,
        "finalized": bool(mode_state.get("finalized")),
        "finalValues": mode_state.get("finalValues") or {},
        "nextPrompt": prompt,
    }


async def profile_validation_status(*, body: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    """
    Check whether required profile fields are available for this user/mode,
    and whether prompt should appear now based on scan cadence.
    """
    user_id = _extract_user_id(user)
    if user_id is None:
        raise ScannerApiError(401, "Please login to check profile validation status")

    requested_user_id = body.get("userId")
    if requested_user_id is not None and str(requested_user_id).strip() and str(requested_user_id) != str(user_id):
        raise ScannerApiError(403, "Forbidden: userId mismatch")

    s = get_label_looker_settings()
    from app.label_looker.db import get_scanner_db

    db = get_scanner_db()
    user_details_coll: AsyncIOMotorCollection = db[s.coll_user_details]
    products_coll: AsyncIOMotorCollection = db[s.coll_products]
    details = await user_details_coll.find_one({"userId": user_id}) or {"userId": user_id}
    product = await _fetch_product_by_id(products_coll=products_coll, product_id=body.get("productId"))

    resolved_mode = _resolve_analysis_mode(
        body=body,
        product=product,
        specific_type=body.get("specificType"),
        main_benefit=body.get("mainBenefit"),
    )
    mode_state = await _upsert_validation_state(
        user_details_coll=user_details_coll,
        user_id=user_id,
        mode=resolved_mode,
        bump_scan_count=False,
        details_doc=details,
    )
    prompt = _build_prompt_payload(mode=resolved_mode, mode_state=mode_state, details=details)

    final_values = dict(mode_state.get("finalValues") or {})
    missing_fields: list[str] = []
    for f in _required_fields_for_mode(resolved_mode):
        if f in final_values:
            continue
        val = _current_field_value(details, resolved_mode, f)
        if val is None or (isinstance(val, str) and not val.strip()) or (isinstance(val, list) and len(val) == 0):
            missing_fields.append(f)

    return {
        "userId": str(user_id),
        "mode": resolved_mode,
        "requiredFields": _required_fields_for_mode(resolved_mode),
        "missingFields": missing_fields,
        "hasRequiredData": len(missing_fields) == 0,
        "scanCount": int(mode_state.get("scanCount") or 0),
        "finalized": bool(mode_state.get("finalized")),
        "shouldPromptNow": bool(prompt.get("shouldPrompt")),
        "prompt": prompt,
    }


async def put_feedback(*, body: dict[str, Any]) -> None:
    scan_id = body.get("scanId")
    if not scan_id:
        raise ScannerApiError(400, "scanId is required")
    rating = body.get("rating")
    feedback = body.get("feedback")
    if rating is not None and rating not in ("good", "okay", "bad"):
        raise ScannerApiError(400, "Invalid rating")

    s = get_label_looker_settings()
    from app.label_looker.db import get_scanner_db

    db = get_scanner_db()
    scan_coll = db[s.coll_scan_analysis]
    oid = ObjectId(str(scan_id)) if ObjectId.is_valid(str(scan_id)) else None
    if oid is None:
        raise ScannerApiError(400, "Invalid scanId")

    fields: dict[str, Any] = {"updatedAt": datetime.now()}
    if rating is not None:
        fields["rating"] = rating
    if feedback is not None:
        fields["feedback"] = feedback
    res = await scan_coll.update_one({"_id": oid}, {"$set": fields})
    if res.matched_count == 0:
        raise ScannerApiError(404, "Scan not found")
