"""
Market Trends Query Module for Make A Wish
==========================================

This module provides functions to query the market_trends_storage collection
based on hero ingredients, benefits, product types, and other properties from
the Make A Wish flow.

All queries use the batch-fetched data stored monthly.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import re
from collections import defaultdict

from app.ai_ingredient_intelligence.db.collections import market_trends_storage_col
from app.ai_ingredient_intelligence.serpapi_batch_config.serpapi_batch_config import load_config


# Cache for config (loaded once)
_config_cache: Optional[Dict[str, Any]] = None
_ingredient_map_cache: Optional[Dict[str, str]] = None  # common_name -> ingredient_tag
_benefit_map_cache: Optional[Dict[str, str]] = None  # benefit name -> benefit_tag
_format_map_cache: Optional[Dict[str, str]] = None  # format name -> format_id


def _load_config() -> Dict[str, Any]:
    """Load and cache config"""
    global _config_cache
    if _config_cache is None:
        _config_cache = load_config()
    return _config_cache


def _build_ingredient_map() -> Dict[str, str]:
    """Build map from common_name to ingredient_tag"""
    global _ingredient_map_cache
    if _ingredient_map_cache is not None:
        return _ingredient_map_cache
    
    config = _load_config()
    ingredient_map = {}
    
    # Process skincare ingredients
    skincare = config.get("ingredients", {}).get("skincare", {})
    for category, ingredient_list in skincare.items():
        if isinstance(ingredient_list, list):
            for ingredient in ingredient_list:
                if isinstance(ingredient, dict):
                    common_name = ingredient.get("common_name", "")
                    ingredient_id = ingredient.get("id", "")
                    if common_name and ingredient_id:
                        ingredient_map[common_name.lower()] = ingredient_id
                        # Also map search terms
                        for search_term in ingredient.get("search_terms", []):
                            ingredient_map[search_term.lower()] = ingredient_id
    
    # Process haircare ingredients
    haircare = config.get("ingredients", {}).get("haircare", {})
    for category, ingredient_list in haircare.items():
        if isinstance(ingredient_list, list):
            for ingredient in ingredient_list:
                if isinstance(ingredient, dict):
                    common_name = ingredient.get("common_name", "")
                    ingredient_id = ingredient.get("id", "")
                    if common_name and ingredient_id:
                        ingredient_map[common_name.lower()] = ingredient_id
                        for search_term in ingredient.get("search_terms", []):
                            ingredient_map[search_term.lower()] = ingredient_id
    
    _ingredient_map_cache = ingredient_map
    return ingredient_map


def _build_benefit_map() -> Dict[str, str]:
    """Build map from benefit name to benefit_tag"""
    global _benefit_map_cache
    if _benefit_map_cache is not None:
        return _benefit_map_cache
    
    config = _load_config()
    benefit_map = {}
    
    # Process skincare benefits
    skincare_benefits = config.get("benefits", {}).get("skincare", [])
    for benefit in skincare_benefits:
        if isinstance(benefit, dict):
            benefit_id = benefit.get("id", "")
            search_terms = benefit.get("search_terms", [])
            for term in search_terms:
                benefit_map[term.lower()] = benefit_id
            benefit_map[benefit_id.lower()] = benefit_id
    
    # Process haircare benefits
    haircare_benefits = config.get("benefits", {}).get("haircare", [])
    for benefit in haircare_benefits:
        if isinstance(benefit, dict):
            benefit_id = benefit.get("id", "")
            search_terms = benefit.get("search_terms", [])
            for term in search_terms:
                benefit_map[term.lower()] = benefit_id
            benefit_map[benefit_id.lower()] = benefit_id
    
    _benefit_map_cache = benefit_map
    return benefit_map


def _build_format_map() -> Dict[str, str]:
    """Build map from format name to format_id"""
    global _format_map_cache
    if _format_map_cache is not None:
        return _format_map_cache
    
    config = _load_config()
    format_map = {}
    
    # Process skincare formats
    skincare_formats = config.get("product_formats", {}).get("skincare", [])
    for format_info in skincare_formats:
        if isinstance(format_info, dict):
            format_id = format_info.get("id", "")
            search_terms = format_info.get("search_terms", [])
            for term in search_terms:
                format_map[term.lower()] = format_id
            format_map[format_id.lower()] = format_id
    
    # Process haircare formats
    haircare_formats = config.get("product_formats", {}).get("haircare", [])
    for format_info in haircare_formats:
        if isinstance(format_info, dict):
            format_id = format_info.get("id", "")
            search_terms = format_info.get("search_terms", [])
            for term in search_terms:
                format_map[term.lower()] = format_id
            format_map[format_id.lower()] = format_id
    
    _format_map_cache = format_map
    return format_map


def normalize_ingredient_name(ingredient_name: str) -> Optional[str]:
    """
    Normalize ingredient name to ingredient_tag.
    
    Examples:
    - "Vitamin C" -> "vitamin_c"
    - "Niacinamide" -> "niacinamide"
    - "Vit C" -> "vitamin_c"
    """
    if not ingredient_name:
        return None
    
    ingredient_map = _build_ingredient_map()
    normalized = ingredient_name.lower().strip()
    
    # Direct lookup
    if normalized in ingredient_map:
        return ingredient_map[normalized]
    
    # Try fuzzy matching (simple word matching)
    for key, value in ingredient_map.items():
        if normalized in key or key in normalized:
            return value
    
    # Try removing common suffixes
    for suffix in [" serum", " cream", " for skin", " extract"]:
        if normalized.endswith(suffix):
            base = normalized[:-len(suffix)].strip()
            if base in ingredient_map:
                return ingredient_map[base]
    
    return None


def normalize_benefit(benefit_name: str) -> Optional[str]:
    """Normalize benefit name to benefit_tag"""
    if not benefit_name:
        return None
    
    benefit_map = _build_benefit_map()
    normalized = benefit_name.lower().strip()
    
    # Direct lookup
    if normalized in benefit_map:
        return benefit_map[normalized]
    
    # Try fuzzy matching
    for key, value in benefit_map.items():
        if normalized in key or key in normalized:
            return value
    
    return None


def normalize_product_type(product_type: str) -> Optional[str]:
    """Normalize product type to format_id"""
    if not product_type:
        return None
    
    format_map = _build_format_map()
    normalized = product_type.lower().strip()
    
    # Direct lookup
    if normalized in format_map:
        return format_map[normalized]
    
    # Try fuzzy matching
    for key, value in format_map.items():
        if normalized in key or key in normalized:
            return value
    
    return None


async def get_level_1_ingredient_trends(
    hero_ingredients: List[str],
    product_type: str,
    category: str = "skincare",
    max_age_days: int = 35
) -> Dict[str, Dict[str, Any]]:
    """
    Get Level 1 ingredient trend data for hero ingredients.
    
    Args:
        hero_ingredients: List of ingredient names (e.g., ["Vitamin C", "Niacinamide"])
        product_type: Product format (e.g., "serum", "cream")
        category: "skincare" or "haircare"
        max_age_days: Maximum age of data in days
    
    Returns:
        Dict mapping ingredient name to trend data:
        {
            "Vitamin C": {
                "trend_data": {...full document...},
                "query_text": "Vitamin C serum",
                "match_type": "exact",
                "confidence": "high"
            }
        }
    """
    cutoff_date = datetime.utcnow() - timedelta(days=max_age_days)
    results = {}
    
    normalized_format = normalize_product_type(product_type)
    
    for ingredient_name in hero_ingredients:
        if not ingredient_name:
            continue
        
        normalized_ingredient = normalize_ingredient_name(ingredient_name)
        
        # Try exact match first
        query = {
            "query_level": "ingredient",
            "category": category,
            "fetch_source": "batch",
            "is_active": True,
            "fetched_at": {"$gte": cutoff_date}
        }
        
        if normalized_ingredient:
            query["ingredient_tag"] = normalized_ingredient
        else:
            # Fallback: search by query_text
            query["query_text"] = {"$regex": re.escape(ingredient_name.lower()), "$options": "i"}
        
        if normalized_format:
            query["product_format"] = normalized_format
        
        # Try exact match
        doc = await market_trends_storage_col.find_one(query, sort=[("fetched_at", -1)])
        
        if not doc and normalized_ingredient:
            # Fallback: try without format
            query_fallback = {
                "query_level": "ingredient",
                "category": category,
                "ingredient_tag": normalized_ingredient,
                "fetch_source": "batch",
                "is_active": True,
                "fetched_at": {"$gte": cutoff_date}
            }
            doc = await market_trends_storage_col.find_one(query_fallback, sort=[("fetched_at", -1)])
        
        if not doc:
            # Last resort: fuzzy match on query_text
            fuzzy_query = {
                "query_level": "ingredient",
                "category": category,
                "query_text": {"$regex": re.escape(ingredient_name.lower()), "$options": "i"},
                "fetch_source": "batch",
                "is_active": True,
                "fetched_at": {"$gte": cutoff_date}
            }
            doc = await market_trends_storage_col.find_one(fuzzy_query, sort=[("fetched_at", -1)])
        
        if doc:
            match_type = "exact" if normalized_ingredient and normalized_format else "fuzzy"
            confidence = "high" if normalized_ingredient else "low"
            
            results[ingredient_name] = {
                "trend_data": doc,
                "query_text": doc.get("query_text", ""),
                "match_type": match_type,
                "confidence": confidence
            }
        else:
            results[ingredient_name] = None
    
    return results


async def get_level_2_competing_approaches(
    benefits: List[str],
    product_type: str,
    category: str = "skincare",
    exclude_ingredients: Optional[List[str]] = None,
    max_results: int = 5,
    max_age_days: int = 35
) -> List[Dict[str, Any]]:
    """
    Get Level 2 competing approaches for the same benefits.
    
    Args:
        benefits: List of benefit names
        product_type: Product format
        category: "skincare" or "haircare"
        exclude_ingredients: List of ingredient_tags to exclude (user's own ingredients)
        max_results: Maximum number of results
        max_age_days: Maximum age of data
    
    Returns:
        List of trend data documents sorted by current_score
    """
    if not benefits:
        return []
    
    cutoff_date = datetime.utcnow() - timedelta(days=max_age_days)
    normalized_format = normalize_product_type(product_type)
    
    # Get benefit tags
    benefit_tags = []
    for benefit in benefits:
        normalized_benefit = normalize_benefit(benefit)
        if normalized_benefit:
            benefit_tags.append(normalized_benefit)
    
    if not benefit_tags:
        return []
    
    # Build query
    query = {
        "$or": [
            {"benefit_tag": {"$in": benefit_tags}},
            {"query_level": "benefit", "category": category}
        ],
        "category": category,
        "fetch_source": "batch",
        "is_active": True,
        "fetched_at": {"$gte": cutoff_date}
    }
    
    if normalized_format:
        query["product_format"] = normalized_format
    
    # Exclude user's ingredients
    if exclude_ingredients:
        exclude_tags = [normalize_ingredient_name(ing) for ing in exclude_ingredients if normalize_ingredient_name(ing)]
        if exclude_tags:
            query["ingredient_tag"] = {"$nin": exclude_tags}
    
    # Also get ingredient-level queries for the same benefits
    cursor = market_trends_storage_col.find(query).sort("current_score", -1).limit(max_results * 2)
    
    results = []
    seen_ingredients = set()
    
    async for doc in cursor:
        ingredient_tag = doc.get("ingredient_tag")
        if ingredient_tag and ingredient_tag not in seen_ingredients:
            seen_ingredients.add(ingredient_tag)
            results.append(doc)
            if len(results) >= max_results:
                break
    
    return results


async def get_level_3_brand_trends(
    hero_ingredients: List[str],
    category: str = "skincare",
    max_results: int = 5,
    max_age_days: int = 35
) -> List[Dict[str, Any]]:
    """
    Get Level 3 brand trends mentioning the ingredients.
    
    Args:
        hero_ingredients: List of ingredient names
        category: "skincare" or "haircare"
        max_results: Maximum number of results
        max_age_days: Maximum age of data
    
    Returns:
        List of brand trend documents
    """
    if not hero_ingredients:
        return []
    
    cutoff_date = datetime.utcnow() - timedelta(days=max_age_days)
    
    # Build regex pattern for ingredient names
    ingredient_patterns = [re.escape(ing.lower()) for ing in hero_ingredients]
    pattern = "|".join(ingredient_patterns)
    
    query = {
        "query_level": "brand",
        "category": category,
        "query_text": {"$regex": pattern, "$options": "i"},
        "fetch_source": "batch",
        "is_active": True,
        "fetched_at": {"$gte": cutoff_date}
    }
    
    cursor = market_trends_storage_col.find(query).sort("current_score", -1).limit(max_results)
    
    results = []
    async for doc in cursor:
        results.append(doc)
    
    return results


async def get_shopping_data(
    hero_ingredients: List[str],
    product_type: str,
    category: str = "skincare",
    max_age_days: int = 35
) -> Optional[Dict[str, Any]]:
    """
    Get shopping data (price ranges, products) for ingredients.
    
    Args:
        hero_ingredients: List of ingredient names
        product_type: Product format
        category: "skincare" or "haircare"
        max_age_days: Maximum age of data
    
    Returns:
        Shopping data dict or None
    """
    if not hero_ingredients:
        return None
    
    cutoff_date = datetime.utcnow() - timedelta(days=max_age_days)
    normalized_format = normalize_product_type(product_type)
    
    # Try to find document with shopping_data
    for ingredient_name in hero_ingredients:
        normalized_ingredient = normalize_ingredient_name(ingredient_name)
        
        query = {
            "query_level": "ingredient",
            "category": category,
            "shopping_data": {"$exists": True, "$ne": None},
            "fetch_source": "batch",
            "is_active": True,
            "fetched_at": {"$gte": cutoff_date}
        }
        
        if normalized_ingredient:
            query["ingredient_tag"] = normalized_ingredient
        
        if normalized_format:
            query["product_format"] = normalized_format
        
        doc = await market_trends_storage_col.find_one(query, sort=[("fetched_at", -1)])
        
        if doc and doc.get("shopping_data"):
            return doc.get("shopping_data")
    
    return None


async def get_comparison_data(
    hero_ingredients: List[str],
    category: str = "skincare",
    max_age_days: int = 35
) -> List[Dict[str, Any]]:
    """
    Get comparison data for multiple ingredients.
    
    Args:
        hero_ingredients: List of ingredient names
        category: "skincare" or "haircare"
        max_age_days: Maximum age of data
    
    Returns:
        List of comparison documents
    """
    if len(hero_ingredients) < 2:
        return []
    
    cutoff_date = datetime.utcnow() - timedelta(days=max_age_days)
    
    # Build regex pattern
    ingredient_patterns = [re.escape(ing.lower()) for ing in hero_ingredients]
    pattern = "|".join(ingredient_patterns)
    
    query = {
        "query_level": "comparison",
        "category": category,
        "query_text": {"$regex": pattern, "$options": "i"},
        "fetch_source": "batch",
        "is_active": True,
        "fetched_at": {"$gte": cutoff_date}
    }
    
    cursor = market_trends_storage_col.find(query).sort("fetched_at", -1).limit(10)
    
    results = []
    async for doc in cursor:
        results.append(doc)
    
    return results


async def get_comprehensive_market_trends(
    hero_ingredients: Optional[List[str]] = None,
    benefits: Optional[List[str]] = None,
    product_type: Optional[str] = None,
    category: str = "skincare",
    max_age_days: int = 35
) -> Dict[str, Any]:
    """
    Main function to fetch comprehensive market trends data for Make A Wish.
    
    This is the primary function to use in the Make A Wish flow.
    
    Args:
        hero_ingredients: List of hero ingredient names (e.g., ["Vitamin C", "Niacinamide"])
        benefits: List of benefits (e.g., ["brightening", "anti-aging"])
        product_type: Product format (e.g., "serum", "cream")
        category: "skincare" or "haircare"
        max_age_days: Maximum age of data in days (default: 35)
    
    Returns:
        {
            "level_1_ingredient_trends": {
                "Vitamin C": {
                    "trend_data": {...full document...},
                    "query_text": "Vitamin C serum",
                    "match_type": "exact",
                    "confidence": "high"
                }
            },
            "level_2_competing_approaches": [...],  # List of alternative approaches
            "level_3_brand_trends": [...],  # Brand data
            "shopping_data": {...},  # Price ranges, products
            "comparison_data": [...],  # Comparison queries
            "insights": {
                "seasonality": {...},
                "competitive_position": {...},
                "rising_query_insights": {...},
                "regional_insights": {...}
            }
        }
    """
    hero_ingredients = hero_ingredients or []
    benefits = benefits or []
    
    result = {
        "level_1_ingredient_trends": {},
        "level_2_competing_approaches": [],
        "level_3_brand_trends": [],
        "shopping_data": None,
        "comparison_data": [],
        "insights": {
            "seasonality": None,
            "competitive_position": None,
            "rising_query_insights": None,
            "regional_insights": None
        }
    }
    
    # Level 1: Ingredient trends
    if hero_ingredients and product_type:
        level_1_data = await get_level_1_ingredient_trends(
            hero_ingredients=hero_ingredients,
            product_type=product_type,
            category=category,
            max_age_days=max_age_days
        )
        result["level_1_ingredient_trends"] = level_1_data
        
        # Extract insights from first ingredient (if available)
        first_ingredient_data = None
        for ing_name, ing_data in level_1_data.items():
            if ing_data and ing_data.get("trend_data"):
                first_ingredient_data = ing_data["trend_data"]
                break
        
        if first_ingredient_data:
            result["insights"]["seasonality"] = first_ingredient_data.get("seasonality")
            result["insights"]["competitive_position"] = first_ingredient_data.get("competitive_position")
            result["insights"]["rising_query_insights"] = first_ingredient_data.get("rising_query_insights")
            result["insights"]["regional_insights"] = first_ingredient_data.get("regional_insights")
    
    # Level 2: Competing approaches
    if benefits and product_type:
        exclude_ingredients = [normalize_ingredient_name(ing) for ing in hero_ingredients if normalize_ingredient_name(ing)]
        level_2_data = await get_level_2_competing_approaches(
            benefits=benefits,
            product_type=product_type,
            category=category,
            exclude_ingredients=hero_ingredients,
            max_results=5,
            max_age_days=max_age_days
        )
        result["level_2_competing_approaches"] = level_2_data
    
    # Level 3: Brand trends
    if hero_ingredients:
        level_3_data = await get_level_3_brand_trends(
            hero_ingredients=hero_ingredients,
            category=category,
            max_results=5,
            max_age_days=max_age_days
        )
        result["level_3_brand_trends"] = level_3_data
    
    # Shopping data
    if hero_ingredients and product_type:
        shopping_data = await get_shopping_data(
            hero_ingredients=hero_ingredients,
            product_type=product_type,
            category=category,
            max_age_days=max_age_days
        )
        result["shopping_data"] = shopping_data
    
    # Comparison data
    if len(hero_ingredients) >= 2:
        comparison_data = await get_comparison_data(
            hero_ingredients=hero_ingredients,
            category=category,
            max_age_days=max_age_days
        )
        result["comparison_data"] = comparison_data
    
    return result

