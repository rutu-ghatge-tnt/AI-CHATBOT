"""
INCI Cost Lookup Utility (MongoDB Version)
==========================================

Loads ingredient costs from MongoDB instead of Excel file.
Provides better performance and integration with existing data.

Usage:
    from app.ai_ingredient_intelligence.utils.inci_cost_lookup_mongo import lookup_cost_by_inci
    
    cost_data = await lookup_cost_by_inci("Niacinamide")
"""

from typing import Optional, Dict, List
import re
from app.ai_ingredient_intelligence.db.collections import db

# Collection for ingredient costs
ingredient_costs_col = db["ingredient_costs"]


def normalize_inci_name(inci: str) -> str:
    """Normalize INCI name for matching (lowercase, remove extra spaces)."""
    if not inci or not isinstance(inci, str):
        return ""
    return re.sub(r'\s+', ' ', inci.strip().lower())


async def lookup_cost_by_inci(inci_name: str, exact_match: bool = False) -> Optional[Dict]:
    """
    Look up cost for an ingredient by INCI name from MongoDB.
    
    Args:
        inci_name: The INCI name to search for
        exact_match: If True, requires exact match. If False, does fuzzy matching.
    
    Returns:
        Dict with keys: 'inci_name', 'branded_ingredient', 'avg_cost', 'primary_supplier'
        or None if not found
    """
    if not inci_name or not inci_name.strip():
        return None
    
    try:
        inci_normalized = normalize_inci_name(inci_name)
        
        if exact_match:
            # Exact match
            doc = await ingredient_costs_col.find_one(
                {"inci_name_normalized": inci_normalized}
            )
        else:
            # Fuzzy match - try exact first, then regex
            doc = await ingredient_costs_col.find_one(
                {"inci_name_normalized": inci_normalized}
            )
            
            if not doc:
                # Try regex match
                doc = await ingredient_costs_col.find_one(
                    {"inci_name_normalized": {"$regex": inci_normalized, "$options": "i"}}
                )
        
        if not doc:
            return None
        
        return {
            'inci_name': doc.get('inci_name', ''),
            'branded_ingredient': doc.get('branded_ingredient', ''),
            'avg_cost': float(doc.get('avg_cost', 0)),
            'primary_supplier': doc.get('primary_supplier', '')
        }
    
    except Exception as e:
        print(f"Error looking up cost for {inci_name}: {e}")
        return None


async def lookup_multiple_costs(inci_names: List[str]) -> Dict[str, Optional[Dict]]:
    """
    Look up costs for multiple INCI names at once (batch query).
    
    Returns:
        Dict mapping INCI name to cost data (or None if not found)
    """
    if not inci_names:
        return {}
    
    results = {}
    normalized_names = {normalize_inci_name(name): name for name in inci_names}
    
    try:
        # Batch query
        cursor = ingredient_costs_col.find(
            {"inci_name_normalized": {"$in": list(normalized_names.keys())}}
        )
        
        found_docs = {}
        async for doc in cursor:
            inci_norm = doc.get('inci_name_normalized', '')
            if inci_norm in normalized_names:
                original_name = normalized_names[inci_norm]
                found_docs[original_name] = {
                    'inci_name': doc.get('inci_name', ''),
                    'branded_ingredient': doc.get('branded_ingredient', ''),
                    'avg_cost': float(doc.get('avg_cost', 0)),
                    'primary_supplier': doc.get('primary_supplier', '')
                }
        
        # Map results
        for inci in inci_names:
            results[inci] = found_docs.get(inci)
        
        return results
    
    except Exception as e:
        print(f"Error in batch lookup: {e}")
        # Fallback to individual lookups
        for inci in inci_names:
            results[inci] = await lookup_cost_by_inci(inci)
        return results


async def get_cost_reference_table_from_mongo(limit: int = 100) -> str:
    """
    Generate a cost reference table string from MongoDB data
    to be included in AI prompts.
    
    Args:
        limit: Maximum number of ingredients to include
    
    Returns:
        Formatted string with ingredient costs from MongoDB
    """
    try:
        # Get ingredients sorted by cost
        cursor = ingredient_costs_col.find({}).sort("avg_cost", 1).limit(limit)
        
        lines = [
            "## INGREDIENT COST REFERENCE FROM DATABASE (MongoDB)",
            "",
            "The following costs are from the ingredient cost database.",
            "Use these EXACT costs when available. For ingredients not in this list, use the reference anchors below.",
            "",
            "| INCI Name | Avg Cost (₹/kg) | Branded Ingredient | Primary Supplier |",
            "|-----------|----------------|-------------------|------------------|"
        ]
        
        count = 0
        async for doc in cursor:
            inci = doc.get('inci_name', '')
            avg = doc.get('avg_cost', 0)
            branded = doc.get('branded_ingredient', '')
            supplier = doc.get('primary_supplier', '')
            
            lines.append(f"| {inci} | ₹{avg:.2f} | {branded} | {supplier} |")
            count += 1
        
        total_count = await ingredient_costs_col.count_documents({})
        
        lines.append("")
        lines.append(f"Total ingredients in database: {total_count}")
        lines.append(f"Showing top {count} by cost")
        lines.append("")
        lines.append("**IMPORTANT:** When an ingredient is found in this database, use the exact cost from the database.")
        lines.append("Only use the reference anchors below for ingredients NOT in this database.")
        
        return "\n".join(lines)
    
    except Exception as e:
        print(f"Error generating cost reference table: {e}")
        return ""


async def get_average_cost_by_category() -> Dict[str, float]:
    """
    Get average costs grouped by ingredient category (if available).
    Useful for estimating costs for unknown ingredients.
    """
    # This would require additional categorization logic
    # For now, return empty dict
    return {}


async def update_cost(inci_name: str, new_cost: float, source: str = "manual") -> bool:
    """
    Update cost for an ingredient.
    
    Args:
        inci_name: INCI name
        new_cost: New cost in ₹/kg
        source: Source of the update (e.g., "manual", "distributor", "excel")
    
    Returns:
        True if updated, False if not found
    """
    from datetime import datetime
    
    inci_normalized = normalize_inci_name(inci_name)
    
    result = await ingredient_costs_col.update_one(
        {"inci_name_normalized": inci_normalized},
        {
            "$set": {
                "avg_cost": new_cost,
                "updated_at": datetime.utcnow(),
                "last_update_source": source
            }
        }
    )
    
    return result.modified_count > 0

