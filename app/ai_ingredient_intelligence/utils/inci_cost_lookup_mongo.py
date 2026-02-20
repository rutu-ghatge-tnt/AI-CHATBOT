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


def _estimate_fallback_cost(inci_name: str) -> Optional[Dict]:
    """
    Estimate cost based on ingredient name patterns when MongoDB lookup fails.
    This is a fallback mechanism using common ingredient cost ranges.
    
    ⚠️ IMPORTANT: This function should ONLY be used in non-Claude contexts (tests, utilities).
    For Claude-based flows (make_wish_basic_mode), return None from lookup_cost_by_inci
    and let Claude handle intelligent cost estimation based on ingredient classification.
    
    Claude uses better rates:
    - Indian origin extract (non-hero): ₹5,000/kg
    - Indian origin extract (hero): ₹10,000/kg
    - Imported extract (hero): ₹15,000/kg
    - Peptide (hero): ₹30,000/kg
    - etc.
    
    This Python fallback uses simpler pattern matching and may give less accurate estimates.
    
    Returns:
        Dict with estimated cost or None if cannot estimate
    """
    if not inci_name:
        return None
    
    inci_lower = inci_name.lower()
    
    # Water and solvents
    if any(term in inci_lower for term in ['aqua', 'water']):
        return {
            'inci_name': inci_name,
            'branded_ingredient': '',
            'avg_cost': 1.0,  # ₹1/kg for water
            'primary_supplier': 'Estimated',
            'is_fallback': True,
            'confidence': 'low'
        }
    
    # Humectants
    if any(term in inci_lower for term in ['glycerin', 'glycerol', 'propanediol', 'butylene glycol']):
        return {
            'inci_name': inci_name,
            'branded_ingredient': '',
            'avg_cost': 120.0,  # ₹120/kg average for humectants
            'primary_supplier': 'Estimated',
            'is_fallback': True,
            'confidence': 'medium'
        }
    
    # Panthenol
    if 'panthenol' in inci_lower:
        return {
            'inci_name': inci_name,
            'branded_ingredient': '',
            'avg_cost': 1500.0,  # ₹1500/kg for panthenol
            'primary_supplier': 'Estimated',
            'is_fallback': True,
            'confidence': 'medium'
        }
    
    # Hyaluronic Acid / Sodium Hyaluronate (varies by MW)
    if any(term in inci_lower for term in ['hyaluronate', 'hyaluronic']):
        if 'low' in inci_lower or 'low mw' in inci_lower:
            return {
                'inci_name': inci_name,
                'branded_ingredient': '',
                'avg_cost': 25000.0,  # ₹25000/kg for low MW HA
                'primary_supplier': 'Estimated',
                'is_fallback': True,
                'confidence': 'low'
            }
        else:
            return {
                'inci_name': inci_name,
                'branded_ingredient': '',
                'avg_cost': 15000.0,  # ₹15000/kg for standard HA
                'primary_supplier': 'Estimated',
                'is_fallback': True,
                'confidence': 'medium'
            }
    
    # Polyglutamic Acid
    if 'polyglutamic' in inci_lower:
        return {
            'inci_name': inci_name,
            'branded_ingredient': '',
            'avg_cost': 20000.0,  # ₹20000/kg for biotech ingredient
            'primary_supplier': 'Estimated',
            'is_fallback': True,
            'confidence': 'low'
        }
    
    # Tremella / Mushroom extracts
    if any(term in inci_lower for term in ['tremella', 'mushroom', 'fuciformis']):
        return {
            'inci_name': inci_name,
            'branded_ingredient': '',
            'avg_cost': 10000.0,  # ₹10000/kg for plant extract
            'primary_supplier': 'Estimated',
            'is_fallback': True,
            'confidence': 'low'
        }
    
    # Beta-Glucan
    if 'beta-glucan' in inci_lower or 'glucan' in inci_lower:
        return {
            'inci_name': inci_name,
            'branded_ingredient': '',
            'avg_cost': 10000.0,  # ₹10000/kg for plant extract
            'primary_supplier': 'Estimated',
            'is_fallback': True,
            'confidence': 'low'
        }
    
    # Allantoin
    if 'allantoin' in inci_lower:
        return {
            'inci_name': inci_name,
            'branded_ingredient': '',
            'avg_cost': 800.0,  # ₹800/kg for allantoin
            'primary_supplier': 'Estimated',
            'is_fallback': True,
            'confidence': 'medium'
        }
    
    # Adenosine
    if 'adenosine' in inci_lower:
        return {
            'inci_name': inci_name,
            'branded_ingredient': '',
            'avg_cost': 20000.0,  # ₹20000/kg for biotech ingredient
            'primary_supplier': 'Estimated',
            'is_fallback': True,
            'confidence': 'low'
        }
    
    # Thickeners / Gelling agents
    if any(term in inci_lower for term in ['hydroxyethylcellulose', 'carbomer', 'xanthan', 'gum']):
        if 'xanthan' in inci_lower:
            return {
                'inci_name': inci_name,
                'branded_ingredient': '',
                'avg_cost': 800.0,  # ₹800/kg for xanthan gum
                'primary_supplier': 'Estimated',
                'is_fallback': True,
                'confidence': 'medium'
            }
        else:
            return {
                'inci_name': inci_name,
                'branded_ingredient': '',
                'avg_cost': 600.0,  # ₹600/kg for other thickeners
                'primary_supplier': 'Estimated',
                'is_fallback': True,
                'confidence': 'medium'
            }
    
    # Common actives - Niacinamide, Vitamin C derivatives
    if any(term in inci_lower for term in ['niacinamide', 'nicotinamide']):
        return {
            'inci_name': inci_name,
            'branded_ingredient': '',
            'avg_cost': 1200.0,  # ₹1200/kg for niacinamide
            'primary_supplier': 'Estimated',
            'is_fallback': True,
            'confidence': 'medium'
        }
    
    if any(term in inci_lower for term in ['ascorbic', 'vitamin c', 'ascorbyl']):
        return {
            'inci_name': inci_name,
            'branded_ingredient': '',
            'avg_cost': 1500.0,  # ₹1500/kg for vitamin C
            'primary_supplier': 'Estimated',
            'is_fallback': True,
            'confidence': 'medium'
        }
    
    # Retinol and derivatives
    if any(term in inci_lower for term in ['retinol', 'retinyl', 'retinoid']):
        return {
            'inci_name': inci_name,
            'branded_ingredient': '',
            'avg_cost': 20000.0,  # ₹20000/kg for retinol
            'primary_supplier': 'Estimated',
            'is_fallback': True,
            'confidence': 'low'
        }
    
    # Peptides
    if any(term in inci_lower for term in ['peptide', 'palmitoyl', 'matrixyl', 'argireline']):
        return {
            'inci_name': inci_name,
            'branded_ingredient': '',
            'avg_cost': 30000.0,  # ₹30000/kg for peptides
            'primary_supplier': 'Estimated',
            'is_fallback': True,
            'confidence': 'low'
        }
    
    # Preservatives
    if any(term in inci_lower for term in ['phenoxyethanol', 'paraben', 'sodium benzoate', 'potassium sorbate']):
        return {
            'inci_name': inci_name,
            'branded_ingredient': '',
            'avg_cost': 800.0,  # ₹800/kg for preservatives
            'primary_supplier': 'Estimated',
            'is_fallback': True,
            'confidence': 'medium'
        }
    
    # Emulsifiers
    if any(term in inci_lower for term in ['polysorbate', 'cetearyl', 'cetyl', 'emulsifier']):
        return {
            'inci_name': inci_name,
            'branded_ingredient': '',
            'avg_cost': 400.0,  # ₹400/kg for emulsifiers
            'primary_supplier': 'Estimated',
            'is_fallback': True,
            'confidence': 'low'
        }
    
    # Oils and butters
    if any(term in inci_lower for term in ['oil', 'butter', 'squalane', 'jojoba', 'argan']):
        return {
            'inci_name': inci_name,
            'branded_ingredient': '',
            'avg_cost': 2000.0,  # ₹2000/kg for oils
            'primary_supplier': 'Estimated',
            'is_fallback': True,
            'confidence': 'low'
        }
    
    # General plant extracts (catch-all for extracts not matching specific patterns)
    # This should come before the default fallback to catch ingredients like "Rosmarinus Officinalis Leaf Extract"
    if 'extract' in inci_lower:
        return {
            'inci_name': inci_name,
            'branded_ingredient': '',
            'avg_cost': 5000.0,  # ₹5000/kg for Indian origin extract (non-hero) - matches Claude prompt
            'primary_supplier': 'Estimated',
            'is_fallback': True,
            'confidence': 'low'
        }
    
    # Fragrance / Parfum
    if any(term in inci_lower for term in ['parfum', 'fragrance', 'perfume']):
        return {
            'inci_name': inci_name,
            'branded_ingredient': '',
            'avg_cost': 1500.0,  # ₹1500/kg for fragrance (more realistic than ₹1000)
            'primary_supplier': 'Estimated',
            'is_fallback': True,
            'confidence': 'low'
        }
    
    # Try Excel fallback if available
    try:
        from app.ai_ingredient_intelligence.utils.inci_cost_lookup import lookup_cost_by_inci as excel_lookup
        excel_result = excel_lookup(inci_name, exact_match=False)
        if excel_result:
            excel_result['is_fallback'] = True
            excel_result['fallback_source'] = 'excel'
            return excel_result
    except Exception:
        pass  # Excel not available, continue
    
    # Default fallback - generic estimate
    return {
        'inci_name': inci_name,
        'branded_ingredient': '',
        'avg_cost': 1000.0,  # ₹1000/kg default
        'primary_supplier': 'Estimated',
        'is_fallback': True,
        'confidence': 'very_low'
    }


async def lookup_cost_by_inci(inci_name: str, exact_match: bool = False, use_fallback: bool = True) -> Optional[Dict]:
    """
    Look up cost for an ingredient by INCI name from MongoDB.
    
    PRIMARY SOURCE: MongoDB ingredient_costs collection (4200+ ingredients)
    FALLBACK: Only use Python fallback if use_fallback=True (for non-Claude contexts like tests)
    
    IMPORTANT: For make_wish_basic_mode, Claude handles cost estimation when MongoDB fails.
    The Python fallback should NOT be used in Claude-based flows - Claude uses intelligent
    classification-based rates (₹5,000-30,000/kg) instead of hardcoded ₹1000 defaults.
    
    Args:
        inci_name: The INCI name to search for
        exact_match: If True, requires exact match. If False, does fuzzy matching.
        use_fallback: If True, use Python fallback estimation when MongoDB fails.
                     If False, return None and let Claude handle it (recommended for basic mode)
    
    Returns:
        Dict with keys: 'inci_name', 'branded_ingredient', 'avg_cost', 'primary_supplier'
        May include 'is_fallback', 'confidence', 'fallback_source' if fallback was used
        or None if not found and fallback disabled
    """
    if not inci_name or not inci_name.strip():
        return None
    
    try:
        inci_normalized = normalize_inci_name(inci_name)
        
        # SPECIAL HANDLING: For water/aqua, prioritize generic water records (₹1-2/kg) over expensive branded ingredients
        # Check if this is a pure water/aqua search (exact match or starts with water/aqua)
        is_water_aqua = (inci_normalized == 'aqua' or inci_normalized == 'water' or 
                        inci_normalized.startswith('water ') or inci_normalized.startswith('aqua '))
        
        if exact_match:
            # Exact match
            if is_water_aqua:
                # For water/aqua, first try to find the generic WATER record
                doc = await ingredient_costs_col.find_one(
                    {"branded_ingredient": "WATER"}
                )
                if not doc:
                    # Fall back to exact match
                    doc = await ingredient_costs_col.find_one(
                        {"inci_name_normalized": inci_normalized}
                    )
            else:
                doc = await ingredient_costs_col.find_one(
                    {"inci_name_normalized": inci_normalized}
                )
        else:
            # Fuzzy match - try exact first, then regex
            if is_water_aqua:
                # For water/aqua, prioritize generic WATER record (₹1/kg) or records with cost <= ₹5/kg
                # This ensures we get the ₹1/kg WATER record instead of expensive branded aqua
                doc = await ingredient_costs_col.find_one(
                    {"branded_ingredient": "WATER"}
                )
                if not doc:
                    # Try to find any water/aqua record with reasonable cost (<= ₹5/kg)
                    doc = await ingredient_costs_col.find_one(
                        {
                            "$or": [
                                {"inci_name_normalized": inci_normalized, "avg_cost": {"$lte": 5}},
                                {"inci_name_normalized": {"$regex": "^(water|aqua)", "$options": "i"}, "avg_cost": {"$lte": 5}}
                            ]
                        },
                        sort=[("avg_cost", 1)]  # Sort by cost ascending to get cheapest first
                    )
                # If still not found, fall back to regular search
                if not doc:
                    doc = await ingredient_costs_col.find_one(
                        {"inci_name_normalized": inci_normalized}
                    )
            else:
                doc = await ingredient_costs_col.find_one(
                    {"inci_name_normalized": inci_normalized}
                )
            
            if not doc:
                # Try regex match
                if is_water_aqua:
                    # For water/aqua, prioritize cheap records
                    doc = await ingredient_costs_col.find_one(
                        {"branded_ingredient": "WATER"}
                    )
                    if not doc:
                        doc = await ingredient_costs_col.find_one(
                            {
                                "$or": [
                                    {"inci_name_normalized": {"$regex": inci_normalized, "$options": "i"}, "avg_cost": {"$lte": 5}},
                                    {"inci_name_normalized": {"$regex": "^(water|aqua)", "$options": "i"}, "avg_cost": {"$lte": 5}}
                                ]
                            },
                            sort=[("avg_cost", 1)]
                        )
                    if not doc:
                        doc = await ingredient_costs_col.find_one(
                            {"inci_name_normalized": {"$regex": inci_normalized, "$options": "i"}}
                        )
                else:
                    doc = await ingredient_costs_col.find_one(
                        {"inci_name_normalized": {"$regex": inci_normalized, "$options": "i"}}
                    )
        
        if doc:
            base_cost = float(doc.get('avg_cost', 0))
            
            # VALIDATION: For water/aqua, if we found an expensive record (>₹5/kg), warn and try to find cheaper alternative
            if is_water_aqua and base_cost > 5:
                print(f"[WARNING] Found expensive water/aqua record: {doc.get('branded_ingredient', 'N/A')} at ₹{base_cost:.2f}/kg")
                print(f"   Looking for cheaper water alternative (₹1-5/kg)...")
                # Try to find the generic WATER record or any cheaper water
                cheap_water = await ingredient_costs_col.find_one(
                    {
                        "$or": [
                            {"branded_ingredient": "WATER"},
                            {"branded_ingredient": {"$regex": "^WATER$", "$options": "i"}},
                            {"inci_name_normalized": {"$in": ["water", "aqua", "water / purified water / demineralized water / aqua"]}, "avg_cost": {"$lte": 5}}
                        ]
                    },
                    sort=[("avg_cost", 1)]
                )
                if cheap_water:
                    print(f"   ✅ Found cheaper water: {cheap_water.get('branded_ingredient', 'N/A')} at ₹{cheap_water.get('avg_cost', 0):.2f}/kg - using this instead")
                    doc = cheap_water
                    base_cost = float(cheap_water.get('avg_cost', 0))
                else:
                    print(f"   ⚠️ No cheaper water found, using expensive record")
            
            # Apply 35% markup to MongoDB costs
            INGREDIENT_COST_MARKUP_PERCENT = 35
            INGREDIENT_COST_MARKUP_MULTIPLIER = 1 + (INGREDIENT_COST_MARKUP_PERCENT / 100.0)  # 1.35
            cost_with_markup = base_cost * INGREDIENT_COST_MARKUP_MULTIPLIER
            print(f"[MongoDB] Found '{inci_name}' = Rs {base_cost:.2f}/kg (base) -> Rs {cost_with_markup:.2f}/kg (with 35% markup)")
            print(f"   Matched: branded_ingredient='{doc.get('branded_ingredient', 'N/A')}', inci_name='{doc.get('inci_name', 'N/A')}'")
            return {
                'inci_name': doc.get('inci_name', ''),
                'branded_ingredient': doc.get('branded_ingredient', ''),
                'avg_cost': cost_with_markup,  # Return cost with markup
                'base_cost': base_cost,  # Keep original for reference
                'markup_percent': INGREDIENT_COST_MARKUP_PERCENT,
                'primary_supplier': doc.get('primary_supplier', ''),
                'is_fallback': False
            }
        
        # Not found in MongoDB
        if use_fallback:
            # Use Python fallback only for non-Claude contexts (e.g., tests, utilities)
            # For Claude-based flows (make_wish_basic_mode), return None and let Claude handle it
            print(f"[WARNING] MongoDB: '{inci_name}' not found, using Python fallback cost estimation")
            print(f"[NOTE] For Claude-based flows, set use_fallback=False to let Claude handle intelligent cost estimation")
            return _estimate_fallback_cost(inci_name)
        
        # Return None - let Claude handle the fallback with intelligent classification
        print(f"[INFO] MongoDB: '{inci_name}' not found, returning None (Claude will handle cost estimation)")
        return None
    
    except Exception as e:
        print(f"[ERROR] MongoDB Error looking up cost for {inci_name}: {e}")
        # On error, try fallback if enabled
        if use_fallback:
            print(f"[WARNING] MongoDB lookup failed for '{inci_name}', using fallback cost estimation")
            return _estimate_fallback_cost(inci_name)
        return None


async def lookup_multiple_costs(inci_names: List[str], use_fallback: bool = True) -> Dict[str, Optional[Dict]]:
    """
    Look up costs for multiple INCI names at once (batch query).
    Falls back to individual lookups with cost estimation for missing ingredients.
    
    Args:
        inci_names: List of INCI names to look up
        use_fallback: If True, use fallback estimation for ingredients not found in MongoDB
    
    Returns:
        Dict mapping INCI name to cost data (may include fallback estimates)
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
        # Apply 35% markup to MongoDB costs
        INGREDIENT_COST_MARKUP_PERCENT = 35
        INGREDIENT_COST_MARKUP_MULTIPLIER = 1 + (INGREDIENT_COST_MARKUP_PERCENT / 100.0)  # 1.35
        
        async for doc in cursor:
            inci_norm = doc.get('inci_name_normalized', '')
            if inci_norm in normalized_names:
                original_name = normalized_names[inci_norm]
                base_cost = float(doc.get('avg_cost', 0))
                cost_with_markup = base_cost * INGREDIENT_COST_MARKUP_MULTIPLIER
                found_docs[original_name] = {
                    'inci_name': doc.get('inci_name', ''),
                    'branded_ingredient': doc.get('branded_ingredient', ''),
                    'avg_cost': cost_with_markup,  # Return cost with markup
                    'base_cost': base_cost,  # Keep original for reference
                    'markup_percent': INGREDIENT_COST_MARKUP_PERCENT,
                    'primary_supplier': doc.get('primary_supplier', ''),
                    'is_fallback': False
                }
        
        # Map results and use fallback for missing ingredients
        for inci in inci_names:
            if inci in found_docs:
                results[inci] = found_docs[inci]
            elif use_fallback:
                # Use fallback estimation for missing ingredients
                results[inci] = _estimate_fallback_cost(inci)
            else:
                results[inci] = None
        
        return results
    
    except Exception as e:
        print(f"Error in batch lookup: {e}")
        # Fallback to individual lookups with fallback enabled
        for inci in inci_names:
            results[inci] = await lookup_cost_by_inci(inci, use_fallback=use_fallback)
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

