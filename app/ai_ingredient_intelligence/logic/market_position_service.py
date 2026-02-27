"""
Market Position Service for Make A Wish
========================================

Fetches "Your Market Position" (competitor comparison) from the externalproducts
collection using ingredient-based matching. Used by the standalone /market-position
endpoint instead of AI-generated clause search in generate-revised.
"""

from typing import Dict, Any, Optional, List
import re

from app.ai_ingredient_intelligence.db.mongodb import db
from app.ai_ingredient_intelligence.db.collections import inci_col
from app.ai_ingredient_intelligence.utils.inci_parser import parse_inci_string


def _normalize(s: str) -> str:
    """Same normalization as externalproducts/INGREDIENT matching."""
    if not s or not isinstance(s, str):
        return ""
    return re.sub(r"\s+", " ", s.strip()).strip().lower()


async def fetch_market_position_from_external_products(
    hero_ingredients: List[str],
    product_type: Optional[str] = None,
    category: str = "skincare",
    your_product: Optional[Dict[str, Any]] = None,
    max_similar_products: int = 10,
) -> Dict[str, Any]:
    """
    Build competitor comparison (Your Market Position) from externalproducts collection.

    Uses ingredient overlap only (no free-text clause search). Finds products that
    share hero/active ingredients, then returns similarProducts, yourProduct,
    competitivePosition, and advantages.

    Args:
        hero_ingredients: List of hero/active ingredient names from the wish.
        product_type: e.g. serum, cream (optional filter).
        category: skincare or haircare (optional filter).
        your_product: Optional dict with formulaName, cost_per_100g, size, etc. for comparison.
        max_similar_products: Max number of similar products to return (default 10).

    Returns:
        {
            "similar_products": [{"brand", "product", "price", "size", "advantage", ...}],
            "your_product": {...},
            "competitive_position": str,
            "advantages": [{"competitor_brand", "advantage"}]
        }
    """
    external_products_col = db["externalproducts"]
    normalized_input = []
    for ing in hero_ingredients or []:
        if ing and str(ing).strip():
            n = _normalize(str(ing).strip())
            if n:
                normalized_input.append(n)
    if not normalized_input:
        return _empty_market_position(your_product)

    # Optional: treat as actives only (we can skip INCI lookup and use all as "actives" for matching)
    input_actives = normalized_input
    try:
        inci_query = {"inciName_normalized": {"$in": normalized_input}}
        inci_cursor = inci_col.find(inci_query, {"inciName_normalized": 1, "category": 1})
        inci_results = await inci_cursor.to_list(length=None)
        active_set = set()
        for doc in inci_results:
            cat = (doc.get("category") or "").lower()
            if cat == "active":
                active_set.add((doc.get("inciName_normalized") or "").strip().lower())
        if active_set:
            input_actives = [n for n in normalized_input if n in active_set]
        if not input_actives:
            input_actives = normalized_input
    except Exception:
        input_actives = normalized_input

    # Fetch products that have ingredients (same pattern as market_research)
    cursor = external_products_col.find(
        {"ingredients": {"$exists": True, "$ne": None, "$ne": ""}}
    )
    all_products = await cursor.to_list(length=None)

    matched = []
    for product in all_products:
        ing_raw = product.get("ingredients", "")
        if not ing_raw:
            continue
        if isinstance(ing_raw, str):
            product_ing_list = parse_inci_string(ing_raw)
        else:
            product_ing_list = ing_raw
        product_normalized = []
        for i in product_ing_list:
            if i and str(i).strip():
                nn = _normalize(str(i).strip())
                if nn:
                    product_normalized.append(nn)
        overlap = [a for a in input_actives if a in product_normalized]
        if not overlap:
            continue
        match_pct = (len(overlap) / len(input_actives)) * 100 if input_actives else 0
        product_category = (product.get("category") or product.get("subcategory") or "").lower()
        product_type_lower = (product_type or "").lower()
        # Optional category/product_type filter (soft)
        if category and category.lower() not in product_category and "skin" not in product_category and "hair" not in product_category:
            if "lip" not in category.lower() and "lip" not in product_category:
                continue
        if product_type_lower and product_type_lower not in (product.get("productType") or product.get("product_type") or "").lower():
            pass  # don't exclude by product type; external may not have it

        price = product.get("price") or product.get("mrp") or product.get("MRP") or 0
        try:
            price = float(price)
        except (TypeError, ValueError):
            price = 0
        size_str = str(product.get("size") or product.get("weight") or product.get("volume") or "0").strip()
        size_clean = size_str.replace("g", "").replace("ml", "").replace("G", "").replace("ML", "").replace("mL", "").strip()
        try:
            size_val = float(size_clean) if size_clean else 0
        except ValueError:
            size_val = 0
        price_per_g = (price / size_val) if size_val > 0 else 0

        matched.append({
            "brand": product.get("brand") or product.get("brandName") or "Unknown",
            "product": product.get("productName") or product.get("name") or product.get("title") or "Unknown",
            "price": price,
            "size": size_str or "—",
            "pricePerGram": round(price_per_g, 2) if price_per_g else None,
            "match_percentage": round(match_pct, 1),
            "active_ingredients": overlap,
            "note": product.get("description") or product.get("note") or "",
        })

    # Sort by match percentage desc, then by price
    matched.sort(key=lambda x: (-x.get("match_percentage", 0), x.get("price") or 0))
    similar = matched[:max_similar_products]

    your = your_product or {}
    cost_per_100g = your.get("cost_per_100g") or your.get("costPer100g") or 0
    your_size = your.get("size") or your.get("recommended_size") or "30g"
    try:
        cost_per_100g = float(cost_per_100g)
    except (TypeError, ValueError):
        cost_per_100g = 0
    your_size_clean = re.sub(r"[^\d.]", "", your_size)
    try:
        your_size_g = float(your_size_clean) if your_size_clean else 30
    except ValueError:
        your_size_g = 30
    your_cost_per_g = (cost_per_100g / 100) if cost_per_100g else 0

    advantages = []
    for item in similar:
        brand = item.get("brand", "")
        comp_price_per_g = item.get("pricePerGram") or 0
        if your_cost_per_g > 0 and comp_price_per_g > 0:
            diff = comp_price_per_g - your_cost_per_g
            if diff > 2:
                adv = f"₹{diff:.1f}/g lower cost vs competitor"
            elif diff < -2:
                adv = f"Premium positioning (₹{-diff:.1f}/g higher than competitor)"
            else:
                adv = "Competitive pricing with similar actives"
        else:
            adv = "Competitive positioning with quality formulation"
        item["advantage"] = adv
        advantages.append({"competitor_brand": brand, "advantage": adv})

    competitive_position = "Competitive on ingredients and positioning. Data from verified external products."
    if similar:
        competitive_position = f"Based on {len(similar)} similar products from the external products database (ingredient overlap)."

    return {
        "similar_products": similar,
        "your_product": {
            "formula_name": your.get("formula_name") or your.get("formulaName") or "Your formula",
            "cost_per_100g": cost_per_100g,
            "size": your_size,
            "cost_per_g": round(your_cost_per_g, 4) if your_cost_per_g else None,
        },
        "competitive_position": competitive_position,
        "advantages": advantages,
    }


def _empty_market_position(your_product: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    your = your_product or {}
    return {
        "similar_products": [],
        "your_product": {
            "formula_name": your.get("formula_name") or your.get("formulaName") or "Your formula",
            "cost_per_100g": your.get("cost_per_100g") or your.get("costPer100g"),
            "size": your.get("size") or your.get("recommended_size") or "—",
            "cost_per_g": None,
        },
        "competitive_position": "No similar products found in external products database. Add hero ingredients and try again.",
        "advantages": [],
    }
