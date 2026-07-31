from __future__ import annotations

from typing import Any

from anthropic import AsyncAnthropic

from app.label_looker.core.constants import DEFAULT_LANGUAGE
from app.label_looker.core.errors import ScannerApiError
from app.label_looker.core.settings import get_label_looker_settings
from app.label_looker.modules.product_analysis.analysis_service_impl import (
    _apply_db_key_ingredients,
    _best_main_benefit,
    _best_product_type,
    _ensure_profile_match_insights,
    _fetch_product_by_id,
    _ingredients_from_product,
    _key_ingredients_from_product,
    _maybe_attach_ll2_tile_content,
    _normalize_analysis_payload,
    _normalize_product_ref,
)
from app.label_looker.prompts_controller import ingredient_analysis_user_message
from app.label_looker.services.active_ingredient_dossiers import (
    format_active_dossiers_for_prompt,
    resolve_active_ingredient_dossiers,
)
from app.label_looker.services.analysis_cache_guards import (
    product_updated_at,
    sanitize_ingredient_categorization,
)
from app.label_looker.services.product_analysis_store import (
    find_product_analysis,
    upsert_product_analysis,
)
from app.label_looker.text_extract import extract_first_json_object
from motor.motor_asyncio import AsyncIOMotorCollection


async def resolve_product_ingredient_lists(
    *,
    product: dict[str, Any] | None,
    branded_ingredients_coll: AsyncIOMotorCollection,
    ingredient_coll: AsyncIOMotorCollection,
) -> tuple[list[str], list[str]]:
    ing_list = await _ingredients_from_product(
        product=product,
        branded_ingredients_coll=branded_ingredients_coll,
        ingredient_coll=ingredient_coll,
    )
    key_list = await _key_ingredients_from_product(
        product=product,
        branded_ingredients_coll=branded_ingredients_coll,
        ingredient_coll=ingredient_coll,
    )
    return ing_list, key_list


async def run_claude_product_analysis(
    *,
    ing_list: list[str],
    product: dict[str, Any] | None,
    db_key_ingredients: list[str],
    specific_type: str | None,
    main_benefit: str | None,
    language: str = DEFAULT_LANGUAGE,
    personalized: bool = False,
    personalization_context: str | None = None,
    body: dict[str, Any] | None = None,
    details_doc: dict[str, Any] | None = None,
    client: AsyncAnthropic | None = None,
    anthropic_api_key: str | None = None,
    anthropic_model: str | None = None,
) -> tuple[dict[str, Any], list[str]]:
    if not ing_list:
        raise ScannerApiError(400, "Product has no resolvable INCI ingredients in catalog")

    s = get_label_looker_settings()
    api_key = anthropic_api_key or s.anthropic_api_key
    model = anthropic_model or s.anthropic_model
    cl = client or AsyncAnthropic(api_key=api_key)

    if not specific_type and product:
        specific_type = _best_product_type(product)
    if not main_benefit and product:
        main_benefit = _best_main_benefit(product)

    active_dossiers = await resolve_active_ingredient_dossiers(
        ingredient_names=[str(x) for x in ing_list],
        product=product,
    )
    active_dossiers_text = format_active_dossiers_for_prompt(active_dossiers)

    user_msg = ingredient_analysis_user_message(
        ingredients_text="\n".join(ing_list),
        specific_type=specific_type,
        main_benefit=main_benefit,
        langauge=str(language),
        personalization_context=personalization_context if personalized else None,
        active_dossiers_text=active_dossiers_text or None,
    )
    msg = await cl.messages.create(
        model=model,
        max_tokens=8192,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = "".join(getattr(b, "text", "") for b in msg.content)
    parsed = extract_first_json_object(raw)
    analytic, ing_out = _normalize_analysis_payload(parsed, ing_list)
    resolved_ings = [str(x) for x in ing_out] if isinstance(ing_out, list) else [str(x) for x in ing_list]
    analytic, _ = sanitize_ingredient_categorization(analytic, resolved_ings)
    analytic = _apply_db_key_ingredients(analytic, db_key_ingredients)
    analytic = _ensure_profile_match_insights(analytic, personalized=personalized)
    if personalized and body is not None:
        analytic = await _maybe_attach_ll2_tile_content(
            analytic=analytic,
            body=body,
            details_doc=details_doc,
            product=product,
            client=cl,
            anthropic_model=model,
        )
    return analytic, resolved_ings


async def analyze_catalog_product(
    *,
    product: dict[str, Any],
    products_coll: AsyncIOMotorCollection,
    branded_ingredients_coll: AsyncIOMotorCollection,
    ingredient_coll: AsyncIOMotorCollection,
    product_analysis_coll: AsyncIOMotorCollection,
    force: bool = False,
    source: str = "batch",
) -> dict[str, Any]:
    """
    Analyze one catalog product and persist to product_analyses.
    Skips when a successful analysis already exists unless force=True.
    """
    product_ref = product.get("_id")
    if product_ref is None:
        raise ScannerApiError(400, "Product document missing _id")

    ing_list, db_key_ingredients = await resolve_product_ingredient_lists(
        product=product,
        branded_ingredients_coll=branded_ingredients_coll,
        ingredient_coll=ingredient_coll,
    )

    if not force:
        existing = await find_product_analysis(
            coll=product_analysis_coll,
            product_ref=product_ref,
            product_updated=product_updated_at(product),
        )
        if existing is not None:
            return {
                "productId": str(product_ref),
                "skipped": True,
                "reason": "already_analyzed",
                "cacheType": "product_catalog",
            }

    if not ing_list:
        await upsert_product_analysis(
            coll=product_analysis_coll,
            product_ref=product_ref,
            product=product,
            analytic_detail={},
            ingredients=[],
            source=source,
            error="no_resolvable_ingredients",
        )
        return {
            "productId": str(product_ref),
            "skipped": True,
            "reason": "no_resolvable_ingredients",
        }

    s = get_label_looker_settings()
    analytic, ing_out = await run_claude_product_analysis(
        ing_list=ing_list,
        product=product,
        db_key_ingredients=db_key_ingredients,
        specific_type=_best_product_type(product),
        main_benefit=_best_main_benefit(product),
        personalized=False,
    )
    await upsert_product_analysis(
        coll=product_analysis_coll,
        product_ref=product_ref,
        product=product,
        analytic_detail=analytic,
        ingredients=ing_out,
        specific_type=_best_product_type(product),
        main_benefit=_best_main_benefit(product),
        source=source,
        model=s.anthropic_model,
    )
    return {
        "productId": str(product_ref),
        "skipped": False,
        "ingredientCount": len(ing_out),
        "cacheType": "product_catalog",
    }


async def load_product_analysis_for_api(
    *,
    product_ref: Any,
    product_analysis_coll: AsyncIOMotorCollection,
) -> dict[str, Any] | None:
    return await find_product_analysis(coll=product_analysis_coll, product_ref=product_ref)


async def fetch_product_doc(
    *,
    products_coll: AsyncIOMotorCollection,
    product_id: Any,
) -> dict[str, Any] | None:
    return await _fetch_product_by_id(products_coll=products_coll, product_id=_normalize_product_ref(product_id))
