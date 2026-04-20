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


async def ingredient_analysis(*, body: dict[str, Any]) -> dict[str, Any]:
    scan_id = body.get("scanId")
    if not scan_id:
        raise ScannerApiError(400, "scanId is required")

    s = get_label_looker_settings()
    from app.label_looker.db import get_scanner_db

    db = get_scanner_db()
    scan_coll: AsyncIOMotorCollection = db[s.coll_scan_analysis]

    oid = ObjectId(str(scan_id)) if ObjectId.is_valid(str(scan_id)) else None
    if oid is None:
        raise ScannerApiError(400, "Invalid scanId")

    doc = await scan_coll.find_one({"_id": oid})
    if not doc:
        raise ScannerApiError(404, "Scan not found")

    ingredients = body.get("ingredients")
    if ingredients is None or (isinstance(ingredients, list) and len(ingredients) == 0):
        ingredients = doc.get("extractedIngredients") or []

    specific_type = body.get("specificType")
    main_benefit = body.get("mainBenefit")
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
        return {"scanId": str(scan_id), "analyticDetail": analytic, "ingredients": ing_out}
    except Exception as e:
        await scan_coll.update_one(
            {"_id": oid},
            {"$set": {"ingredientAnalysisError": str(e), "updatedAt": datetime.now()}},
        )
        raise ScannerApiError(500, GENERIC_ANALYSIS_FAIL) from e


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
