"""
Market Trends Storage - Retrieve Stored Trend Data
===================================================

Functions to retrieve pre-fetched market trend data from the database
instead of making real-time API calls.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from app.ai_ingredient_intelligence.db.collections import market_trends_storage_col


async def get_stored_trend_data(
    topic: str,
    max_age_days: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """
    Retrieve stored trend data for a topic/ingredient.
    
    Args:
        topic: The topic/ingredient to retrieve data for
        max_age_days: Maximum age of data in days (None = no limit)
        
    Returns:
        Dictionary with trend data if found, None otherwise
    """
    topic_normalized = topic.lower().strip()
    
    query = {"topic_normalized": topic_normalized}
    
    # Add age filter if specified
    if max_age_days:
        cutoff_date = datetime.utcnow() - timedelta(days=max_age_days)
        query["fetched_at"] = {"$gte": cutoff_date}
    
    stored_data = await market_trends_storage_col.find_one(query)
    
    if stored_data:
        return stored_data.get("trend_data")
    
    return None


async def get_stored_trend_data_for_ingredients(
    ingredients: List[str],
    max_age_days: Optional[int] = None
) -> Dict[str, Any]:
    """
    Retrieve stored trend data for multiple ingredients.
    
    Args:
        ingredients: List of ingredient names
        max_age_days: Maximum age of data in days (None = no limit)
        
    Returns:
        Dictionary mapping ingredient names to their trend data:
        {
            "ingredient_name": {
                "analyze": {...},
                "consumer_intent": {...},
                "competitive": {...},
                "regional": {...}
            }
        }
    """
    result = {}
    
    for ingredient in ingredients:
        if not ingredient or not ingredient.strip():
            continue
        
        # Clean ingredient name (remove parentheses and extra text)
        clean_ingredient = ingredient.split("(")[0].strip()
        
        # Try exact match first
        trend_data = await get_stored_trend_data(clean_ingredient, max_age_days)
        
        # If not found, try with "serum" suffix
        if not trend_data:
            trend_data = await get_stored_trend_data(f"{clean_ingredient} serum", max_age_days)
        
        # If still not found, try without common suffixes
        if not trend_data:
            # Remove common suffixes
            base_name = clean_ingredient
            for suffix in [" serum", " for skin", " benefits"]:
                if base_name.endswith(suffix):
                    base_name = base_name[:-len(suffix)].strip()
            
            if base_name != clean_ingredient:
                trend_data = await get_stored_trend_data(base_name, max_age_days)
        
        if trend_data:
            result[ingredient] = trend_data
        else:
            # Store None to indicate no data found
            result[ingredient] = None
    
    return result


async def search_stored_trends(
    query: str,
    max_results: int = 10
) -> List[Dict[str, Any]]:
    """
    Search stored trend data by query (fuzzy match on topic names).
    
    Args:
        query: Search query
        max_results: Maximum number of results
        
    Returns:
        List of matching trend data documents
    """
    query_normalized = query.lower().strip()
    
    # Use regex for partial matching
    import re
    pattern = re.compile(query_normalized, re.IGNORECASE)
    
    cursor = market_trends_storage_col.find({
        "$or": [
            {"topic": pattern},
            {"topic_normalized": {"$regex": query_normalized, "$options": "i"}}
        ]
    }).limit(max_results)
    
    results = []
    async for doc in cursor:
        results.append({
            "topic": doc.get("topic"),
            "topic_normalized": doc.get("topic_normalized"),
            "trend_data": doc.get("trend_data"),
            "fetched_at": doc.get("fetched_at"),
            "updated_at": doc.get("updated_at"),
            "data_version": doc.get("data_version")
        })
    
    return results


async def get_all_stored_topics() -> List[str]:
    """
    Get list of all topics that have stored trend data.
    
    Returns:
        List of topic names
    """
    cursor = market_trends_storage_col.find(
        {},
        {"topic": 1, "_id": 0}
    )
    
    topics = []
    async for doc in cursor:
        topics.append(doc.get("topic"))
    
    return sorted(topics)


async def check_data_freshness(topic: str) -> Optional[Dict[str, Any]]:
    """
    Check how fresh the stored data is for a topic.
    
    Args:
        topic: Topic name
        
    Returns:
        Dictionary with freshness info, or None if not found
    """
    topic_normalized = topic.lower().strip()
    
    stored_data = await market_trends_storage_col.find_one({
        "topic_normalized": topic_normalized
    })
    
    if not stored_data:
        return None
    
    fetched_at = stored_data.get("fetched_at")
    if not fetched_at:
        return None
    
    if isinstance(fetched_at, str):
        fetched_at = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
    
    age = datetime.utcnow() - fetched_at
    age_days = age.days
    age_hours = age.total_seconds() / 3600
    
    return {
        "topic": stored_data.get("topic"),
        "fetched_at": fetched_at.isoformat(),
        "age_days": age_days,
        "age_hours": round(age_hours, 2),
        "is_fresh": age_days < 7,  # Consider fresh if less than 7 days old
        "data_version": stored_data.get("data_version", 1)
    }

