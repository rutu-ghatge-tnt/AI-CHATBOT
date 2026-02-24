"""
Formula Generation API Endpoint
================================

This module provides the API endpoint for the "Create A Wish" feature.

ENDPOINT: POST /api/generate-formula

WHAT IT DOES:
- Accepts wish data from frontend
- Generates complete cosmetic formulation
- Returns structured formula with phases, ingredients, insights

HOW IT WORKS:
1. Receives CreateWishRequest
2. Calls formula_generator.generate_formula()
3. Returns GenerateFormulaResponse

WHAT WE USE:
- formula_generator.py: Core generation logic
- MongoDB: Ingredient database
- Claude (Anthropic): AI optimization
- BIS RAG: Compliance checking
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from bson import ObjectId
import time
import asyncio

# Import authentication
from app.ai_ingredient_intelligence.auth import verify_jwt_token
from app.ai_ingredient_intelligence.models.schemas import (
    CreateWishRequest,
    GenerateFormulaResponse,
    UpdateWishHistoryRequest,
    UpdateWishHistoryResponse,
    DeleteWishHistoryResponse
)
from app.ai_ingredient_intelligence.logic.formula_generator import (
    generate_formula,
    get_texture_description
)
from app.ai_ingredient_intelligence.logic.make_wish_generator import (
    generate_formula_from_wish as generate_make_wish_formula
)
from app.ai_ingredient_intelligence.db.collections import wish_history_col

# Import notification helpers
from app.ai_ingredient_intelligence.logic.websocket_notifications import notify_user_enhanced
from app.ai_ingredient_intelligence.models.notification_schemas import NotificationAction

router = APIRouter(prefix="/formula", tags=["Formula Generation"])


def filter_original_formulation_references(items: list, text_fields: list = ["text", "title"]) -> list:
    """
    Filter out items that reference 'original formulation' or similar terms.
    
    Args:
        items: List of dicts (insights or warnings)
        text_fields: List of field names to check for references
        
    Returns:
        Filtered list without original formulation references
    """
    original_formulation_keywords = [
        "original formulation", "original formula", "previous formulation", 
        "previous formula", "provided formulation", "initial formulation"
    ]
    
    filtered = []
    for item in items:
        # Check all specified text fields
        item_text = " ".join([
            str(item.get(field, "")).lower() 
            for field in text_fields 
            if field in item
        ])
        
        # Skip if mentions original formulation
        if not any(keyword in item_text for keyword in original_formulation_keywords):
            filtered.append(item)
    
    return filtered


def transform_make_wish_to_frontend_format(make_wish_result: dict, original_wish_data: dict) -> dict:
    """
    Transform 5-stage Make a Wish response to frontend-expected format.
    
    Frontend expects:
    {
        "name": str,
        "version": str,
        "cost": float,
        "costTarget": {"min": float, "max": float},
        "ph": {"min": float, "max": float},
        "texture": str,
        "shelfLife": str,
        "phases": [...],
        "insights": [...],
        "warnings": [...],
        "compliance": {...}
    }
    """
    try:
        # Extract data from 5-stage result
        optimized = make_wish_result.get("optimized_formula", {})
        ingredient_selection = make_wish_result.get("ingredient_selection", {})
        cost_analysis = make_wish_result.get("cost_analysis", {})
        compliance = make_wish_result.get("compliance", {})
        
        # Get formula name
        formula_name = ingredient_selection.get("formula_name") or optimized.get("optimized_formula", {}).get("name") or f"{original_wish_data.get('productType', 'Formula').title()}"
        
        # Get cost - use new format (per_g) if available, fallback to old format
        cost_estimate = cost_analysis.get("cost_estimate", {})
        if cost_estimate:
            # Use realistic estimate from new format (per_g)
            raw_material_per_g = cost_estimate.get("raw_material_per_g", {})
            total_cost_per_g = raw_material_per_g.get("realistic") or raw_material_per_g.get("best_estimate") or raw_material_per_g.get("optimistic", 0)
            # Convert to per_100g for backward compatibility (multiply by 100)
            total_cost = total_cost_per_g * 100 if total_cost_per_g else 0
        else:
            # Fallback to old format
            total_cost = cost_analysis.get("raw_material_cost", {}).get("total_per_100g") or cost_analysis.get("raw_material_cost", {}).get("total_per_g", 0) * 100 or optimized.get("optimized_formula", {}).get("estimated_cost_per_100g") or optimized.get("optimized_formula", {}).get("estimated_cost_per_g", 0) * 100 or 0
        
        # Get pH
        target_ph = ingredient_selection.get("target_ph") or optimized.get("optimized_formula", {}).get("target_ph") or {"min": 5.0, "max": 6.0}
        
        # Get ingredients from optimized formula
        optimized_ingredients = optimized.get("ingredients", [])
        
        # Organize ingredients into phases
        phases_data = ingredient_selection.get("phases", [])
        phases = []
        used_ingredients = set()  # Track which ingredients have been assigned
        
        # First, try to match ingredients to phases from phases_data
        for phase_info in phases_data:
            phase_id = phase_info.get("id", "A")
            phase_name = phase_info.get("name", "Phase")
            
            # Get ingredients for this phase
            phase_ingredient_names = phase_info.get("ingredient_names", [])
            phase_ingredients = []
            
            for ing in optimized_ingredients:
                ing_name = ing.get("name", "")
                ing_inci = ing.get("inci", "")
                ing_key = f"{ing_name}|{ing_inci}"
                
                # Skip if already used
                if ing_key in used_ingredients:
                    continue
                
                # Match ingredient to phase by name or INCI
                if (ing_name in phase_ingredient_names or 
                    ing_inci in phase_ingredient_names or
                    any(name.lower() in ing_name.lower() or name.lower() in ing_inci.lower() 
                        for name in phase_ingredient_names)):
                    
                    phase_ingredients.append({
                        "name": ing_name,
                        "inci": ing_inci,
                        "percent": ing.get("percent", 0),
                        "cost": ing.get("cost_contribution", 0),
                        "function": ing.get("function", "Other"),
                        "hero": ing.get("is_hero", False)
                    })
                    used_ingredients.add(ing_key)
            
            # If no ingredients matched by name, try to find by phase ID
            if not phase_ingredients:
                for ing in optimized_ingredients:
                    ing_key = f"{ing.get('name', '')}|{ing.get('inci', '')}"
                    if ing_key in used_ingredients:
                        continue
                    if ing.get("phase") == phase_id:
                        phase_ingredients.append({
                            "name": ing.get("name", ""),
                            "inci": ing.get("inci", ""),
                            "percent": ing.get("percent", 0),
                            "cost": ing.get("cost_contribution", 0),
                            "function": ing.get("function", "Other"),
                            "hero": ing.get("is_hero", False)
                        })
                        used_ingredients.add(ing_key)
            
            if phase_ingredients:
                phases.append({
                    "id": phase_id,
                    "name": phase_name,
                    "temp": phase_info.get("process_temp", "room"),
                    "color": get_phase_color(phase_id),
                    "ingredients": phase_ingredients
                })
        
        # Add any remaining ingredients to appropriate phases
        for ing in optimized_ingredients:
            ing_key = f"{ing.get('name', '')}|{ing.get('inci', '')}"
            if ing_key not in used_ingredients:
                phase_id = ing.get("phase", "A")
                # Find existing phase or create new one
                phase_found = False
                for phase in phases:
                    if phase["id"] == phase_id:
                        phase["ingredients"].append({
                            "name": ing.get("name", ""),
                            "inci": ing.get("inci", ""),
                            "percent": ing.get("percent", 0),
                            "cost": ing.get("cost_contribution", 0),
                            "function": ing.get("function", "Other"),
                            "hero": ing.get("is_hero", False)
                        })
                        phase_found = True
                        used_ingredients.add(ing_key)
                        break
                
                if not phase_found:
                    # Create new phase for this ingredient
                    phases.append({
                        "id": phase_id,
                        "name": f"Phase {phase_id}",
                        "temp": "room",
                        "color": get_phase_color(phase_id),
                        "ingredients": [{
                            "name": ing.get("name", ""),
                            "inci": ing.get("inci", ""),
                            "percent": ing.get("percent", 0),
                            "cost": ing.get("cost_contribution", 0),
                            "function": ing.get("function", "Other"),
                            "hero": ing.get("is_hero", False)
                        }]
                    })
                    used_ingredients.add(ing_key)
        
        # If no phases created, create default phases from ingredients
        if not phases:
            # Group by phase from optimized ingredients
            phase_groups = {}
            for ing in optimized_ingredients:
                phase_id = ing.get("phase", "A")
                if phase_id not in phase_groups:
                    phase_groups[phase_id] = []
                phase_groups[phase_id].append({
                    "name": ing.get("name", ""),
                    "inci": ing.get("inci", ""),
                    "percent": ing.get("percent", 0),
                    "cost": ing.get("cost_contribution", 0),
                    "function": ing.get("function", "Other"),
                    "hero": ing.get("is_hero", False)
                })
            
            for phase_id, ingredients in phase_groups.items():
                phases.append({
                    "id": phase_id,
                    "name": f"Phase {phase_id}",
                    "temp": "room",
                    "color": get_phase_color(phase_id),
                    "ingredients": ingredients
                })
        
        # Get insights - filter out any that reference "original formulation"
        insights = []
        for insight in ingredient_selection.get("insights", []):
            insights.append({
                "icon": insight.get("icon", "💡"),
                "title": insight.get("title", ""),
                "text": insight.get("text", "")
            })
        for insight in optimized.get("insights", []):
            insights.append({
                "icon": insight.get("icon", "💡"),
                "title": insight.get("title", ""),
                "text": insight.get("text", "")
            })
        # Filter out original formulation references
        insights = filter_original_formulation_references(insights, ["text", "title"])
        
        # Get warnings - filter out any that reference "original formulation"
        warnings = []
        for warning in ingredient_selection.get("warnings", []):
            warnings.append({
                "type": warning.get("severity", "info"),
                "text": warning.get("text", "")
            })
        for warning in optimized.get("warnings", []):
            warnings.append({
                "type": warning.get("severity", "info"),
                "text": warning.get("text", "")
            })
        # Filter out original formulation references
        warnings = filter_original_formulation_references(warnings, ["text"])
        
        # Get compliance
        compliance_data = {
            "silicone": True,  # Default
            "paraben": True,   # Default
            "vegan": False     # Default
        }
        
        # Check exclusions
        exclusions = original_wish_data.get("exclusions", [])
        exclusion_lower = [exc.lower() for exc in exclusions]
        
        if "silicone-free" in exclusion_lower:
            compliance_data["silicone"] = False
        if "paraben-free" in exclusion_lower:
            compliance_data["paraben"] = False
        if "vegan" in exclusion_lower:
            compliance_data["vegan"] = True
        
        # Override with compliance check results if available
        if compliance.get("overall_status"):
            bis_compliance = compliance.get("bis_compliance", {})
            # Check ingredient status for actual compliance
            ingredient_status = compliance.get("ingredient_status", [])
            for ing_status in ingredient_status:
                ing_name = ing_status.get("ingredient", "").lower()
                if "silicone" in ing_name or "dimethicone" in ing_name:
                    compliance_data["silicone"] = True
                if "paraben" in ing_name:
                    compliance_data["paraben"] = True
        
        # Get texture
        texture = original_wish_data.get("texture", "lightweight")
        from app.ai_ingredient_intelligence.logic.formula_generator import get_texture_description
        texture_desc = get_texture_description(texture)
        
        # Build response with both old and new cost formats
        response = {
            "name": formula_name,
            "version": "v1",
            "cost": total_cost,  # Old format - single number (backward compatible)
            "costTarget": {
                "min": original_wish_data.get("costMin", 30),
                "max": original_wish_data.get("costMax", 60)
            },
            "ph": target_ph,
            "texture": texture_desc,
            "shelfLife": "12 months",
            "phases": phases,
            "insights": insights,
            "warnings": warnings,
            "compliance": compliance_data
        }
        
        # Add new cost estimation data if available (use per_g as primary, include per_100g for compatibility)
        if cost_estimate:
            raw_material_per_g = cost_estimate.get("raw_material_per_g", {})
            raw_material_per_100g = cost_estimate.get("raw_material_per_100g", {})
            response["costEstimate"] = {
                "rawMaterialPerG": {
                    "optimistic": raw_material_per_g.get("optimistic"),
                    "realistic": raw_material_per_g.get("realistic"),
                    "conservative": raw_material_per_g.get("conservative"),
                    "displayRange": raw_material_per_g.get("display_range"),
                    "bestEstimate": raw_material_per_g.get("best_estimate"),
                    "confidence": raw_material_per_g.get("confidence")
                },
                "rawMaterialPer100g": {
                    "optimistic": raw_material_per_100g.get("optimistic"),
                    "realistic": raw_material_per_100g.get("realistic"),
                    "conservative": raw_material_per_100g.get("conservative"),
                    "displayRange": raw_material_per_100g.get("display_range"),
                    "bestEstimate": raw_material_per_100g.get("best_estimate"),
                    "confidence": raw_material_per_100g.get("confidence")
                },
                "confidenceBreakdown": cost_estimate.get("confidence_breakdown", {}),
                "topCostDrivers": cost_estimate.get("top_cost_drivers", []),
                "disclaimers": cost_estimate.get("disclaimers", [])
            }
        
        # Add validation report if available
        validation_report = cost_analysis.get("validation_report", {})
        if validation_report:
            response["costValidation"] = {
                "waterCostCheck": validation_report.get("water_cost_check"),
                "totalVsBenchmark": validation_report.get("total_vs_benchmark"),
                "activeCostRatio": validation_report.get("active_cost_ratio"),
                "mrpPlausibility": validation_report.get("mrp_plausibility"),
                "ingredientRatioCheck": validation_report.get("ingredient_ratio_check"),
                "competitorAlignment": validation_report.get("competitor_alignment"),
                "overallConfidence": validation_report.get("overall_confidence"),
                "flags": validation_report.get("flags", [])
            }
        
        # Add competitor comparison data (for "Your Market Position" table)
        competitor_comparison = cost_analysis.get("competitor_comparison", {})
        if competitor_comparison:
            # Merge advantages into similar_products for easier frontend access
            similar_products = competitor_comparison.get("similar_products", [])
            advantages = competitor_comparison.get("advantages", [])
            
            # Create a lookup map: brand -> advantage
            advantage_map = {}
            for adv in advantages:
                brand = adv.get("competitor_brand", "").lower().strip()
                advantage_text = adv.get("advantage", "").strip()
                # Remove dashes if AI mistakenly used them
                if advantage_text in ["—", "-", "–", "—", ""]:
                    advantage_text = ""
                if brand and advantage_text:
                    advantage_map[brand] = advantage_text
            
            # Attach advantage to each product
            for product in similar_products:
                product_brand = product.get("brand", "").lower().strip()
                product_name = product.get("product", "").lower().strip()
                
                # Try to find advantage by brand first
                if product_brand in advantage_map:
                    product["advantage"] = advantage_map[product_brand]
                else:
                    # Try to find by product name as fallback
                    found = False
                    for adv in advantages:
                        adv_brand = adv.get("competitor_brand", "").lower().strip()
                        if adv_brand in product_name or product_name in adv_brand:
                            advantage_text = adv.get("advantage", "").strip()
                            if advantage_text and advantage_text not in ["—", "-", "–", "—"]:
                                product["advantage"] = advantage_text
                                found = True
                                break
                    
                    # If still no advantage found, set a default message
                    if not found:
                        product["advantage"] = "Competitive positioning with quality formulation"
            
            response["competitorComparison"] = {
                "similarProducts": similar_products,  # Now includes advantage field
                "yourProduct": competitor_comparison.get("your_product", {}),
                "competitivePosition": competitor_comparison.get("competitive_position", ""),
                "advantages": advantages  # Keep original for backward compatibility
            }
        
        return response
    
    except Exception as e:
        print(f"⚠️ Error transforming Make a Wish response: {e}")
        import traceback
        traceback.print_exc()
        # Fallback to old method
        raise


def get_phase_color(phase_id: str) -> str:
    """Get color gradient for phase based on ID"""
    colors = {
        "A": "from-blue-500 to-blue-600",
        "B": "from-green-500 to-green-600",
        "C": "from-purple-500 to-purple-600",
        "D": "from-orange-500 to-orange-600",
        "E": "from-pink-500 to-pink-600"
    }
    return colors.get(phase_id, "from-slate-500 to-slate-600")


@router.post("/generate", response_model=GenerateFormulaResponse)
async def generate_formula_endpoint(
    request: CreateWishRequest,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Generate a cosmetic formulation based on user wish data
    
    AUTO-SAVE: Results are automatically saved to wish history if user is authenticated.
    Provide optional "name" and "tag" in request to customize the saved history item.
    
    REQUEST BODY:
    {
        "productType": "serum",
        "benefits": ["Brightening", "Hydration"],
        "exclusions": ["Silicone-free", "Paraben-free"],
        "heroIngredients": ["Vitamin C", "Hyaluronic Acid"],
        "costMin": 30,
        "costMax": 60,
        "texture": "gel",
        "fragrance": "none",
        "notes": "Additional requirements",
        "name": "Formula Name" (optional, for auto-saving),
        "tag": "optional-tag" (optional),
        "history_id": "existing_history_id" (optional, to update existing history)
    }
    
    RESPONSE:
    {
        "name": "Brightening Serum",
        "version": "v1",
        "cost": 48.5,
        "ph": {"min": 5.0, "max": 5.5},
        "texture": "Lightweight gel",
        "shelfLife": "12 months",
        "phases": [...],
        "insights": [...],
        "warnings": [...],
        "compliance": {...},
        "history_id": "..." (if auto-saved)
    }
    """
    print(f"\n{'='*80}")
    print(f"[DEBUG] 🚀 API CALL: /api/formula/generate")
    print(f"[DEBUG] Request received at: {datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()}")
    print(f"{'='*80}\n")
    
    start_time = time.time()
    
    # 🔹 Auto-save: Extract user info and required name/tag for history
    user_id_value = current_user.get("user_id") or current_user.get("_id")
    name = request.name.strip() if request.name else ""
    tag = request.tag
    notes = request.notes  # Already exists in CreateWishRequest
    provided_history_id = request.history_id
    history_id = None
    
    # Validate name is provided if auto-save is enabled (user_id is present) and no existing history_id
    if user_id_value and not provided_history_id and not name:
        raise HTTPException(status_code=400, detail="name is required for auto-save")
    
    # Validate history_id if provided
    if provided_history_id:
        try:
            if ObjectId.is_valid(provided_history_id):
                existing_item = await wish_history_col.find_one({
                    "_id": ObjectId(provided_history_id),
                    "user_id": user_id_value
                })
                if existing_item:
                    history_id = provided_history_id
                    print(f"[AUTO-SAVE] Using existing history_id: {history_id}")
                else:
                    print(f"[AUTO-SAVE] Warning: Provided history_id {provided_history_id} not found or doesn't belong to user, creating new one")
            else:
                print(f"[AUTO-SAVE] Warning: Invalid history_id format: {provided_history_id}, creating new one")
        except Exception as e:
            print(f"[AUTO-SAVE] Warning: Error validating history_id: {e}, creating new one")
    
    try:
        # Convert Pydantic model to dict (exclude autosave fields from wish_data)
        wish_data = request.model_dump(exclude={"name", "tag", "history_id"})
        print(f"[DEBUG] Wish data keys: {list(wish_data.keys())}")
        print(f"[DEBUG] Product type: {wish_data.get('productType')}")
        print(f"[DEBUG] Benefits: {wish_data.get('benefits')}")
        print(f"[DEBUG] Exclusions: {wish_data.get('exclusions')}")
        print(f"[DEBUG] Hero ingredients: {wish_data.get('heroIngredients')}")
        print(f"[DEBUG] Cost range: {wish_data.get('costMin')} - {wish_data.get('costMax')}")
        
        # Validate required fields
        if not wish_data.get("productType"):
            raise HTTPException(
                status_code=400,
                detail="productType is required"
            )
        
        if not wish_data.get("benefits") or len(wish_data.get("benefits", [])) == 0:
            raise HTTPException(
                status_code=400,
                detail="At least one benefit is required"
            )
        
        # Set defaults only if not provided
        if wish_data.get("costMin") is None:
            wish_data["costMin"] = 30
        if wish_data.get("costMax") is None:
            wish_data["costMax"] = 60
        
        # Validate cost range
        if wish_data.get("costMin") is not None and wish_data.get("costMax") is not None:
            if wish_data["costMin"] >= wish_data["costMax"]:
                raise HTTPException(
                    status_code=400,
                    detail="costMax must be greater than costMin"
                )
            if wish_data["costMin"] < 0 or wish_data["costMax"] < 0:
                raise HTTPException(
                    status_code=400,
                    detail="Cost values must be positive"
                )
        
        wish_data.setdefault("texture", wish_data.get("productType", "serum"))
        wish_data.setdefault("fragrance", "none")
        wish_data.setdefault("exclusions", [])
        wish_data.setdefault("heroIngredients", [])
        wish_data.setdefault("notes", "")
        
        print(f"📝 Generating formula for product type: {wish_data['productType']}")
        print(f"   Benefits: {', '.join(wish_data['benefits'])}")
        print(f"   Exclusions: {', '.join(wish_data.get('exclusions', []))}")
        print(f"   Hero Ingredients: {', '.join(wish_data.get('heroIngredients', []))}")
        
        # Create a unique identifier for the wish data to check for duplicates
        import json
        wish_data_for_comparison = {
            "category": wish_data.get("category", "skincare"),
            "productType": wish_data.get("productType"),
            "benefits": sorted(wish_data.get("benefits", [])),
            "exclusions": sorted(wish_data.get("exclusions", [])),
            "heroIngredients": sorted(wish_data.get("heroIngredients", [])),
            "costMin": wish_data.get("costMin"),
            "costMax": wish_data.get("costMax"),
            "texture": wish_data.get("texture")
        }
        wish_data_hash = json.dumps(wish_data_for_comparison, sort_keys=True)
        
        # 🔹 Auto-save: Save initial state with "in_progress" status if user_id provided and no existing history_id
        if user_id_value and not history_id:
            try:
                # Check if a history item with the same wish data already exists for this user
                existing_history_item = await wish_history_col.find_one({
                    "user_id": user_id_value,
                    "wish_data_hash": wish_data_hash
                }, sort=[("created_at", -1)])  # Get the most recent one
                
                if existing_history_item:
                    history_id = str(existing_history_item["_id"])
                    print(f"[AUTO-SAVE] Found existing history item with same wish data, reusing history_id: {history_id}")
                else:
                    # Name is required - already validated above
                    # Truncate if too long
                    if len(name) > 100:
                        name = name[:100]
                    
                    # Save initial state
                    history_doc = {
                        "user_id": user_id_value,
                        "name": name,
                        "tag": tag,
                        "notes": notes,
                        "wish_data": wish_data,
                        "wish_data_hash": wish_data_hash,
                        "status": "in_progress",
                        "created_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()
                    }
                    result = await wish_history_col.insert_one(history_doc)
                    history_id = str(result.inserted_id)
                    print(f"[AUTO-SAVE] Saved initial state with history_id: {history_id}")
            except Exception as e:
                print(f"[AUTO-SAVE] Warning: Failed to save initial state: {e}")
                import traceback
                traceback.print_exc()
                # Continue with generation even if saving fails
        
        # Generate formula using 5-stage Make a Wish pipeline
        formula = None
        try:
            # Transform wish_data to match Make a Wish format
            make_wish_data = {
                "category": wish_data.get("category", "skincare"),
                "productType": wish_data.get("productType", "serum"),
                "benefits": wish_data.get("benefits", []),
                "exclusions": wish_data.get("exclusions", []),
                "heroIngredients": wish_data.get("heroIngredients", []),
                "costMin": wish_data.get("costMin", 30),
                "costMax": wish_data.get("costMax", 60),
                "texture": wish_data.get("texture", "lightweight"),
                "claims": wish_data.get("preferences", {}).get("claims", []),
                "targetAudience": wish_data.get("targetAudience", []),
                "additionalNotes": wish_data.get("notes", "")
            }
            
            # Generate using 5-stage pipeline
            make_wish_result = await generate_make_wish_formula(make_wish_data)
            
            # Transform 5-stage response to frontend format
            formula = transform_make_wish_to_frontend_format(make_wish_result, wish_data)
            print("✅ Used 5-stage Make a Wish pipeline")
        
        except Exception as make_wish_error:
            print(f"⚠️ 5-stage pipeline failed, falling back to hybrid approach: {make_wish_error}")
            import traceback
            traceback.print_exc()
            # Fallback to old hybrid approach
            formula = await generate_formula(wish_data)
            print("✅ Used hybrid approach (fallback)")
        except ValueError as ve:
            # Handle specific validation errors
            raise HTTPException(
                status_code=400,
                detail=f"Formula generation validation error: {str(ve)}"
            )
        except Exception as gen_error:
            print(f"❌ Error in generate_formula: {gen_error}")
            import traceback
            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail=f"Error during formula generation: {str(gen_error)}"
            )
        
        # Validate response structure
        if not formula or not isinstance(formula, dict):
            raise HTTPException(
                status_code=500,
                detail="Invalid formula structure returned"
            )
        
        if "phases" not in formula or not formula["phases"]:
            raise HTTPException(
                status_code=500,
                detail="No phases generated in formula"
            )
        
        processing_time = time.time() - start_time
        print(f"[DEBUG] ✅ Formula generated in {processing_time:.2f}s")
        print(f"[DEBUG]    Cost: ₹{formula.get('cost', 0)}/unit")
        print(f"[DEBUG]    Phases: {len(formula.get('phases', []))}")
        print(f"[DEBUG]    Ingredients: {sum(len(p.get('ingredients', [])) for p in formula.get('phases', []))}")
        
        # Ensure all required fields are present
        formula.setdefault("name", f"{wish_data['productType'].title()} Formula")
        formula.setdefault("version", "v1")
        formula.setdefault("cost", 0)
        formula.setdefault("costTarget", {"min": wish_data.get("costMin", 30), "max": wish_data.get("costMax", 60)})
        formula.setdefault("ph", {"min": 5.0, "max": 6.5})
        # Import here to avoid circular dependency
        from app.ai_ingredient_intelligence.logic.formula_generator import get_texture_description
        formula.setdefault("texture", get_texture_description(wish_data.get("texture", "serum")))
        formula.setdefault("shelfLife", "12 months")
        formula.setdefault("insights", [])
        formula.setdefault("warnings", [])
        
        # Compliance is set by validate_formula, but set default if not present
        # Compliance logic: False = free (good), True = contains (bad for silicone/paraben)
        # For vegan: True = vegan (good)
        if "compliance" not in formula:
            exclusions = wish_data.get("exclusions", [])
            # Check if formula actually contains these ingredients (will be validated properly in validate_formula)
            formula["compliance"] = {
                "silicone": True,  # Default, will be checked against actual ingredients
                "paraben": True,   # Default, will be checked against actual ingredients
                "vegan": "vegan" in [exc.lower() for exc in exclusions] if exclusions else False
            }
        
        # 🔹 Auto-save: Update history with "completed" status and formula_result
        if user_id_value and history_id:
            try:
                update_doc = {
                    "formula_result": formula,
                    "status": "completed",
                    "updated_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()
                }
                
                await wish_history_col.update_one(
                    {"_id": ObjectId(history_id), "user_id": user_id_value},
                    {"$set": update_doc}
                )
                print(f"[AUTO-SAVE] Updated history {history_id} with completed status and formula result")
            except Exception as e:
                print(f"[AUTO-SAVE] Warning: Failed to update history: {e}")
                import traceback
                traceback.print_exc()
                # Don't fail the response if saving fails
        elif user_id_value and name:
            # Create new history item if we didn't have history_id but have name
            try:
                if len(name) > 100:
                    name = name[:100]
                
                history_doc = {
                    "user_id": user_id_value,
                    "name": name,
                    "tag": tag,
                    "notes": notes,
                    "wish_data": wish_data,
                    "wish_data_hash": wish_data_hash,
                    "formula_result": formula,
                    "status": "completed",
                    "created_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()
                }
                result_insert = await wish_history_col.insert_one(history_doc)
                history_id = str(result_insert.inserted_id)
                print(f"[AUTO-SAVE] Created new history {history_id} with completed status and formula result")
            except Exception as e:
                print(f"[AUTO-SAVE] Warning: Failed to create history: {e}")
                import traceback
                traceback.print_exc()
                # Don't fail the response if saving fails
        
        # Add history_id to formula if available
        if history_id:
            formula["history_id"] = history_id
        
        return GenerateFormulaResponse(**formula)
    
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid request data: {str(e)}"
        )
    except Exception as e:
        print(f"❌ Unexpected error generating formula: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@router.post("/save-wish-history")
async def save_wish_history(
    payload: dict,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    ⚠️ DEPRECATED ENDPOINT - This endpoint is no longer needed.
    
    Wish history is now automatically saved by the /generate endpoints:
    - POST /api/formula/generate - Auto-saves when name is provided
    - POST /api/make-wish/generate - Auto-saves when name is provided
    
    The generate endpoints return a history_id in the response which can be used
    to retrieve the saved history later.
    
    This endpoint is kept for backward compatibility but returns an error.
    Please update your frontend to use the autosave feature instead.
    """
    print(f"\n{'='*80}")
    print(f"[DEPRECATED] 🚀 API CALL: /api/formula/save-wish-history")
    print(f"[DEPRECATED] This endpoint is deprecated. Use autosave in /generate endpoints instead.")
    print(f"{'='*80}\n")
    
    user_id_value = current_user.get("user_id") or current_user.get("_id")
    print(f"[DEPRECATED] Called by user: {user_id_value}")
    
    raise HTTPException(
        status_code=410,  # 410 Gone - indicates the resource is no longer available
        detail={
            "error": "Endpoint deprecated",
            "message": "The /save-wish-history endpoint is deprecated. Wish history is now automatically saved by the /generate endpoints.",
            "migration_guide": {
                "old_way": "Call /generate, then call /save-wish-history with the result",
                "new_way": "Call /generate with 'name' field in request body. The endpoint will auto-save and return 'history_id' in the response.",
                "endpoints": [
                    "POST /api/formula/generate - Include 'name' field in CreateWishRequest",
                    "POST /api/make-wish/generate - Include 'name' field in MakeWishRequest"
                ],
                "example": {
                    "request": {
                        "productType": "serum",
                        "benefits": ["Brightening"],
                        "name": "My Formula Name"  # Required for autosave
                    },
                    "response": {
                        "...": "formula data",
                        "history_id": "507f1f77bcf86cd799439011"  # MongoDB ObjectId
                    }
                }
            }
        }
    )


@router.get("/wish-history")
async def get_wish_history(
    search: Optional[str] = None,
    limit: int = 50,
    offset: Optional[int] = None,
    skip: Optional[int] = None,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Get wish history for a user
    
    HISTORY FUNCTIONALITY:
    - Returns all formula generation history items for the authenticated user
    - Each item contains the original wish data and the generated formula result
    - Supports pagination with limit and offset/skip parameters
    - Search works across name and notes fields
    - History items are sorted by creation date (newest first)
    - Users can access previously generated formulas and their original requirements
    
    Query params:
    - search: Optional search term (searches name and notes)
    - limit: Number of results (default 50)
    - offset: Number of results to skip (default 0) - preferred parameter
    - skip: Number of results to skip (default 0) - kept for backward compatibility
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    """
    # Use offset if provided, otherwise use skip, default to 0
    skip_value = offset if offset is not None else (skip if skip is not None else 0)
    
    print(f"\n{'='*80}")
    print(f"[DEBUG] 🚀 API CALL: /api/formula/wish-history")
    print(f"[DEBUG] Request received at: {datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()}")
    print(f"[DEBUG] Query params - search: {search}, limit: {limit}, offset: {offset}, skip: {skip}, using skip_value: {skip_value}")
    print(f"{'='*80}\n")
    
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        print(f"[DEBUG] User ID extracted: {user_id}")
        if not user_id:
            raise HTTPException(
                status_code=400,
                detail="User ID not found in JWT token"
            )
        
        # Build query
        query = {"user_id": user_id}
        
        if search:
            query["$or"] = [
                {"name": {"$regex": search, "$options": "i"}},
                {"notes": {"$regex": search, "$options": "i"}}
            ]
        
        # Get total count
        total = await wish_history_col.count_documents(query)
        
        # Get items - only get summary fields (exclude large fields)
        cursor = wish_history_col.find(
            query,
            {
                "_id": 1,
                "name": 1,
                "notes": 1,
                "created_at": 1,
                "tag": 1,
                "status": 1,
                "market_trends_status": 1,
                "market_trends_error": 1,
                "wish_text": 1,
                "query_id": 1,
            }
        ).sort("created_at", -1).skip(skip_value).limit(limit)
        
        # Import QMS collection for fetching query details
        from app.ai_ingredient_intelligence.db.collections import qms_queries_col
        
        items = []
        async for doc in cursor:
            # Create summary item (exclude large fields)
            # wish_data = doc.get("wish_data", {})
            # formula_result = doc.get("formula_result", {})
            
            # Fetch query details if query_id exists
            query_info = None
            if doc.get("query_id"):
                try:
                    query_doc = await qms_queries_col.find_one(
                        {"_id": ObjectId(doc.get("query_id"))},
                        {"display_id": 1, "queue_number": 1, "status": 1, "created_at": 1}
                    )
                    if query_doc:
                        query_info = {
                            "query_id": doc.get("query_id"),
                            "query_display_id": query_doc.get("display_id"),
                            "queue_number": query_doc.get("queue_number"),
                            "status": query_doc.get("status"),
                            "created_at": query_doc.get("created_at").isoformat() if isinstance(query_doc.get("created_at"), datetime) else query_doc.get("created_at")
                        }
                except Exception as e:
                    print(f"⚠️ Warning: Failed to fetch query details: {e}")
                    # Just include query_id if fetch fails
                    query_info = {"query_id": doc.get("query_id")}
            
            items.append({
                "id": str(doc["_id"]),
                # "user_id": doc.get("user_id"),
                "name": doc.get("name", ""),
                "tag": doc.get("tag", ""),
                "wish_text": doc.get("wish_text", ""),
                "status": doc.get("status", ""),
                "market_trends_status": doc.get("market_trends_status"),
                "market_trends_error": doc.get("market_trends_error"),
                "notes": doc.get("notes", ""),
                "created_at": doc.get("created_at", ""),
                "query_id": doc.get("query_id"),  # Include query_id for reference
                "query_info": query_info,  # Include full query info if available
                # "formula_data": doc.get("formula_data", None),
                # "has_wish_data": wish_data is not None and bool(wish_data),
                # "has_formula_result": formula_result is not None and bool(formula_result)
            })
        
        return {
            "items": items,
            "total": total
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting wish history: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get wish history: {str(e)}"
        )


@router.get("/wish-history/{history_id}/details")
async def get_wish_history_detail(
    history_id: str,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Get full details of a specific wish history item (includes all large fields)
    
    Returns the complete data:
    - mode: "basic" or "advanced" (inferred from stored payload)
    - basic_mode_result: full AI payload for basic mode; None for advanced
    - formula_data: full optimized formula for advanced mode; None for basic
    - parsed_data, complexity, formula_id, created_at, updated_at, etc.
    - quote_data: commercialization request if exists
    
    Use after /generate-revised (which returns only success, formula_id, history_id)
    and pass history_id to load the full result here.
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    - Only returns items belonging to the authenticated user
    """
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        # Note: user_id validation is optional for this endpoint (dev version removed it)
        # Keeping it for security but can be commented out if needed
        
        # Validate ObjectId - check if it's a valid MongoDB ObjectId format
        # MongoDB ObjectIds are 24-character hex strings (no dashes)
        # UUIDs have dashes and are 36 characters, so we can detect them
        import re
        uuid_pattern = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
        
        if uuid_pattern.match(history_id):
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid history ID format: UUID detected. The save-wish-history endpoint is disabled and returns dummy UUIDs. Please use the history_id returned from the /generate endpoint (which auto-saves and returns a MongoDB ObjectId). Received UUID: {history_id}"
            )
        
        if not ObjectId.is_valid(history_id):
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid history ID format. Expected MongoDB ObjectId (24 hex characters), got: {history_id[:50]}"
            )
        
        # Fetch full item (including large fields) - optimized query
        doc = await wish_history_col.find_one({
            "_id": ObjectId(history_id),
            # "user_id": user_id
        })
        
        if not doc:
            raise HTTPException(status_code=404, detail="History item not found")
        
        # Fetch commercialization request with timeout to prevent blocking
        # This is optional data, so we don't want it to slow down the main response
        formula_id = doc.get("formula_id", "")
        commercialization_request = None
        
        if formula_id:
            # Check QMS queries instead of commercialization_requests (dev version)
            from app.ai_ingredient_intelligence.db.collections import qms_queries_col
            try:
                # Use asyncio.wait_for to timeout after 2 seconds
                # If it takes longer, we'll just return None for quote_data
                qms_query = await asyncio.wait_for(
                    qms_queries_col.find_one({
                        # "user_id": user_id,  # Dev version removed user_id check
                        "wish_brief.formula_id": formula_id,
                        "wish_brief.history_id": history_id,
                        "status": {"$nin": ["cancelled"]}  # Any active query
                    }),
                    timeout=2.0
                )
                
                # If found, format the response
                if qms_query:
                    commercialization_request = {
                        "_id": str(qms_query.get("_id")),
                        "queue_number": qms_query.get("queue_number") or qms_query.get("wish_brief", {}).get("queue_number"),
                        "status": qms_query.get("status"),
                        "created_at": qms_query.get("created_at").isoformat() if isinstance(qms_query.get("created_at"), datetime) else qms_query.get("created_at"),
                        "additional_notes": qms_query.get("wish_brief", {}).get("additional_notes"),
                        "display_id": qms_query.get("display_id")
                    }
            except asyncio.TimeoutError:
                # QMS query timed out - just skip it, don't block response
                print(f"[WARNING] QMS query timed out for formula_id: {formula_id}")
                commercialization_request = None
            except Exception as e:
                # Don't fail the whole request if QMS query fails
                print(f"[WARNING] Error fetching QMS query: {e}")
                commercialization_request = None
        
        # Return full data - mode at doc root (basic/advanced); fallback infer from payload for old docs
        basic_mode_result = doc.get("basic_mode_result")
        formula_data = doc.get("formula_data")
        trend_data = doc.get("trend_data", {})  # Get trend analysis data
        market_trends = doc.get("market_trends")  # Get market trends data
        synthesis_data = doc.get("synthesis_data", {})  # Get synthesis data
        
        # Get query/commercialization info if available (fetch from QMS queries collection)
        query_info = None
        if doc.get("query_id"):
            try:
                from app.ai_ingredient_intelligence.db.collections import qms_queries_col
                query_doc = await qms_queries_col.find_one(
                    {"_id": ObjectId(doc.get("query_id"))},
                    {"display_id": 1, "queue_number": 1, "status": 1, "created_at": 1, "updated_at": 1}
                )
                if query_doc:
                    query_info = {
                        "query_id": doc.get("query_id"),
                        "query_display_id": query_doc.get("display_id"),
                        "queue_number": query_doc.get("queue_number"),
                        "status": query_doc.get("status"),
                        "created_at": query_doc.get("created_at").isoformat() if isinstance(query_doc.get("created_at"), datetime) else query_doc.get("created_at"),
                        "updated_at": query_doc.get("updated_at").isoformat() if isinstance(query_doc.get("updated_at"), datetime) else query_doc.get("updated_at")
                    }
            except Exception as e:
                print(f"⚠️ Warning: Failed to fetch query details: {e}")
                # Just include query_id if fetch fails
                query_info = {"query_id": doc.get("query_id")}
        
        return {
            "id": str(doc["_id"]),
            "history_id": str(doc["_id"]),
            "user_id": doc.get("user_id"),
            "name": doc.get("name", ""),
            "notes": doc.get("notes", ""),
            "wish_text": doc.get("wish_text", ""),
            "status": doc.get("status", ""),
            "market_trends_status": doc.get("market_trends_status"),
            "market_trends_error": doc.get("market_trends_error"),
            "tag": doc.get("tag", ""),
            "parsed_data": doc.get("parsed_data"),
            "complexity": doc.get("complexity", ""),
            "formula_id": doc.get("formula_id", ""),
            "created_at": doc.get("created_at", ""),
            "updated_at": doc.get("updated_at"),
            "mode": doc.get("mode", "advanced"),
            "basic_mode_result": basic_mode_result,
            "formula_data": formula_data,
            "trend_data": trend_data,  # Include trend analysis data in response
            "market_trends": market_trends,  # Include market trends data in response
            "synthesis_data": synthesis_data,  # Include synthesis data in response
            "query_info": query_info,  # Include query/commercialization info if available
            "gamma_ppt": doc.get("gamma_ppt"),  # Include Gamma PPT info (download_url, edit_url, etc.)
            # For future reference: legacy / backward compatibility (uncomment if needed)
            # "wish_data": doc.get("wish_data"),
            # "formula_result": doc.get("formula_result"),
            "quote_data": commercialization_request,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting wish history detail: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get wish history detail: {str(e)}"
        )


@router.patch("/wish-history/{history_id}", response_model=UpdateWishHistoryResponse)
async def update_wish_history(
    history_id: str,
    payload: UpdateWishHistoryRequest,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Update wish history item - all fields are optional and can be updated
    
    HISTORY FUNCTIONALITY:
    - All fields can be edited to support regeneration scenarios
    - Allows updating formula results, wish data, and other fields when regenerating
    - Useful for saving regenerated content back to history
    
    Editable fields (all optional):
    - name: Update the name of the wish history item
    - notes: Update user notes
    - tag: Update tag for categorization
    - wish_data: Update wish data (for regeneration)
    - formula_result: Update formula result (for regeneration)
    - status: Update status (e.g., 'in_progress', 'completed')
    
    Note: user_id and created_at are automatically preserved and should not be included in payload
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    """
    print(f"\n{'='*80}")
    print(f"[DEBUG] 🚀 API CALL: /api/formula/wish-history/{history_id} (PATCH)")
    print(f"[DEBUG] Request received at: {datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()}")
    print(f"[DEBUG] History ID: {history_id}")
    print(f"[DEBUG] Payload: {payload.model_dump(exclude_none=True)}")
    print(f"{'='*80}\n")
    
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        print(f"[DEBUG] User ID extracted: {user_id}")
        if not user_id:
            raise HTTPException(
                status_code=400,
                detail="User ID not found in JWT token"
            )
        
        # Validate ObjectId
        if not ObjectId.is_valid(history_id):
            raise HTTPException(status_code=400, detail="Invalid history ID")
        
        # Build update document - only include fields that are provided (not None)
        update_doc = payload.model_dump(exclude_none=True)
        
        if not update_doc:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        # Get the wish item before update to get the name for notification
        wish_item = await wish_history_col.find_one({"_id": ObjectId(history_id), "user_id": user_id})
        
        if not wish_item:
            raise HTTPException(
                status_code=404,
                detail="History item not found or you don't have permission to update it"
            )
        
        wish_name = wish_item.get("name", "Wish")
        
        # Only update if it belongs to the user
        result = await wish_history_col.update_one(
            {"_id": ObjectId(history_id), "user_id": user_id},
            {"$set": update_doc}
        )
        
        if result.matched_count == 0:
            raise HTTPException(
                status_code=404,
                detail="History item not found or you don't have permission to update it"
            )
        
        # Send notification for successful update
        try:
            await notify_user_enhanced(
                user_id=user_id,
                module="make-wish",
                notification_type="success",
                title="Wish Updated Successfully!",
                message=f"Your wish '{wish_name}' has been updated.",
                action=NotificationAction(
                    label="View Wish",
                    kind="route",
                    to=f"/make-wish/{history_id}"
                ),
                meta={
                    "history_id": history_id,
                    "status": "updated",
                    "type": "make_wish_updated",
                    "updated_fields": list(update_doc.keys())
                },
                send_websocket=False
            )
            print(f"✅ [UPDATE] Notification sent for wish update: {history_id}")
        except Exception as notify_error:
            print(f"⚠️ [UPDATE] Failed to send notification: {notify_error}")
            # Don't fail the request if notification fails
        
        return UpdateWishHistoryResponse(
            success=True,
            message="Wish history updated successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating wish history: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update wish history: {str(e)}"
        )


@router.delete("/wish-history/{history_id}", response_model=DeleteWishHistoryResponse)
async def delete_wish_history(
    history_id: str,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Delete a wish history item
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    """
    print(f"\n{'='*80}")
    print(f"[DEBUG] 🚀 API CALL: /api/formula/wish-history/{history_id} (DELETE)")
    print(f"[DEBUG] Request received at: {datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()}")
    print(f"[DEBUG] History ID: {history_id}")
    print(f"{'='*80}\n")
    
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        print(f"[DEBUG] User ID extracted: {user_id}")
        if not user_id:
            raise HTTPException(
                status_code=400,
                detail="User ID not found in JWT token"
            )
        
        # Validate ObjectId
        if not ObjectId.is_valid(history_id):
            raise HTTPException(status_code=400, detail="Invalid history ID")
        
        # Get the wish item before deletion to get the name for notification
        wish_item = await wish_history_col.find_one({"_id": ObjectId(history_id), "user_id": user_id})
        
        if not wish_item:
            raise HTTPException(
                status_code=404,
                detail="History item not found or you don't have permission to delete it"
            )
        
        wish_name = wish_item.get("name", "Wish")
        
        # Delete only if it belongs to the user
        result = await wish_history_col.delete_one(
            {"_id": ObjectId(history_id), "user_id": user_id}
        )
        
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=404,
                detail="History item not found or you don't have permission to delete it"
            )
        
        # Save notification for successful deletion (no WebSocket push)
        try:
            await notify_user_enhanced(
                user_id=user_id,
                module="make-wish",
                notification_type="delete",
                title="Wish Deleted",
                message=f"Your wish '{wish_name}' has been deleted successfully.",
                meta={
                    "history_id": history_id,
                    "status": "deleted",
                    "type": "make_wish_deleted",
                    "wish_name": wish_name
                },
                send_websocket=False
            )
            print(f"✅ [DELETE] Notification saved for wish deletion: {history_id}")
        except Exception as notify_error:
            print(f"⚠️ [DELETE] Failed to send notification: {notify_error}")
            # Don't fail the request if notification fails
        
        return DeleteWishHistoryResponse(
            success=True,
            message="History item deleted successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting wish history: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete wish history: {str(e)}"
        )

