"""
Make a Wish API Endpoint
========================

This module provides the API endpoint for the "Make a Wish" feature.

ENDPOINT: POST /api/make-wish/generate

WHAT IT DOES:
- Accepts wish data from frontend
- Runs complete 5-stage AI pipeline
- Returns comprehensive formula with all analysis

STAGES:
1. Ingredient Selection
2. Formula Optimization
3. Manufacturing Process
4. Cost Analysis
5. Compliance Check
"""

from fastapi import APIRouter, HTTPException, Header, Depends, Query, BackgroundTasks, Body
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone, timedelta
from bson import ObjectId
import time
import httpx
import os

# Import authentication - Using JWT tokens
from app.ai_ingredient_intelligence.auth import verify_jwt_token

from app.ai_ingredient_intelligence.logic.make_wish_generator import (
    generate_formula_from_wish
)
from app.ai_ingredient_intelligence.logic.make_wish_basic_mode import (
    generate_formula_basic_mode
)
from app.ai_ingredient_intelligence.logic.make_wish_rules_engine import (
    get_rules_engine,
    ValidationSeverity
)
from app.ai_ingredient_intelligence.models.schemas import (
    MakeWishRequest,
    MakeWishResponse
)
from pydantic import BaseModel, Field
from typing import Optional
from app.ai_ingredient_intelligence.db.collections import wish_history_col

# Import modular Gamma PPT and Claude prompt generators
from app.ai_ingredient_intelligence.logic.gamma_ppt_generator import (
    generate_ppt_from_data,
    is_gamma_available
)
from app.ai_ingredient_intelligence.logic.claude_prompt_generator import (
    generate_business_strategy_prompt,
    get_default_business_strategy_prompt
)
from app.ai_ingredient_intelligence.logic.market_trends_service import MarketTrendsService
from app.ai_ingredient_intelligence.logic.packaging_data import (
    get_all_packaging_options,
    get_packaging_options_by_category,
    get_packaging_by_size
)

router = APIRouter(prefix="/make-wish", tags=["Make a Wish"])


# ============================================================================
# HELPER ENDPOINT: Get Packaging Options
# ============================================================================

@router.get("/packaging-options")
async def get_packaging_options(
    category: Optional[str] = Query(None, description="Filter by category: 'liquid' or 'solid'"),
    size: Optional[str] = Query(None, description="Filter by size: e.g., '30g', '50g' (ALL SIZES IN GRAMS)"),
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Get all available packaging options for cost calculation.
    
    NOTE: All sizes are in GRAMS (g) only. No ml units.
    For liquid products, 1ml ≈ 1g (standard approximation for cosmetics).
    
    This endpoint provides packaging data including:
    - Bottle/jar cost
    - Carton box cost
    - Labeling cost
    - Total packaging cost
    
    QUERY PARAMETERS:
    - category: Optional filter by "liquid" or "solid"
    - size: Optional filter by size (e.g., "30g", "50g") - ALL IN GRAMS
    
    RESPONSE:
    {
        "packaging_options": {
            "dropper_bottle_30g": {
                "type": "Dropper bottle 30g",
                "category": "liquid",
                "size": "30g",
                "bottle_cost": 15.0,
                "carton_box_cost": 7.0,
                "labeling_cost": 4.0,
                "total": 26.0
            },
            ...
        }
    }
    """
    try:
        if category and size:
            # Get options for specific category and size
            options = get_packaging_by_size(size, category)
            result = {}
            for opt in options:
                result[opt["key"]] = {
                    "type": opt["type"],
                    "category": opt["category"],
                    "size": opt["size"],
                    "bottle_cost": opt["bottle_cost"],
                    "carton_box_cost": opt["carton_box_cost"],
                    "labeling_cost": opt["labeling_cost"],
                    "total": opt["total"]
                }
        elif category:
            # Get options for category
            options = get_packaging_options_by_category(category)
            result = {}
            for opt in options:
                result[opt["key"]] = {
                    "type": opt["type"],
                    "category": opt["category"],
                    "size": opt["size"],
                    "bottle_cost": opt["bottle_cost"],
                    "carton_box_cost": opt["carton_box_cost"],
                    "labeling_cost": opt["labeling_cost"],
                    "total": opt["total"]
                }
        else:
            # Get all options
            result = get_all_packaging_options()
        
        return {
            "success": True,
            "packaging_options": result,
            "count": len(result)
        }
    except Exception as e:
        print(f"❌ Error fetching packaging options: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching packaging options: {str(e)}"
        )


# ============================================================================
# HELPER ENDPOINT: Check Gamma PPT Generation Status
# ============================================================================

@router.get("/check-ppt-status/{generation_id}", response_model=None)
async def check_ppt_status(
    generation_id: str,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Check the status of a Gamma PPT generation.
    
    This endpoint allows you to check if a presentation generation is complete
    and retrieve the download/edit URLs.
    
    PATH PARAMETER:
    - generation_id: The Gamma generationId from the /generate-ppt response
    
    RESPONSE:
    {
        "success": true,
        "status": "pending" | "completed" | "failed",
        "download_url": "https://...",
        "edit_url": "https://...",
        "presentation_id": "...",
        "message": "..."
    }
    """
    print(f"\n{'='*80}")
    print(f"[DEBUG] 🔍 Checking PPT status for generation_id: {generation_id}")
    print(f"{'='*80}\n")
    
    try:
        # Import Gamma API utilities
        from app.ai_ingredient_intelligence.logic.gamma_ppt_generator import GAMMA_API_KEY, GAMMA_API_BASE_URL
        
        if not GAMMA_API_KEY:
            raise HTTPException(
                status_code=500,
                detail="GAMMA_API_KEY not configured"
            )
        
        # Check status via Gamma API
        status_url = f"{GAMMA_API_BASE_URL}/generations/{generation_id}"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                status_url,
                headers={
                    "X-API-KEY": GAMMA_API_KEY,
                    "accept": "application/json"
                }
            )
            
            if response.status_code == 401:
                raise HTTPException(
                    status_code=500,
                    detail="Invalid Gamma API key. Please check your GAMMA_API_KEY in .env file."
                )
            
            if response.status_code != 200:
                error_text = response.text[:200]
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Gamma API error: {error_text}"
                )
            
            status_data = response.json()
            print(f"[DEBUG] Gamma status response: {status_data}")
            
            status = status_data.get("status", "unknown")
            
            # Extract URLs if status is completed
            download_url = None
            edit_url = None
            presentation_id = status_data.get("generationId") or generation_id
            
            if status == "completed":
                # Per Gamma API docs, when status is "completed", response includes:
                # - exportUrl: Direct download URL for PPTX/PDF
                # - gammaUrl: URL to view/edit the presentation
                # - gammaId: The presentation ID
                
                download_url = (
                    status_data.get("exportUrl") or  # Primary field per Gamma API
                    status_data.get("downloadUrl") or
                    status_data.get("url") or
                    status_data.get("presentationUrl") or
                    status_data.get("file")
                )
                
                edit_url = (
                    status_data.get("gammaUrl") or  # Primary field per Gamma API
                    status_data.get("editUrl") or
                    status_data.get("editPath") or
                    status_data.get("presentationUrl") or
                    status_data.get("url")
                )
                
                presentation_id = (
                    status_data.get("gammaId") or  # Primary field per Gamma API
                    status_data.get("id") or
                    status_data.get("presentationId") or
                    presentation_id
                )
                
                # Check nested structures
                if not download_url or not edit_url:
                    for key in ["data", "presentation", "result", "gamma"]:
                        if key in status_data and isinstance(status_data[key], dict):
                            nested = status_data[key]
                            download_url = download_url or nested.get("url") or nested.get("downloadUrl")
                            edit_url = edit_url or nested.get("editUrl") or nested.get("editPath")
                            if download_url or edit_url:
                                break
            
            message = ""
            if status == "pending":
                message = "Presentation is still being generated. Please check again in a few moments."
            elif status == "completed":
                if download_url or edit_url:
                    message = "Presentation is ready! Use the URLs above to access it."
                else:
                    message = "Presentation is completed but URLs not found in response. Check Gamma dashboard."
            elif status == "failed":
                message = "Presentation generation failed. Please try generating again."
            else:
                message = f"Unknown status: {status}"
            
            return {
                "success": True,
                "status": status,
                "download_url": download_url,
                "edit_url": edit_url,
                "presentation_id": presentation_id,
                "generation_id": generation_id,
                "message": message,
                "gamma_response": status_data
            }
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"[DEBUG] ❌ Error checking PPT status: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Error checking PPT status: {str(e)}"
        )


# ============================================================================
# HELPER FUNCTIONS FOR GAMMA API
# ============================================================================

def _extract_ingredients_from_phases(phases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract flat list of ingredients from phases structure"""
    ingredients = []
    for phase in phases:
        for ing in phase.get("ingredients", []):
            ingredients.append({
                "name": ing.get("name", ""),
                "inci": ing.get("inci", ""),
                "percent": ing.get("percent", 0),
                "phase": phase.get("id", ""),
                "function": ing.get("function", ""),
                "cost_per_kg": ing.get("cost", 0) * 1000 if ing.get("cost") else 0,  # Convert to per kg
                "is_hero": ing.get("hero", False)
            })
    return ingredients


def _check_cost_in_range(cost: float, cost_target: Dict[str, float]) -> bool:
    """Check if cost is within target range"""
    if not cost_target:
        return True
    min_cost = cost_target.get("min", 0)
    max_cost = cost_target.get("max", float('inf'))
    return min_cost <= cost <= max_cost


def _extract_ingredients_from_basic_mode(basic_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract ingredients list from basic_mode_result structure"""
    ingredients = []
    formula_data = basic_result.get("formula", {})
    technical_formula = formula_data.get("technicalFormula", {}) if isinstance(formula_data, dict) else {}
    
    # Extract from technical formula phases
    phases = technical_formula.get("phases", [])
    for phase in phases:
        # Phase ID can be in "id" or "phase" field
        phase_id = phase.get("id") or phase.get("phase", "")
        for ing in phase.get("ingredients", []):
            # Handle percentage - could be "percent" or "percentage", number or string
            percent = ing.get("percent") or ing.get("percentage", 0)
            if isinstance(percent, str):
                try:
                    percent = float(percent.replace('%', '').strip())
                except:
                    percent = 0
            percent = float(percent) if percent else 0
            
            ingredients.append({
                "name": ing.get("name", ""),
                "inci": ing.get("inci", ing.get("name", "")),
                "percent": percent,
                "phase": phase_id,
                "function": ing.get("function", ""),
                "is_hero": ing.get("hero", False) or ing.get("isHero", False)
            })
    
    return ingredients


def _extract_insights_from_basic_mode(basic_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract insights from basic_mode_result structure"""
    insights = []
    formula_data = basic_result.get("formula", {})
    key_features = formula_data.get("keyFeatures", []) if isinstance(formula_data, dict) else []
    
    for feature in key_features:
        insights.append({
            "icon": feature.get("icon", "💡"),
            "title": feature.get("title", ""),
            "text": feature.get("explanation", "")
        })
    
    return insights


def _extract_warnings_from_basic_mode(basic_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract warnings from basic_mode_result structure"""
    warnings = []
    formula_data = basic_result.get("formula", {})
    qa_cards = formula_data.get("qaCards", []) if isinstance(formula_data, dict) else []
    
    # Extract any warnings from Q&A or other sections
    # Basic mode typically doesn't have warnings, but check anyway
    pro_tips = formula_data.get("proTips", []) if isinstance(formula_data, dict) else []
    for tip in pro_tips:
        if "warning" in tip.get("text", "").lower() or "caution" in tip.get("text", "").lower():
            warnings.append({
                "severity": "info",
                "text": tip.get("text", "")
            })
    
    return warnings


def _extract_cost_analysis_from_basic_mode(basic_result: Dict[str, Any], business_numbers: Dict[str, Any]) -> Dict[str, Any]:
    """Extract cost analysis from basic_mode_result structure"""
    formula_data = basic_result.get("formula", {})
    technical_formula = formula_data.get("technicalFormula", {}) if isinstance(formula_data, dict) else {}
    
    cost_per_100g = technical_formula.get("totalCostPer100g", 0)
    
    cost_analysis = {
        "raw_material_cost": {
            "total_per_100g": cost_per_100g,
            "total_per_g": cost_per_100g / 100 if cost_per_100g > 0 else 0
        }
    }
    
    # Add packaging options if available
    if business_numbers.get("packagingOptions"):
        cost_analysis["packaging_estimate"] = business_numbers.get("packagingOptions", {})
    
    # Add market comparison if available
    if business_numbers.get("marketComparison"):
        cost_analysis["competitor_comparison"] = {
            "similar_products": business_numbers.get("marketComparison", [])
        }
    
    return cost_analysis


def format_wish_data_for_gamma(wish_response: Dict[str, Any]) -> str:
    """
    Transform MakeWishResponse data into structured text for Gamma API.
    Formats ALL data from all 5 stages of the Make a Wish pipeline into comprehensive presentation-ready content.
    Includes every field and nested data available in the wish response.
    
    Supports both old format (with ingredient_selection, optimized_formula) and new format (with formula, insights).
    """
    sections = []
    
    # Detect format: new format has 'formula' and 'insights' at top level, old format has 'ingredient_selection' and 'optimized_formula'
    # Also check for formula_result structure (another old format variant) and basic_mode_result
    is_new_format = 'formula' in wish_response and 'insights' in wish_response
    has_formula_result = 'formula_result' in wish_response
    has_basic_mode_result = 'basic_mode_result' in wish_response
    
    # Currency Note - IMPORTANT
    sections.append("=" * 80)
    sections.append("⚠️ CURRENCY NOTE: ALL PRICES AND COSTS ARE IN INDIAN RUPEES (₹)")
    sections.append("All monetary values in this data are in Indian Rupees (₹).")
    sections.append("Do NOT convert to dollars ($) or any other currency.")
    sections.append("=" * 80)
    
    # Executive Summary - COMPLETE wish_data
    sections.append("\n" + "=" * 80)
    sections.append("EXECUTIVE SUMMARY - COMPLETE WISH DATA")
    sections.append("=" * 80)
    
    # Get wish_data, fallback to parsed_data if wish_data is empty
    wish_data = wish_response.get("wish_data") or {}
    parsed_data = wish_response.get("parsed_data") or {}
    
    # Ensure both are dicts (handle None case)
    if not isinstance(wish_data, dict):
        wish_data = {}
    if not isinstance(parsed_data, dict):
        parsed_data = {}
    
    # If wish_data is empty but parsed_data exists, use parsed_data
    if not wish_data and parsed_data:
        print(f"[FORMAT] ⚠️ wish_data is empty, using parsed_data for formatting")
        # Extract key info from parsed_data
        if parsed_data.get("product_type"):
            product_type = parsed_data.get("product_type", {})
            if isinstance(product_type, dict):
                wish_data["productType"] = product_type.get("name", "N/A")
        if parsed_data.get("category"):
            wish_data["category"] = parsed_data.get("category", "N/A")
        if parsed_data.get("detected_benefits"):
            wish_data["benefits"] = parsed_data.get("detected_benefits", [])
        if parsed_data.get("detected_ingredients"):
            wish_data["heroIngredients"] = parsed_data.get("detected_ingredients", [])
        if parsed_data.get("wish_text"):
            wish_data["wish_text"] = parsed_data.get("wish_text", "")
        if parsed_data.get("complexity"):
            wish_data["complexity"] = parsed_data.get("complexity", "")
    
    # Also include parsed_data details directly
    if parsed_data:
        sections.append("\n--- PARSED DATA (from natural language wish) ---")
        if parsed_data.get("wish_text"):
            sections.append(f"Original Wish Text: {parsed_data.get('wish_text')}")
        if parsed_data.get("category"):
            sections.append(f"Detected Category: {parsed_data.get('category')}")
        if parsed_data.get("product_type"):
            product_type = parsed_data.get("product_type", {})
            if isinstance(product_type, dict):
                sections.append(f"Product Type: {product_type.get('name', 'N/A')}")
        if parsed_data.get("detected_ingredients"):
            ingredients_list = parsed_data.get('detected_ingredients', [])
            # Handle list of strings or list of dicts
            if ingredients_list and isinstance(ingredients_list[0], dict):
                ingredients_str = ', '.join([str(ing.get('name', ing.get('ingredient', ing))) for ing in ingredients_list if ing])
            else:
                ingredients_str = ', '.join([str(ing) for ing in ingredients_list if ing])
            sections.append(f"Detected Ingredients: {ingredients_str}")
        if parsed_data.get("detected_benefits"):
            benefits_list = parsed_data.get('detected_benefits', [])
            # Handle list of strings or list of dicts
            if benefits_list and isinstance(benefits_list[0], dict):
                benefits_str = ', '.join([str(ben.get('name', ben.get('benefit', ben))) for ben in benefits_list if ben])
            else:
                benefits_str = ', '.join([str(ben) for ben in benefits_list if ben])
            sections.append(f"Detected Benefits: {benefits_str}")
        if parsed_data.get("complexity"):
            sections.append(f"Complexity Level: {parsed_data.get('complexity')}")
        if parsed_data.get("mode"):
            sections.append(f"Mode: {parsed_data.get('mode')}")
    
    sections.append(f"\nProduct Type: {wish_data.get('productType', 'N/A') if isinstance(wish_data, dict) else 'N/A'}")
    category = wish_data.get('category', 'N/A') if isinstance(wish_data, dict) else 'N/A'
    sections.append(f"Category: {category.title() if isinstance(category, str) else 'N/A'}")
    
    # Handle benefits - could be list of strings or list of dicts
    benefits = wish_data.get('benefits', []) if isinstance(wish_data, dict) else []
    if benefits and isinstance(benefits, list):
        if benefits and isinstance(benefits[0], dict):
            benefits_str = ', '.join([str(b.get('name', b.get('benefit', b))) for b in benefits if b])
        else:
            benefits_str = ', '.join([str(b) for b in benefits if b])
        sections.append(f"Benefits: {benefits_str}")
    else:
        sections.append(f"Benefits: N/A")
    
    if wish_data.get('heroIngredients'):
        hero_ingredients = wish_data.get('heroIngredients', [])
        if hero_ingredients and isinstance(hero_ingredients, list):
            if hero_ingredients and isinstance(hero_ingredients[0], dict):
                hero_str = ', '.join([str(ing.get('name', ing.get('ingredient', ing))) for ing in hero_ingredients if ing])
            else:
                hero_str = ', '.join([str(ing) for ing in hero_ingredients if ing])
            sections.append(f"Hero Ingredients: {hero_str}")
    if wish_data.get('exclusions'):
        exclusions = wish_data.get('exclusions', [])
        if exclusions and isinstance(exclusions, list):
            if exclusions and isinstance(exclusions[0], dict):
                excl_str = ', '.join([str(ex.get('name', ex.get('ingredient', ex))) for ex in exclusions if ex])
            else:
                excl_str = ', '.join([str(ex) for ex in exclusions if ex])
            sections.append(f"Exclusions: {excl_str}")
    if wish_data.get('texture'):
        sections.append(f"Texture: {wish_data.get('texture', 'N/A')}")
    if wish_data.get('costMin') and wish_data.get('costMax'):
        sections.append(f"Cost Range: ₹{wish_data.get('costMin')} - ₹{wish_data.get('costMax')} per unit")
    
    # Additional wish_data fields
    if wish_data.get('claims'):
        claims = wish_data.get('claims', [])
        if claims and isinstance(claims, list):
            if claims and isinstance(claims[0], dict):
                claims_str = ', '.join([str(c.get('name', c.get('claim', c))) for c in claims if c])
            else:
                claims_str = ', '.join([str(c) for c in claims if c])
            sections.append(f"Claims: {claims_str}")
    if wish_data.get('targetAudience'):
        audience = wish_data.get('targetAudience', [])
        if audience and isinstance(audience, list):
            if audience and isinstance(audience[0], dict):
                audience_str = ', '.join([str(a.get('name', a.get('audience', a))) for a in audience if a])
            else:
                audience_str = ', '.join([str(a) for a in audience if a])
            sections.append(f"Target Audience: {audience_str}")
    if wish_data.get('additionalNotes'):
        sections.append(f"Additional Notes: {wish_data.get('additionalNotes', '')}")
    if wish_data.get('mode'):
        sections.append(f"Mode: {wish_data.get('mode', 'advanced').title()}")
    if wish_data.get('preferences'):
        prefs = wish_data.get('preferences', {})
        if prefs.get('keyIngredients'):
            key_ings = prefs.get('keyIngredients', [])
            if key_ings and isinstance(key_ings, list):
                if key_ings and isinstance(key_ings[0], dict):
                    key_ings_str = ', '.join([str(ing.get('name', ing.get('ingredient', ing))) for ing in key_ings if ing])
                else:
                    key_ings_str = ', '.join([str(ing) for ing in key_ings if ing])
                sections.append(f"Key Ingredients Preference: {key_ings_str}")
        if prefs.get('avoidIngredients'):
            avoid_ings = prefs.get('avoidIngredients', [])
            if avoid_ings and isinstance(avoid_ings, list):
                if avoid_ings and isinstance(avoid_ings[0], dict):
                    avoid_ings_str = ', '.join([str(ing.get('name', ing.get('ingredient', ing))) for ing in avoid_ings if ing])
                else:
                    avoid_ings_str = ', '.join([str(ing) for ing in avoid_ings if ing])
                sections.append(f"Avoid Ingredients: {avoid_ings_str}")
        if prefs.get('claims'):
            pref_claims = prefs.get('claims', [])
            if pref_claims and isinstance(pref_claims, list):
                if pref_claims and isinstance(pref_claims[0], dict):
                    pref_claims_str = ', '.join([str(c.get('name', c.get('claim', c))) for c in pref_claims if c])
                else:
                    pref_claims_str = ', '.join([str(c) for c in pref_claims if c])
                sections.append(f"Preferred Claims: {pref_claims_str}")
    
    # Handle basic_mode_result format
    if has_basic_mode_result:
        basic_mode_result = wish_response.get("basic_mode_result", {})
        formula_data = basic_mode_result.get("formula", {}) if isinstance(basic_mode_result, dict) else {}
        technical_formula = formula_data.get("technicalFormula", {}) if isinstance(formula_data, dict) else {}
        extracted_params = basic_mode_result.get("extractedParameters", {}) if isinstance(basic_mode_result, dict) else {}
        active_options = basic_mode_result.get("activeOptions", {}) if isinstance(basic_mode_result, dict) else {}
        business_numbers = basic_mode_result.get("businessNumbers", {}) if isinstance(basic_mode_result, dict) else {}
        
        sections.append("\n" + "=" * 80)
        sections.append("FORMULA INFORMATION (BASIC MODE)")
        sections.append("=" * 80)
        
        if formula_data.get('formulaName'):
            sections.append(f"\nFormula Name: {formula_data.get('formulaName')}")
        if extracted_params.get('productType'):
            sections.append(f"Product Type: {extracted_params.get('productType')}")
        if extracted_params.get('primaryConcern'):
            sections.append(f"Primary Concern: {extracted_params.get('primaryConcern')}")
        if extracted_params.get('secondaryConcerns'):
            concerns = extracted_params.get('secondaryConcerns', [])
            if concerns:
                sections.append(f"Secondary Concerns: {', '.join([str(c) for c in concerns])}")
        if extracted_params.get('priceSegment'):
            sections.append(f"Price Segment: {extracted_params.get('priceSegment')}")
        
        # Active Options
        if active_options:
            sections.append("\n" + "=" * 80)
            sections.append("ACTIVE INGREDIENT OPTIONS")
            sections.append("=" * 80)
            
            concern_wise_options = active_options.get("concernWiseOptions", [])
            if concern_wise_options:
                for concern_group in concern_wise_options:
                    concern = concern_group.get("concern", "")
                    explanation = concern_group.get("explanation", "")
                    options = concern_group.get("options", [])
                    recommendation = concern_group.get("recommendation", "")
                    
                    sections.append(f"\n--- {concern} ---")
                    if explanation:
                        sections.append(f"Explanation: {explanation}")
                    sections.append("\nOptions:")
                    for opt in options:
                        name = opt.get("name", "")
                        concentration = opt.get("concentration", "")
                        efficacy = opt.get("efficacy", 0)
                        cost_impact = opt.get("costImpact", "")
                        why_good = opt.get("whyGood", "")
                        is_recommended = "⭐ RECOMMENDED" if opt.get("recommended", False) else ""
                        
                        sections.append(f"  • {name} {is_recommended}")
                        sections.append(f"    Concentration: {concentration}")
                        sections.append(f"    Efficacy: {'⭐' * efficacy} ({efficacy}/5)")
                        sections.append(f"    Cost Impact: {cost_impact}")
                        if why_good:
                            sections.append(f"    Why Good: {why_good}")
                    if recommendation:
                        sections.append(f"\nRecommendation: {recommendation}")
            
            # Recommended Formula Summary
            recommended_formula = active_options.get("recommendedFormula", {})
            if recommended_formula:
                sections.append("\n--- Recommended Formula Summary ---")
                hero_actives = recommended_formula.get("heroActives", [])
                if hero_actives:
                    sections.append("Hero Actives:")
                    for hero in hero_actives:
                        name = hero.get("name", "")
                        percentage = hero.get("percentage", 0)
                        targets = hero.get("targets", "")
                        sections.append(f"  • {name} ({percentage}%): {targets}")
                if recommended_formula.get("totalActivePercentage"):
                    sections.append(f"Total Active Percentage: {recommended_formula.get('totalActivePercentage')}%")
                if recommended_formula.get("positioning"):
                    sections.append(f"Positioning: {recommended_formula.get('positioning')}")
                if recommended_formula.get("estimatedActiveCost"):
                    sections.append(f"Estimated Active Cost: {recommended_formula.get('estimatedActiveCost')}")
        
        # Technical Formula
        if technical_formula:
            sections.append("\n" + "=" * 80)
            sections.append("TECHNICAL FORMULA")
            sections.append("=" * 80)
            
            if technical_formula.get('totalCostPer100g'):
                sections.append(f"\nTotal Cost per 100g: ₹{technical_formula.get('totalCostPer100g')}")
            
            # Phases with ingredients
            if technical_formula.get('phases'):
                total_percent = 0
                sections.append("\nFormula Phases and Ingredients:")
                sections.append("-" * 80)
                sections.append(f"{'Ingredient':<40} {'Percentage':<15} {'Phase':<10} {'Function':<15}")
                sections.append("-" * 80)
                
                for phase in technical_formula.get('phases', []):
                    # Phase ID can be in "id" or "phase" field
                    phase_id = phase.get('id') or phase.get('phase', '')
                    phase_name = phase.get('name', '')
                    sections.append(f"\n--- Phase {phase_id}: {phase_name} ---")
                    
                    for ing in phase.get('ingredients', []):
                        name = ing.get('name', 'Unknown')
                        inci = ing.get('inci', '')
                        # Handle percentage - could be "percent" or "percentage"
                        percent = ing.get('percent') or ing.get('percentage', 0)
                        if isinstance(percent, str):
                            try:
                                percent = float(percent.replace('%', '').strip())
                            except:
                                percent = 0
                        percent = float(percent) if percent else 0
                        function = ing.get('function', '')
                        is_hero = "⭐ HERO" if (ing.get('hero', False) or ing.get('isHero', False)) else ""
                        
                        total_percent += percent
                        sections.append(f"{name} {is_hero:<10} {percent:<15}% {phase_id:<10} {function:<15}")
                        if inci and inci != name:
                            sections.append(f"  INCI: {inci}")
                
                sections.append("-" * 80)
                sections.append(f"Total Percentage: {total_percent:.2f}%")
        
        # Key Features
        if formula_data.get('keyFeatures'):
            sections.append("\n" + "=" * 80)
            sections.append("KEY FEATURES")
            sections.append("=" * 80)
            sections.append("\nFeatures:")
            for feature in formula_data.get('keyFeatures', []):
                icon = feature.get('icon', '✨')
                title = feature.get('title', '')
                subtitle = feature.get('subtitle', '')
                explanation = feature.get('explanation', '')
                sections.append(f"  {icon} {title}")
                if subtitle:
                    sections.append(f"    {subtitle}")
                if explanation:
                    sections.append(f"    {explanation}")
        
        # Q&A Cards
        if formula_data.get('qaCards'):
            sections.append("\n" + "=" * 80)
            sections.append("FREQUENTLY ASKED QUESTIONS")
            sections.append("=" * 80)
            for qa in formula_data.get('qaCards', []):
                question = qa.get('question', '')
                answer = qa.get('answer', '')
                sections.append(f"\nQ: {question}")
                if answer:
                    sections.append(f"A: {answer}")
        
        # Business Numbers
        if business_numbers:
            sections.append("\n" + "=" * 80)
            sections.append("BUSINESS ANALYSIS")
            sections.append("=" * 80)
            
            # Market Comparison
            if business_numbers.get('marketComparison'):
                sections.append("\nMarket Comparison:")
                for competitor in business_numbers.get('marketComparison', []):
                    brand = competitor.get('brand', '')
                    product = competitor.get('product', '')
                    mrp = competitor.get('mrp', 0)
                    size = competitor.get('size', '')
                    advantage = competitor.get('advantage', '')
                    sections.append(f"  • {brand} - {product}: ₹{mrp} ({size})")
                    if advantage:
                        sections.append(f"    Advantage: {advantage}")
            
            # Packaging Options
            if business_numbers.get('packagingOptions'):
                sections.append("\nPackaging Options:")
                for pkg_key, pkg_data in business_numbers.get('packagingOptions', {}).items():
                    sections.append(f"  {pkg_key}:")
                    if isinstance(pkg_data, dict):
                        for key, value in pkg_data.items():
                            sections.append(f"    {key}: {value}")
        
        # Category Trends
        if formula_data.get('categoryTrends'):
            sections.append("\n" + "=" * 80)
            sections.append("CATEGORY TRENDS")
            sections.append("=" * 80)
            for trend in formula_data.get('categoryTrends', []):
                title = trend.get('title', '')
                description = trend.get('description', '')
                sections.append(f"\n• {title}")
                if description:
                    sections.append(f"  {description}")
    
    # Handle formula_result format (old format variant)
    elif has_formula_result:
        formula_result = wish_response.get("formula_result", {})
        
        sections.append("\n" + "=" * 80)
        sections.append("FORMULA INFORMATION")
        sections.append("=" * 80)
        
        if formula_result.get('name'):
            sections.append(f"\nFormula Name: {formula_result.get('name')}")
        if formula_result.get('version'):
            sections.append(f"Version: {formula_result.get('version')}")
        if formula_result.get('cost'):
            sections.append(f"Cost: ₹{formula_result.get('cost')}/100g")
        if formula_result.get('costTarget'):
            cost_target = formula_result.get('costTarget', {})
            sections.append(f"Cost Target: ₹{cost_target.get('min', 0)} - ₹{cost_target.get('max', 0)}/100g")
        if formula_result.get('ph'):
            ph_info = formula_result.get('ph', {})
            sections.append(f"Target pH: {ph_info.get('min', '')} - {ph_info.get('max', '')}")
        if formula_result.get('texture'):
            sections.append(f"Texture: {formula_result.get('texture')}")
        if formula_result.get('shelfLife'):
            sections.append(f"Shelf Life: {formula_result.get('shelfLife')}")
        
        # Phases with ingredients
        if formula_result.get('phases'):
            sections.append("\n" + "=" * 80)
            sections.append("FORMULA PHASES AND INGREDIENTS")
            sections.append("=" * 80)
            
            total_percent = 0
            sections.append("\nOptimized Ingredient Percentages:")
            sections.append("-" * 80)
            sections.append(f"{'Ingredient':<40} {'Percentage':<15} {'Phase':<10} {'Function':<15} {'Cost':<15}")
            sections.append("-" * 80)
            
            for phase in formula_result.get('phases', []):
                phase_id = phase.get('id', '')
                phase_name = phase.get('name', '')
                phase_temp = phase.get('temp', '')
                
                sections.append(f"\n--- Phase {phase_id}: {phase_name} ({phase_temp}) ---")
                
                for ing in phase.get('ingredients', []):
                    name = ing.get('name', 'Unknown')
                    inci = ing.get('inci', '')
                    percent = ing.get('percent', 0)
                    cost = ing.get('cost', 0)
                    function = ing.get('function', '')
                    is_hero = "⭐ HERO" if ing.get('hero', False) else ""
                    
                    total_percent += percent
                    sections.append(f"{name} {is_hero:<10} {percent:<15}% {phase_id:<10} {function:<15} ₹{cost:<15}")
                    if inci and inci != name:
                        sections.append(f"  INCI: {inci}")
            
            sections.append("-" * 80)
            sections.append(f"Total Percentage: {total_percent:.2f}%")
        
        # Insights
        if formula_result.get('insights'):
            sections.append("\n" + "=" * 80)
            sections.append("FORMULA INSIGHTS")
            sections.append("=" * 80)
            sections.append("\nKey Insights:")
            for insight in formula_result.get('insights', []):
                icon = insight.get('icon', '•')
                title = insight.get('title', '')
                text = insight.get('text', '')
                sections.append(f"  {icon} {title}: {text}")
        
        # Warnings
        if formula_result.get('warnings'):
            sections.append("\n" + "=" * 80)
            sections.append("WARNINGS AND NOTES")
            sections.append("=" * 80)
            sections.append("\nWarnings:")
            for warning in formula_result.get('warnings', []):
                warning_type = warning.get('type', 'info').upper()
                text = warning.get('text', '')
                sections.append(f"  [{warning_type}] {text}")
        
        # Compliance
        if formula_result.get('compliance'):
            sections.append("\n" + "=" * 80)
            sections.append("COMPLIANCE INFORMATION")
            sections.append("=" * 80)
            compliance = formula_result.get('compliance', {})
            sections.append(f"\nSilicone-Free: {'Yes' if compliance.get('silicone') else 'No'}")
            sections.append(f"Paraben-Free: {'Yes' if compliance.get('paraben') else 'No'}")
            sections.append(f"Vegan: {'Yes' if compliance.get('vegan') else 'No'}")
    
    # Handle new format structure
    formula = {}
    insights = {}
    if is_new_format:
        formula = wish_response.get("formula", {})
        insights = wish_response.get("insights", {})
        
        # Formula Information
        sections.append("\n" + "=" * 80)
        sections.append("FORMULA INFORMATION")
        sections.append("=" * 80)
        
        if formula.get('name'):
            sections.append(f"\nFormula Name: {formula.get('name')}")
        if formula.get('complexity'):
            sections.append(f"Complexity: {formula.get('complexity', '').title()}")
        if formula.get('product_type'):
            product_type = formula.get('product_type', {})
            if isinstance(product_type, dict):
                sections.append(f"Product Type: {product_type.get('name', 'N/A')}")
        if formula.get('texture'):
            texture = formula.get('texture', {})
            if isinstance(texture, dict):
                sections.append(f"Texture: {texture.get('label', 'N/A')}")
        
        # Phases (new format)
        if formula.get('phases'):
            sections.append("\nFormula Phases:")
            for phase in formula.get('phases', []):
                phase_name = phase.get('name', 'Unknown Phase')
                phase_order = phase.get('order', 0)
                ingredients = phase.get('ingredients', [])
                sections.append(f"\n  Phase {phase_order}: {phase_name}")
                sections.append(f"    Ingredients ({len(ingredients)}):")
                for ing in ingredients:
                    name = ing.get('display_name', ing.get('name', 'Unknown'))
                    inci = ing.get('inci_name', '')
                    percent = ing.get('percentage', 'N/A')
                    phase_letter = ing.get('phase', '')
                    purpose = ing.get('purpose', '')
                    is_hero = "⭐ HERO" if ing.get('is_hero', False) else ""
                    sections.append(f"      • {name} {is_hero} - {percent} ({phase_letter})")
                    if inci:
                        sections.append(f"        INCI: {inci}")
                    if purpose:
                        sections.append(f"        Purpose: {purpose}")
        
        # Hero Ingredients (new format)
        if formula.get('hero_ingredients'):
            sections.append("\nHero Ingredients:")
            for hero in formula.get('hero_ingredients', []):
                name = hero.get('name', 'Unknown')
                percent = hero.get('percentage', 'N/A')
                why = hero.get('why_included', '')
                sections.append(f"  • {name} ({percent})")
                if why:
                    sections.append(f"    Why: {why}")
        
        # Formula Summary
        if formula.get('total_ingredients'):
            sections.append(f"\nTotal Ingredients: {formula.get('total_ingredients', 0)}")
        if formula.get('total_hero_actives'):
            sections.append(f"Hero Actives: {formula.get('total_hero_actives', 0)}")
        if formula.get('available_claims'):
            claims = formula.get('available_claims', [])
            if claims:
                sections.append(f"Available Claims: {', '.join([str(c) for c in claims])}")
        if formula.get('exclusions_met'):
            exclusions = formula.get('exclusions_met', [])
            if exclusions:
                sections.append(f"Exclusions Met: {', '.join([str(e) for e in exclusions])}")
        
        # Insights (new format)
        if insights:
            sections.append("\n" + "=" * 80)
            sections.append("FORMULA INSIGHTS")
            sections.append("=" * 80)
            
            # Why These Ingredients
            if insights.get('why_these_ingredients'):
                sections.append("\nWhy These Ingredients:")
                for why_ing in insights.get('why_these_ingredients', []):
                    name = why_ing.get('ingredient_name', 'Unknown')
                    explanation = why_ing.get('explanation', '')
                    complexity_reason = why_ing.get('complexity_reason', '')
                    sections.append(f"  • {name}: {explanation}")
                    if complexity_reason:
                        sections.append(f"    Complexity Note: {complexity_reason}")
            
            # Challenges
            if insights.get('challenges'):
                sections.append("\nPotential Challenges:")
                for challenge in insights.get('challenges', []):
                    title = challenge.get('title', '')
                    description = challenge.get('description', '')
                    tip = challenge.get('tip', '')
                    severity = challenge.get('severity', 'info').upper()
                    sections.append(f"  [{severity}] {title}")
                    if description:
                        sections.append(f"    Description: {description}")
                    if tip:
                        sections.append(f"    Tip: {tip}")
            
            # Marketing Tips
            if insights.get('marketing_tips'):
                sections.append("\nMarketing Tips:")
                for tip in insights.get('marketing_tips', []):
                    title = tip.get('title', '')
                    content = tip.get('content', '')
                    category = tip.get('category', '').title()
                    sections.append(f"  [{category}] {title}")
                    if content:
                        sections.append(f"    {content}")
            
            # FAQ
            if insights.get('faq'):
                sections.append("\nFrequently Asked Questions:")
                for faq in insights.get('faq', []):
                    question = faq.get('question', '')
                    answer = faq.get('answer', '')
                    sections.append(f"  Q: {question}")
                    if answer:
                        sections.append(f"  A: {answer}")
    
    # Stage 1: Ingredient Selection (old format)
    sections.append("\n" + "=" * 80)
    sections.append("STAGE 1: INGREDIENT SELECTION")
    sections.append("=" * 80)
    
    ingredient_selection = wish_response.get("ingredient_selection") or {}
    # Ensure ingredient_selection is a dict (handle None case)
    if not isinstance(ingredient_selection, dict):
        ingredient_selection = {}
    if 'ingredients' in ingredient_selection:
        sections.append(f"\nTotal Ingredients Selected: {len(ingredient_selection['ingredients'])}")
        sections.append("\nSelected Ingredients:")
        for idx, ing in enumerate(ingredient_selection['ingredients'], 1):
            name = ing.get('ingredient_name', 'Unknown')
            inci = ing.get('inci_name', '')
            percent = ing.get('recommended_percent', 0)
            function = ing.get('functional_category', '')
            phase = ing.get('phase', '')
            is_hero = "⭐ HERO" if ing.get('is_hero', False) else ""
            is_active = "🔬 ACTIVE" if ing.get('is_active', False) else ""
            
            sections.append(f"\n{idx}. {name} {is_hero} {is_active}")
            if inci:
                sections.append(f"   INCI: {inci}")
            if percent:
                sections.append(f"   Recommended: {percent}%")
            if function:
                sections.append(f"   Function: {function}")
            if phase:
                sections.append(f"   Phase: {phase}")
            if ing.get('notes'):
                sections.append(f"   Notes: {ing.get('notes')}")
    
    # Formula Name and Type
    if ingredient_selection.get('formula_name'):
        sections.append(f"\nSuggested Formula Name: {ingredient_selection.get('formula_name')}")
    if ingredient_selection.get('formula_type'):
        sections.append(f"Formula Type: {ingredient_selection.get('formula_type', 'N/A')}")
    
    # Target pH
    if ingredient_selection.get('target_ph'):
        ph_info = ingredient_selection.get('target_ph', {})
        sections.append(f"Target pH Range: {ph_info.get('min', '')} - {ph_info.get('max', '')}")
    
    # Phases Information
    if ingredient_selection.get('phases'):
        sections.append("\nManufacturing Phases:")
        for phase in ingredient_selection.get('phases', []):
            sections.append(f"  Phase {phase.get('id', '')}: {phase.get('name', '')}")
            sections.append(f"    Process Temp: {phase.get('process_temp', 'N/A')}")
            sections.append(f"    Instructions: {phase.get('instructions', 'N/A')}")
            if phase.get('ingredient_names'):
                ing_names = phase.get('ingredient_names', [])
                if ing_names and isinstance(ing_names, list):
                    if ing_names and isinstance(ing_names[0], dict):
                        ing_names_str = ', '.join([str(ing.get('name', ing.get('ingredient', ing))) for ing in ing_names if ing])
                    else:
                        ing_names_str = ', '.join([str(ing) for ing in ing_names if ing])
                    sections.append(f"    Ingredients: {ing_names_str}")
    
    # Insights
    if ingredient_selection.get('insights'):
        sections.append("\nKey Insights:")
        for insight in ingredient_selection.get('insights', []):
            icon = insight.get('icon', '•')
            category = insight.get('category', '')
            title = insight.get('title', '')
            text = insight.get('text', '')
            sections.append(f"  {icon} [{category.upper()}] {title}: {text}")
    
    # Warnings
    if ingredient_selection.get('warnings'):
        sections.append("\nWarnings:")
        for warning in ingredient_selection.get('warnings', []):
            severity = warning.get('severity', 'info').upper()
            category = warning.get('category', '')
            text = warning.get('text', '')
            solution = warning.get('solution', '')
            sections.append(f"  [{severity}] [{category.upper()}] {text}")
            if solution:
                sections.append(f"    Solution: {solution}")
    
    # Ingredient Synergies
    if ingredient_selection.get('ingredient_synergies'):
        sections.append("\nIngredient Synergies:")
        for synergy in ingredient_selection.get('ingredient_synergies', []):
            ingredients = synergy.get('ingredients', [])
            benefit = synergy.get('benefit', '')
            if ingredients and isinstance(ingredients, list):
                if ingredients and isinstance(ingredients[0], dict):
                    ing_str = ', '.join([str(ing.get('name', ing.get('ingredient', ing))) for ing in ingredients if ing])
                else:
                    ing_str = ', '.join([str(ing) for ing in ingredients if ing])
                sections.append(f"  {ing_str}: {benefit}")
            else:
                sections.append(f"  {str(ingredients)}: {benefit}")
    
    # Ingredient Conflicts
    if ingredient_selection.get('ingredient_conflicts'):
        sections.append("\nIngredient Conflicts:")
        for conflict in ingredient_selection.get('ingredient_conflicts', []):
            ingredients = conflict.get('ingredients', [])
            issue = conflict.get('issue', '')
            solution = conflict.get('solution', '')
            if ingredients and isinstance(ingredients, list):
                if ingredients and isinstance(ingredients[0], dict):
                    ing_str = ', '.join([str(ing.get('name', ing.get('ingredient', ing))) for ing in ingredients if ing])
                else:
                    ing_str = ', '.join([str(ing) for ing in ingredients if ing])
                sections.append(f"  {ing_str}: {issue}")
            else:
                sections.append(f"  {str(ingredients)}: {issue}")
            if solution:
                sections.append(f"    Solution: {solution}")
    
    # Reasoning
    if ingredient_selection.get('reasoning'):
        sections.append("\nSelection Reasoning:")
        sections.append(f"  {ingredient_selection.get('reasoning', '')}")
    
    # Stage 2: Optimized Formula
    # Skip if we already handled formula_result or basic_mode_result format
    if not has_formula_result and not has_basic_mode_result:
        sections.append("\n" + "=" * 80)
        sections.append("STAGE 2: OPTIMIZED FORMULA")
        sections.append("=" * 80)
    
    optimized_formula = wish_response.get("optimized_formula") or {}
    # Ensure optimized_formula is a dict (handle None case)
    if not isinstance(optimized_formula, dict):
        optimized_formula = {}
        
        # For new format, optimized_formula might be empty or have different structure
        # Check if we have formula data from new format
        if is_new_format and formula:
            # Extract from new format structure
            if formula.get('name'):
                sections.append(f"\nFormula Name: {formula.get('name')}")
            if formula.get('complexity'):
                sections.append(f"Complexity: {formula.get('complexity', '').title()}")
            
            # Calculate total percentage from phases
            if formula.get('phases'):
                total_percent = 0
                sections.append("\nOptimized Ingredient Percentages:")
                sections.append("-" * 80)
                sections.append(f"{'Ingredient':<40} {'Percentage':<15} {'Phase':<10} {'Purpose':<15}")
                sections.append("-" * 80)
                
                for phase in formula.get('phases', []):
                    phase_name = phase.get('name', '')
                    phase_order = phase.get('order', 0)
                    for ing in phase.get('ingredients', []):
                        name = ing.get('display_name', ing.get('name', 'Unknown'))
                        percent_str = ing.get('percentage', '0%')
                        phase_letter = ing.get('phase', str(phase_order))
                        purpose = ing.get('purpose', '')
                        
                        # Try to extract numeric value for total calculation
                        try:
                            percent_val = float(percent_str.replace('%', '').replace('q.s.', '0').strip())
                            total_percent += percent_val
                        except:
                            pass
                        
                        sections.append(f"{name:<40} {percent_str:<15} {phase_letter:<10} {purpose:<15}")
                
                if total_percent > 0:
                    sections.append("-" * 80)
                    sections.append(f"Total Percentage: {total_percent:.2f}%")
        else:
            # Old format handling
            formula_info = optimized_formula.get("optimized_formula", {}) if isinstance(optimized_formula, dict) else {}
    # Ensure formula_info is a dict
    if not isinstance(formula_info, dict):
        formula_info = {}
    
    if formula_info.get('name'):
        sections.append(f"\nFormula Name: {formula_info.get('name')}")
    if formula_info.get('total_percentage'):
        sections.append(f"Total Percentage: {formula_info.get('total_percentage')}%")
    if formula_info.get('estimated_cost_per_g'):
        sections.append(f"Estimated Cost: ₹{formula_info.get('estimated_cost_per_g')}/g")
    if formula_info.get('target_ph'):
        ph_range = formula_info.get('target_ph', {})
        sections.append(f"Target pH: {ph_range.get('min', '')} - {ph_range.get('max', '')}")
    
    if 'ingredients' in optimized_formula:
        sections.append("\nOptimized Ingredient Percentages:")
        sections.append("-" * 80)
        sections.append(f"{'Ingredient':<40} {'Percentage':<15} {'Phase':<10} {'Function':<15}")
        sections.append("-" * 80)
        for ing in optimized_formula['ingredients']:
            name = ing.get('name', 'Unknown')
            percent = ing.get('percent', 0)
            phase = ing.get('phase', '')
            function = ing.get('function', '')
            sections.append(f"{name:<40} {percent:<15}% {phase:<10} {function:<15}")
    
            # Cost Breakdown (old format only)
    if optimized_formula.get('cost_breakdown'):
        cost_breakdown = optimized_formula.get('cost_breakdown', {})
        sections.append("\nCost Breakdown:")
        sections.append(f"  Total per g: ₹{cost_breakdown.get('total_per_g', 0)}")
        sections.append(f"  Actives: ₹{cost_breakdown.get('actives_cost', 0)}")
        sections.append(f"  Base: ₹{cost_breakdown.get('base_cost', 0)}")
        sections.append(f"  Functional: ₹{cost_breakdown.get('functional_cost', 0)}")
        sections.append(f"  Preservation: ₹{cost_breakdown.get('preservation_cost', 0)}")
        if cost_breakdown.get('cost_vs_target'):
            sections.append(f"  Cost vs Target: {cost_breakdown.get('cost_vs_target', 'N/A')}")
    
            # Phase Summary (old format only)
    if optimized_formula.get('phase_summary'):
        sections.append("\nPhase Summary:")
        for phase_sum in optimized_formula.get('phase_summary', []):
            sections.append(f"  Phase {phase_sum.get('phase', '')}: {phase_sum.get('name', '')} - {phase_sum.get('total_percent', 0)}% ({phase_sum.get('ingredients_count', 0)} ingredients)")
    
            # Insights from Optimized Formula (old format only)
    if optimized_formula.get('insights'):
        sections.append("\nOptimization Insights:")
        for insight in optimized_formula.get('insights', []):
            icon = insight.get('icon', '•')
            title = insight.get('title', '')
            text = insight.get('text', '')
            sections.append(f"  {icon} {title}: {text}")
    
            # Warnings from Optimized Formula (old format only)
    if optimized_formula.get('warnings'):
        sections.append("\nOptimization Warnings:")
        for warning in optimized_formula.get('warnings', []):
            severity = warning.get('severity', 'info').upper()
            text = warning.get('text', '')
            affected = warning.get('affected_ingredients', [])
            solution = warning.get('solution', '')
            sections.append(f"  [{severity}] {text}")
            if affected:
                if affected and isinstance(affected, list):
                    if affected and isinstance(affected[0], dict):
                        affected_str = ', '.join([str(a.get('name', a.get('ingredient', a))) for a in affected if a])
                    else:
                        affected_str = ', '.join([str(a) for a in affected if a])
                    sections.append(f"    Affected Ingredients: {affected_str}")
                else:
                    sections.append(f"    Affected Ingredients: {str(affected)}")
            if solution:
                sections.append(f"    Solution: {solution}")
    
            # Stability Notes (old format only)
    if optimized_formula.get('stability_notes'):
        sections.append("\nStability Notes:")
        for note in optimized_formula.get('stability_notes', []):
            sections.append(f"  • {note}")
    
            # pH Adjustment (old format only)
    if optimized_formula.get('ph_adjustment'):
        ph_adj = optimized_formula.get('ph_adjustment', {})
        sections.append("\npH Adjustment:")
        sections.append(f"  Expected Initial pH: {ph_adj.get('expected_initial_ph', 'N/A')}")
        sections.append(f"  Target pH: {ph_adj.get('target_ph', 'N/A')}")
        sections.append(f"  Adjuster: {ph_adj.get('adjuster', 'N/A')}")
        sections.append(f"  Estimated Amount: {ph_adj.get('estimated_amount', 'N/A')}")
    
    # Stage 3: Manufacturing Process
    # Skip if we already handled formula_result or basic_mode_result format
    if not has_formula_result and not has_basic_mode_result:
        sections.append("\n" + "=" * 80)
        sections.append("STAGE 3: MANUFACTURING PROCESS")
        sections.append("=" * 80)
    
    manufacturing = wish_response.get("manufacturing") or {}
    # Ensure manufacturing is a dict (handle None case)
    if not isinstance(manufacturing, dict):
        manufacturing = {}
    if manufacturing.get('process_type'):
        sections.append(f"\nProcess Type: {manufacturing.get('process_type', '').title()}")
    if manufacturing.get('difficulty_level'):
        sections.append(f"Difficulty Level: {manufacturing.get('difficulty_level', '').title()}")
    if manufacturing.get('estimated_time'):
        time_info = manufacturing.get('estimated_time', {})
        sections.append(f"Lab Scale (100g): {time_info.get('lab_scale_100g', 'N/A')}")
        sections.append(f"Pilot Scale (5kg): {time_info.get('pilot_scale_5kg', 'N/A')}")
    
    if 'manufacturing_steps' in manufacturing:
        sections.append("\nManufacturing Steps:")
        for step in manufacturing['manufacturing_steps']:
            step_num = step.get('step_number', '')
            title = step.get('title', '')
            phase = step.get('phase', '')
            temp = step.get('temperature', '')
            duration = step.get('duration', '')
            
            sections.append(f"\nStep {step_num}: {title}")
            if phase:
                sections.append(f"  Phase: {phase}")
            if temp:
                sections.append(f"  Temperature: {temp}")
            if duration:
                sections.append(f"  Duration: {duration}")
            if step.get('ingredients'):
                sections.append(f"  Ingredients: {', '.join(step.get('ingredients', []))}")
            if step.get('instructions'):
                for instruction in step.get('instructions', []):
                    sections.append(f"    • {instruction}")
    
    # Equipment
    if manufacturing.get('equipment_needed'):
        equipment = manufacturing.get('equipment_needed', {})
        if equipment.get('essential'):
            sections.append("\nEssential Equipment:")
            for item in equipment.get('essential', []):
                sections.append(f"  • {item.get('item', '')}: {item.get('purpose', '')}")
        if equipment.get('recommended'):
            sections.append("\nRecommended Equipment:")
            for item in equipment.get('recommended', []):
                sections.append(f"  • {item.get('item', '')}: {item.get('purpose', '')}")
    
    # Critical Parameters
    if manufacturing.get('critical_parameters'):
        sections.append("\nCritical Parameters:")
        for param in manufacturing.get('critical_parameters', []):
            sections.append(f"  {param.get('parameter', '')} ({param.get('stage', '')}):")
            sections.append(f"    Target: {param.get('target', 'N/A')}")
            sections.append(f"    Method: {param.get('method', 'N/A')}")
            if param.get('adjustment'):
                sections.append(f"    Adjustment: {param.get('adjustment', 'N/A')}")
    
    # Troubleshooting
    if manufacturing.get('troubleshooting'):
        sections.append("\nTroubleshooting Guide:")
        for issue in manufacturing.get('troubleshooting', []):
            sections.append(f"  Issue: {issue.get('issue', 'N/A')}")
            sections.append(f"    Cause: {issue.get('cause', 'N/A')}")
            sections.append(f"    Solution: {issue.get('solution', 'N/A')}")
    
    # Packaging Guidelines
    if manufacturing.get('packaging_guidelines'):
        pkg = manufacturing.get('packaging_guidelines', {})
        sections.append("\nPackaging Guidelines:")
        if pkg.get('recommended_packaging'):
            rec_pkg = pkg.get('recommended_packaging', [])
            if rec_pkg and isinstance(rec_pkg, list):
                if rec_pkg and isinstance(rec_pkg[0], dict):
                    rec_pkg_str = ', '.join([str(p.get('name', p.get('packaging', p))) for p in rec_pkg if p])
                else:
                    rec_pkg_str = ', '.join([str(p) for p in rec_pkg if p])
                sections.append(f"  Recommended: {rec_pkg_str}")
        if pkg.get('avoid'):
            avoid_pkg = pkg.get('avoid', [])
            if avoid_pkg and isinstance(avoid_pkg, list):
                if avoid_pkg and isinstance(avoid_pkg[0], dict):
                    avoid_pkg_str = ', '.join([str(p.get('name', p.get('packaging', p))) for p in avoid_pkg if p])
                else:
                    avoid_pkg_str = ', '.join([str(p) for p in avoid_pkg if p])
                sections.append(f"  Avoid: {avoid_pkg_str}")
        if pkg.get('fill_temperature'):
            sections.append(f"  Fill Temperature: {pkg.get('fill_temperature', 'N/A')}")
        if pkg.get('storage'):
            sections.append(f"  Storage: {pkg.get('storage', 'N/A')}")
    
    # Quality Control
    if manufacturing.get('quality_control'):
        qc = manufacturing.get('quality_control', {})
        sections.append("\nQuality Control:")
        if qc.get('in_process'):
            sections.append("  In-Process Checks:")
            for check in qc.get('in_process', []):
                sections.append(f"    • {check}")
        if qc.get('final_product'):
            sections.append("  Final Product Checks:")
            for check in qc.get('final_product', []):
                sections.append(f"    • {check}")
    
    # Scale Up Notes
    if manufacturing.get('scale_up_notes'):
        sections.append("\nScale-Up Notes:")
        for note in manufacturing.get('scale_up_notes', []):
            sections.append(f"  • {note}")
    
    # Safety Precautions
    if manufacturing.get('safety_precautions'):
        sections.append("\nSafety Precautions:")
        for precaution in manufacturing.get('safety_precautions', []):
            sections.append(f"  • {precaution}")
    
    # Stage 4: Cost Analysis
    # Skip if we already handled formula_result or basic_mode_result format (cost info already included)
    if not has_formula_result and not has_basic_mode_result:
        sections.append("\n" + "=" * 80)
        sections.append("STAGE 4: COST ANALYSIS")
        sections.append("=" * 80)
    
    cost_analysis = wish_response.get("cost_analysis") or {}
    # Ensure cost_analysis is a dict (handle None case)
    if not isinstance(cost_analysis, dict):
        cost_analysis = {}
    
    # Raw Material Cost
    if cost_analysis.get('raw_material_cost'):
        rm_cost = cost_analysis.get('raw_material_cost', {})
        sections.append("\nRaw Material Cost:")
        sections.append(f"  Total per g: ₹{rm_cost.get('total_per_g', 0)}")
        sections.append(f"  Total per 100g: ₹{rm_cost.get('total_per_100g', 0)}")
        
        if rm_cost.get('breakdown_by_category'):
            breakdown = rm_cost.get('breakdown_by_category', {})
            sections.append("\n  Breakdown by Category:")
            sections.append(f"    Actives: ₹{breakdown.get('actives', 0)}")
            sections.append(f"    Base: ₹{breakdown.get('base_ingredients', 0)}")
            sections.append(f"    Functional: ₹{breakdown.get('functional_ingredients', 0)}")
            sections.append(f"    Preservatives: ₹{breakdown.get('preservatives', 0)}")
    
    # Cost Estimate with ranges
    if cost_analysis.get('cost_estimate'):
        cost_est = cost_analysis.get('cost_estimate', {})
        if cost_est.get('raw_material_per_g'):
            per_g = cost_est.get('raw_material_per_g', {})
            sections.append("\nCost Estimate (per g):")
            sections.append(f"  Optimistic: ₹{per_g.get('optimistic', 0)}")
            sections.append(f"  Realistic: ₹{per_g.get('realistic', 0)}")
            sections.append(f"  Conservative: ₹{per_g.get('conservative', 0)}")
            sections.append(f"  Range: {per_g.get('display_range', 'N/A')}")
            sections.append(f"  Confidence: {per_g.get('confidence', 'N/A').title()}")
    
    # Total Product Cost
    if cost_analysis.get('total_product_cost'):
        total_cost = cost_analysis.get('total_product_cost', {})
        if total_cost.get('with_packaging_per_unit'):
            sections.append("\nTotal Product Cost (with packaging):")
            for size, cost_data in total_cost.get('with_packaging_per_unit', {}).items():
                sections.append(f"  {size}: ₹{cost_data.get('total', 0)}")
                sections.append(f"    - Formula: ₹{cost_data.get('formula_cost', 0)}")
                sections.append(f"    - Packaging: ₹{cost_data.get('packaging_cost', 0)}")
                sections.append(f"    - Labelling: ₹{cost_data.get('labelling_cost', 0)}")
                sections.append(f"    - Carton: ₹{cost_data.get('carton_box_cost', 0)}")
    
    # Top Cost Drivers
    if cost_analysis.get('raw_material_cost', {}).get('top_cost_drivers'):
        sections.append("\nTop Cost Drivers:")
        for driver in cost_analysis.get('raw_material_cost', {}).get('top_cost_drivers', []):
            sections.append(f"  {driver.get('ingredient', '')}: ₹{driver.get('cost', 0)} ({driver.get('percentage', 0)}%) - {driver.get('contribution', '')} of total")
    
    # Cost Estimate Details
    if cost_analysis.get('cost_estimate'):
        cost_est = cost_analysis.get('cost_estimate', {})
        if cost_est.get('raw_material_per_100g'):
            per_100g = cost_est.get('raw_material_per_100g', {})
            sections.append("\nCost Estimate (per 100g):")
            sections.append(f"  Optimistic: ₹{per_100g.get('optimistic', 0)}")
            sections.append(f"  Realistic: ₹{per_100g.get('realistic', 0)}")
            sections.append(f"  Conservative: ₹{per_100g.get('conservative', 0)}")
            sections.append(f"  Range: {per_100g.get('display_range', 'N/A')}")
        
        # Confidence Breakdown
        if cost_est.get('confidence_breakdown'):
            conf = cost_est.get('confidence_breakdown', {})
            sections.append("\nConfidence Breakdown:")
            if conf.get('high_confidence_ingredients'):
                high = conf.get('high_confidence_ingredients', {})
                sections.append(f"  High Confidence: {high.get('count', 0)} ingredients, ₹{high.get('cost_contribution', 0)} ({high.get('percentage_of_total', '0%')})")
            if conf.get('medium_confidence_ingredients'):
                med = conf.get('medium_confidence_ingredients', {})
                sections.append(f"  Medium Confidence: {med.get('count', 0)} ingredients, ₹{med.get('cost_contribution', 0)} ({med.get('percentage_of_total', '0%')})")
            if conf.get('low_confidence_ingredients'):
                low = conf.get('low_confidence_ingredients', {})
                sections.append(f"  Low Confidence: {low.get('count', 0)} ingredients, ₹{low.get('cost_contribution', 0)} ({low.get('percentage_of_total', '0%')})")
                if low.get('names'):
                    low_names = low.get('names', [])
                    if low_names and isinstance(low_names, list):
                        if low_names and isinstance(low_names[0], dict):
                            low_names_str = ', '.join([str(n.get('name', n.get('ingredient', n))) for n in low_names if n])
                        else:
                            low_names_str = ', '.join([str(n) for n in low_names if n])
                        sections.append(f"    Ingredients: {low_names_str}")
                    else:
                        sections.append(f"    Ingredients: {str(low_names)}")
                if low.get('recommendation'):
                    sections.append(f"    Recommendation: {low.get('recommendation', '')}")
        
        # Top Cost Drivers (detailed)
        if cost_est.get('top_cost_drivers'):
            sections.append("\nDetailed Top Cost Drivers:")
            for driver in cost_est.get('top_cost_drivers', []):
                sections.append(f"  {driver.get('ingredient', '')}:")
                sections.append(f"    Percentage in Formula: {driver.get('percentage_in_formula', 0)}%")
                sections.append(f"    Cost per kg Range: {driver.get('cost_per_kg_range', 'N/A')}")
                sections.append(f"    Cost per g Range: {driver.get('cost_per_g_range', 'N/A')}")
                sections.append(f"    Share of Total: {driver.get('share_of_total', 'N/A')}")
                sections.append(f"    Confidence: {driver.get('confidence', 'N/A').title()}")
                if driver.get('note'):
                    sections.append(f"    Note: {driver.get('note', '')}")
        
        # Disclaimers
        if cost_est.get('disclaimers'):
            sections.append("\nCost Estimation Disclaimers:")
            for disclaimer in cost_est.get('disclaimers', []):
                sections.append(f"  • {disclaimer}")
    
    # Packaging Estimate
    if cost_analysis.get('packaging_estimate'):
        sections.append("\nPackaging Options:")
        for option_key, option_data in cost_analysis.get('packaging_estimate', {}).items():
            sections.append(f"  {option_data.get('type', option_key)}:")
            sections.append(f"    Packaging: ₹{option_data.get('packaging_cost', 0)}")
            sections.append(f"    Labelling: ₹{option_data.get('labelling_cost', 0)}")
            sections.append(f"    Carton: ₹{option_data.get('carton_box_cost', 0)}")
            sections.append(f"    Total: ₹{option_data.get('total_packaging_cost', 0)}")
            sections.append(f"    Total Unit Cost: ₹{option_data.get('total_unit', 0)}")
    
    # Total Product Cost with Overhead
    if cost_analysis.get('total_product_cost', {}).get('with_overhead_20_percent'):
        sections.append("\nTotal Product Cost (with 20% Manufacturing Overhead):")
        for size, cost_data in cost_analysis.get('total_product_cost', {}).get('with_overhead_20_percent', {}).items():
            sections.append(f"  {size}:")
            sections.append(f"    Subtotal: ₹{cost_data.get('subtotal_before_overhead', 0)}")
            sections.append(f"    Overhead (20%): ₹{cost_data.get('manufacturing_overhead_20_percent', 0)}")
            sections.append(f"    Total: ₹{cost_data.get('total', 0)}")
    
    # Pricing Recommendations
    if cost_analysis.get('pricing_recommendations'):
        pricing = cost_analysis.get('pricing_recommendations', {})
        sections.append("\nPricing Recommendations:")
        if pricing.get('d2c_mrp_5x'):
            sections.append("\n  D2C MRP (5x markup):")
            for size, price in pricing.get('d2c_mrp_5x', {}).items():
                sections.append(f"    {size}: ₹{price}")
        if pricing.get('retail_mrp_6x'):
            sections.append("\n  Retail MRP (6x markup):")
            for size, price in pricing.get('retail_mrp_6x', {}).items():
                sections.append(f"    {size}: ₹{price}")
        if pricing.get('premium_positioning_8x'):
            sections.append("\n  Premium Positioning (8x markup):")
            for size, price in pricing.get('premium_positioning_8x', {}).items():
                sections.append(f"    {size}: ₹{price}")
    
    # Cost Optimization Suggestions
    if cost_analysis.get('cost_optimization_suggestions'):
        sections.append("\nCost Optimization Suggestions:")
        for suggestion in cost_analysis.get('cost_optimization_suggestions', []):
            sections.append(f"  • {suggestion.get('suggestion', '')}")
            sections.append(f"    Savings: {suggestion.get('savings', 'N/A')}")
            sections.append(f"    Impact: {suggestion.get('impact', 'N/A')}")
    
    # Competitor Comparison
    if cost_analysis.get('competitor_comparison'):
        comp = cost_analysis.get('competitor_comparison', {})
        sections.append("\nCompetitor Comparison:")
        if comp.get('similar_products'):
            sections.append("  Similar Products:")
            for product in comp.get('similar_products', []):
                sections.append(f"    {product.get('brand', '')} - {product.get('product', '')}:")
                sections.append(f"      MRP: ₹{product.get('mrp', 0)} ({product.get('size', 'N/A')})")
                sections.append(f"      Price per {product.get('size_unit', 'unit')}: {product.get('price_per_unit_display', 'N/A')}")
                if product.get('advantage'):
                    sections.append(f"      Advantage: {product.get('advantage', '')}")
        if comp.get('your_product'):
            your_prod = comp.get('your_product', {})
            sections.append("  Your Product:")
            sections.append(f"    Recommended MRP: ₹{your_prod.get('recommended_mrp', 0)} ({your_prod.get('size', 'N/A')})")
            sections.append(f"    Price per {your_prod.get('size_unit', 'unit')}: {your_prod.get('price_per_unit_display', 'N/A')}")
        if comp.get('competitive_position'):
            sections.append(f"  Competitive Position: {comp.get('competitive_position', 'N/A')}")
        if comp.get('advantages'):
            sections.append("  Advantages:")
            for adv in comp.get('advantages', []):
                sections.append(f"    • {adv.get('competitor_brand', '')}: {adv.get('advantage', '')}")
    
    # Validation Report
    if cost_analysis.get('validation_report'):
        val = cost_analysis.get('validation_report', {})
        sections.append("\nCost Validation Report:")
        sections.append(f"  Water Cost Check: {val.get('water_cost_check', 'N/A')}")
        sections.append(f"  Total vs Benchmark: {val.get('total_vs_benchmark', 'N/A')}")
        sections.append(f"  Active Cost Ratio: {val.get('active_cost_ratio', 'N/A')}")
        sections.append(f"  MRP Plausibility: {val.get('mrp_plausibility', 'N/A')}")
        sections.append(f"  Ingredient Ratio Check: {val.get('ingredient_ratio_check', 'N/A')}")
        sections.append(f"  Competitor Alignment: {val.get('competitor_alignment', 'N/A')}")
        sections.append(f"  Overall Confidence: {val.get('overall_confidence', 'N/A').upper()}")
        if val.get('flags'):
            sections.append("  Flags:")
            for flag in val.get('flags', []):
                sections.append(f"    ⚠️ {flag}")
    
    # Stage 5: Compliance
    # Skip if we already handled formula_result or basic_mode_result format (compliance already included)
    if not has_formula_result and not has_basic_mode_result:
        sections.append("\n" + "=" * 80)
        sections.append("STAGE 5: COMPLIANCE CHECK")
        sections.append("=" * 80)
    
    compliance = wish_response.get("compliance") or {}
    # Ensure compliance is a dict (handle None case)
    if not isinstance(compliance, dict):
        compliance = {}
    sections.append(f"\nOverall Status: {compliance.get('overall_status', 'N/A') if isinstance(compliance, dict) else 'N/A'}")
    
    # BIS Compliance
    if compliance.get('bis_compliance'):
        bis = compliance.get('bis_compliance', {})
        sections.append(f"\nBIS (India) Compliance: {bis.get('status', 'N/A')}")
        if bis.get('issues'):
            sections.append("  Issues:")
            for issue in bis.get('issues', []):
                sections.append(f"    • {issue}")
        if bis.get('warnings'):
            sections.append("  Warnings:")
            for warning in bis.get('warnings', []):
                sections.append(f"    • {warning}")
    
    # EU Compliance
    if compliance.get('eu_compliance'):
        eu = compliance.get('eu_compliance', {})
        sections.append(f"\nEU Compliance: {eu.get('status', 'N/A')}")
        if eu.get('warnings'):
            sections.append("  Warnings:")
            for warning in eu.get('warnings', []):
                if isinstance(warning, dict):
                    sections.append(f"    • {warning.get('ingredient', '')}: {warning.get('concern', '')}")
                else:
                    sections.append(f"    • {warning}")
    
    # FDA Compliance
    if compliance.get('fda_compliance'):
        fda = compliance.get('fda_compliance', {})
        sections.append(f"\nFDA (US) Compliance: {fda.get('status', 'N/A')}")
    
    # Required Warnings
    if compliance.get('required_warnings'):
        sections.append("\nRequired Warnings:")
        for warning in compliance.get('required_warnings', []):
            sections.append(f"  • {warning}")
    
    # Ingredient Status
    if compliance.get('ingredient_status'):
        sections.append("\nIngredient Compliance Status:")
        for ing_status in compliance.get('ingredient_status', []):
            sections.append(f"  {ing_status.get('ingredient', '')}:")
            sections.append(f"    BIS: {ing_status.get('bis', 'N/A')}")
            sections.append(f"    EU: {ing_status.get('eu', 'N/A')}")
            sections.append(f"    FDA: {ing_status.get('fda', 'N/A')}")
            sections.append(f"    Concentration: {ing_status.get('concentration', 'N/A')}")
            sections.append(f"    Limit: {ing_status.get('limit', 'N/A')}")
            sections.append(f"    Status: {ing_status.get('status', 'N/A')}")
    
    # Claims Guidance
    if compliance.get('claims_guidance'):
        claims = compliance.get('claims_guidance', {})
        sections.append("\nClaims Guidance:")
        if claims.get('allowed_claims'):
            sections.append("  Allowed Claims:")
            for claim in claims.get('allowed_claims', []):
                sections.append(f"    ✓ {claim}")
        if claims.get('claims_needing_substantiation'):
            sections.append("  Claims Needing Substantiation:")
            for claim in claims.get('claims_needing_substantiation', []):
                sections.append(f"    ⚠ {claim}")
        if claims.get('prohibited_claims'):
            sections.append("  Prohibited Claims:")
            for claim in claims.get('prohibited_claims', []):
                sections.append(f"    ✗ {claim}")
    
    # Recommendations
    if compliance.get('recommendations'):
        sections.append("\nCompliance Recommendations:")
        for rec in compliance.get('recommendations', []):
            sections.append(f"  • {rec}")
    
    # Metadata
    if wish_response.get('metadata'):
        sections.append("\n" + "=" * 80)
        sections.append("METADATA")
        sections.append("=" * 80)
        metadata = wish_response.get('metadata', {})
        if metadata.get('generated_at'):
            sections.append(f"Generated At: {metadata.get('generated_at', 'N/A')}")
        if metadata.get('processing_time'):
            sections.append(f"Processing Time: {metadata.get('processing_time', 'N/A')} seconds")
        if metadata.get('formula_version'):
            sections.append(f"Formula Version: {metadata.get('formula_version', 'N/A')}")
        if metadata.get('model_used'):
            sections.append(f"Model Used: {metadata.get('model_used', 'N/A')}")
        if metadata.get('stages_completed'):
            stages = metadata.get('stages_completed', [])
            if stages and isinstance(stages, list):
                stages_str = ', '.join([str(s) for s in stages if s])
                sections.append(f"Stages Completed: {stages_str}")
            else:
                sections.append(f"Stages Completed: N/A")
    
    # History ID
    if wish_response.get('history_id'):
        sections.append(f"\nHistory ID: {wish_response.get('history_id', 'N/A')}")
    
    sections.append("\n" + "=" * 80)
    sections.append("END OF COMPREHENSIVE WISH DATA REPORT")
    sections.append("=" * 80)
    sections.append("\nThis presentation includes ALL data from the Make a Wish 5-stage pipeline:")
    sections.append("1. Complete wish requirements and preferences")
    sections.append("2. Full ingredient selection with all details")
    sections.append("3. Complete optimized formula with all percentages and analysis")
    sections.append("4. Comprehensive manufacturing process with all steps and guidelines")
    sections.append("5. Detailed cost analysis with all pricing recommendations")
    sections.append("6. Complete compliance check with all regulatory information")
    sections.append("7. All metadata and additional information")
    
    return "\n".join(sections)


# ============================================================================
# EXPORT ENDPOINTS
# ============================================================================

@router.post("/export-to-inspiration-board")
async def export_make_wish_to_board(
    request: dict,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """Export make a wish formulations to inspiration board"""
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID not found in JWT token")
        
        board_id = request.get("board_id")
        history_ids = request.get("history_ids", [])
        
        if not board_id:
            raise HTTPException(status_code=400, detail="Board ID is required")
        
        if not history_ids:
            raise HTTPException(status_code=400, detail="At least one history ID is required")
        
        # Use the inspiration boards export endpoint
        from app.ai_ingredient_intelligence.models.inspiration_boards_schemas import (
            ExportToBoardRequest, ExportItemRequest
        )
        
        # Create export request
        export_request = ExportToBoardRequest(
            board_id=board_id,
            exports=[
                ExportItemRequest(
                    feature_type="make_wish",
                    history_ids=history_ids
                )
            ]
        )
        
        # Call the inspiration boards export endpoint
        from app.ai_ingredient_intelligence.api.inspiration_boards import export_to_board_endpoint
        result = await export_to_board_endpoint(export_request, background_tasks, current_user)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"ERROR exporting make a wish to board: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# MARKET TRENDS ENDPOINT
# ============================================================================

class MarketTrendsRequest(BaseModel):
    """Request schema for market trends fetching"""
    hero_ingredients: Optional[List[str]] = Field(default_factory=list, description="List of hero ingredient names")
    benefits: Optional[List[str]] = Field(default_factory=list, description="List of benefits")
    product_type: Optional[str] = Field(None, description="Product type (serum, cream, etc.)")
    category: str = Field("skincare", description="Category: skincare or haircare")
    max_age_days: int = Field(35, description="Maximum age of cached data in days")
    use_fallback: bool = Field(True, description="Whether to use SerpAPI if MongoDB has no data")


@router.post("/market-trends", response_model=None)
async def fetch_market_trends(
    request: MarketTrendsRequest,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Fetch market trends data for ingredients, benefits, and product type.
    
    This endpoint provides market intelligence data from MongoDB (batch data)
    with SerpAPI fallback if needed.
    
    REQUEST BODY:
    {
        "hero_ingredients": ["Vitamin C", "Niacinamide"],
        "benefits": ["brightening", "anti-aging"],
        "product_type": "serum",
        "category": "skincare",
        "max_age_days": 35,
        "use_fallback": true
    }
    
    RESPONSE:
    Formatted market trends data ready for frontend visualization:
    - ingredient_trends: Timeseries data, growth rates, related queries
    - benefit_trends: Competing approaches
    - competitive_landscape: Brand trends
    - regional_insights: Regional distribution
    - shopping_insights: Price ranges
    - key_insights: Generated insights
    """
    try:
        trends_service = MarketTrendsService()
        
        trends_data = await trends_service.fetch_trends_for_wish(
            hero_ingredients=request.hero_ingredients,
            benefits=request.benefits,
            product_type=request.product_type,
            category=request.category,
            max_age_days=request.max_age_days,
            use_fallback=request.use_fallback
        )
        
        return {
            "success": True,
            "data": trends_data,
            "timestamp": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()
        }
    
    except Exception as e:
        print(f"❌ Error fetching market trends: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching market trends: {str(e)}"
        )


# ============================================================================
# MAIN ENDPOINTS
# ============================================================================


@router.post("/generate", response_model=MakeWishResponse)
async def generate_make_wish_formula(
    request: MakeWishRequest,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Generate a cosmetic formulation using the complete 5-stage "Make a Wish" AI pipeline.
    
    AUTO-SAVE: Results are automatically saved to wish history if user is authenticated.
    Provide optional "name" and "tag" in request to customize the saved history item.
    
    REQUEST BODY:
    {
        "category": "skincare" or "haircare",
        "productType": "serum",
        "benefits": ["Brightening", "Hydration"],
        "exclusions": ["Silicone-free", "Paraben-free"],
        "heroIngredients": ["Niacinamide", "Hyaluronic Acid"],
        "costMin": 30,
        "costMax": 60,
        "texture": "lightweight",
        "claims": ["Vegan", "Dermatologist-tested"],
        "targetAudience": ["oily-skin", "young-adults"],
        "additionalNotes": "Additional requirements",
        "mode": "basic" or "advanced" (optional, default: "advanced"),
        "name": "Formula Name" (optional, for auto-saving),
        "tag": "optional-tag" (optional),
        "notes": "User notes" (optional),
        "history_id": "existing_history_id" (optional, to update existing history)
    }
    
    MODE OPTIONS:
    - "advanced" (default): Full 5-stage pipeline for formulators/scientists
    - "basic": Simplified flow for layman users with active ingredient options, business context, and simplified explanations
    
    RESPONSE:
    Complete formula with:
    - Ingredient selection
    - Optimized percentages
    - Manufacturing process
    - Cost analysis
    - Compliance check
    - history_id (if auto-saved)
    """
    start_time = time.time()
    
    # 🔹 Auto-save: Extract user info and required name/tag for history
    user_id_value = current_user.get("user_id") or current_user.get("_id")
    name = request.name.strip() if request.name else ""
    tag = request.tag
    notes = request.notes  # This is the notes field from MakeWishRequest (for history)
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
        wish_data = request.model_dump(exclude={"name", "tag", "notes", "history_id"})
        
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
        
        # Set defaults
        wish_data.setdefault("category", "skincare")
        wish_data.setdefault("texture", "lightweight")
        wish_data.setdefault("exclusions", [])
        wish_data.setdefault("heroIngredients", [])
        wish_data.setdefault("claims", [])
        wish_data.setdefault("targetAudience", [])
        wish_data.setdefault("additionalNotes", "")
        wish_data.setdefault("mode", "basic")  # Default to basic mode (advanced is deprecated)
        
        # Validate mode
        mode = wish_data.get("mode", "advanced").lower()
        if mode not in ["basic", "advanced"]:
            raise HTTPException(
                status_code=400,
                detail="mode must be either 'basic' or 'advanced'"
            )
        wish_data["mode"] = mode
        
        if wish_data.get("costMin") is None:
            wish_data["costMin"] = 30
        if wish_data.get("costMax") is None:
            wish_data["costMax"] = 60
        
        # Validate cost range
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
        
        # Validate using rules engine
        rules_engine = get_rules_engine()
        can_proceed, validation_results, fixed_wish_data = rules_engine.validate_wish_data(wish_data)
        
        if not can_proceed:
            blocking_errors = [r for r in validation_results if r.severity == ValidationSeverity.BLOCK]
            error_messages = [r.message for r in blocking_errors]
            raise HTTPException(
                status_code=400,
                detail=f"Validation failed: {'; '.join(error_messages)}"
            )
        
        # Use fixed wish data (with auto-selections applied)
        wish_data = fixed_wish_data
        
        # Log validation warnings
        warnings = [r for r in validation_results if r.severity == ValidationSeverity.WARN]
        if warnings:
            print(f"⚠️ Validation warnings: {len(warnings)}")
            for warning in warnings:
                print(f"   - {warning.message}")
        
        print(f"📝 Generating Make a Wish formula...")
        print(f"   Mode: {wish_data.get('mode', 'advanced').upper()}")
        print(f"   Category: {wish_data['category']}")
        print(f"   Product Type: {wish_data['productType']}")
        print(f"   Benefits: {', '.join(wish_data['benefits'])}")
        print(f"   Exclusions: {', '.join(wish_data.get('exclusions', []))}")
        print(f"   Hero Ingredients: {', '.join(wish_data.get('heroIngredients', []))}")
        print(f"   Cost Range: ₹{wish_data['costMin']} - ₹{wish_data['costMax']}/unit")
        
        # Create a unique identifier for the wish data to check for duplicates
        # Use a combination of key fields to identify similar wishes
        import json
        wish_data_for_comparison = {
            "category": wish_data.get("category"),
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
        
        # Generate formula - use basic mode (advanced is deprecated)
        try:
            mode = wish_data.get("mode", "basic").lower()
            if mode == "basic":
                # Basic mode - simplified flow
                basic_result = await generate_formula_basic_mode(wish_data)
                # Convert basic mode result to expected format
                result = {
                    "wish_data": wish_data,
                    "ingredient_selection": {},
                    "optimized_formula": {},
                    "manufacturing": {},
                    "cost_analysis": {},  # Cost is in businessNumbers.packagingOptions
                    "compliance": {},
                    "basic_mode_result": basic_result,
                    "metadata": {
                        "generated_at": datetime.now().isoformat(),
                        "formula_version": "1.0",
                        "mode": "basic"
                    }
                }
            else:
                # Advanced mode (deprecated but still supported)
                result = await generate_formula_from_wish(wish_data)
        except ValueError as ve:
            raise HTTPException(
                status_code=400,
                detail=f"Formula generation validation error: {str(ve)}"
            )
        except Exception as gen_error:
            print(f"❌ Error in generate_formula_from_wish: {gen_error}")
            import traceback
            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail=f"Error during formula generation: {str(gen_error)}"
            )
        
        # Validate response structure
        if not result or not isinstance(result, dict):
            raise HTTPException(
                status_code=500,
                detail="Invalid formula structure returned"
            )
        
        processing_time = time.time() - start_time
        print(f"✅ Make a Wish formula generated in {processing_time:.2f}s")
        
        # Extract key metrics
        optimized = result.get("optimized_formula", {})
        cost_analysis = result.get("cost_analysis", {})
        compliance = result.get("compliance", {})
        
        print(f"   Formula Cost: ₹{cost_analysis.get('raw_material_cost', {}).get('total_per_100g', 0)}/unit")
        print(f"   Compliance: {compliance.get('overall_status', 'UNKNOWN')}")
        print(f"   Ingredients: {len(optimized.get('ingredients', []))}")
        
        # Fetch market trends data
        market_trends = None
        try:
            print(f"📊 Fetching market trends data...")
            trends_service = MarketTrendsService()
            
            # Extract hero ingredients from ingredient_selection
            hero_ingredients = wish_data.get("heroIngredients", [])
            if not hero_ingredients and result.get("ingredient_selection", {}).get("ingredients"):
                # Extract from selected ingredients
                selected_ingredients = result.get("ingredient_selection", {}).get("ingredients", [])
                hero_ingredients = [
                    ing.get("ingredient_name") or ing.get("name", "")
                    for ing in selected_ingredients[:5]  # Top 5
                    if ing.get("is_hero", False) or ing.get("is_active", False)
                ]
                # If no hero ingredients found, use top ingredients
                if not hero_ingredients:
                    hero_ingredients = [
                        ing.get("ingredient_name") or ing.get("name", "")
                        for ing in selected_ingredients[:3]
                    ]
            
            market_trends = await trends_service.fetch_trends_for_wish(
                hero_ingredients=hero_ingredients,
                benefits=wish_data.get("benefits", []),
                product_type=wish_data.get("productType"),
                category=wish_data.get("category", "skincare"),
                max_age_days=35,
                use_fallback=True
            )
            print(f"✅ Market trends fetched successfully")
        except Exception as e:
            print(f"⚠️ Error fetching market trends: {e}")
            import traceback
            traceback.print_exc()
            # Don't fail the request if trends fail
            market_trends = None
        
        # Add market trends to result
        if market_trends:
            result["market_trends"] = market_trends
        
        # 🔹 Auto-save: Update history with "completed" status and formula_result
        if user_id_value and history_id:
            try:
                update_doc = {
                    "formula_result": result,
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
                    "formula_result": result,
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
        
        # Add history_id to result if available
        if history_id:
            result["history_id"] = history_id
        
        # Return response
        return MakeWishResponse(**result)
    
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid request data: {str(e)}"
        )
    except Exception as e:
        print(f"❌ Unexpected error generating Make a Wish formula: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


# ============================================================================
# PPT GENERATION ENDPOINT
# ============================================================================

class GeneratePPTRequest(BaseModel):
    """Request schema for PPT generation - only accepts history_id
    
    All data will be retrieved from the database using the history_id.
    Supports all formats: formula_result, formula_data (new/old), basic_mode_result
    """
    history_id: str = Field(..., description="History ID to fetch wish data from database")
    
    class Config:
        json_schema_extra = {
            "example": {
                "history_id": "507f1f77bcf86cd799439011"
            }
        }


@router.post("/generate-ppt", response_model=None)
async def generate_wish_ppt(
    request: GeneratePPTRequest = Body(...),
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Generate PowerPoint presentation from Make a Wish data using Gamma API.
    
    REQUEST BODY:
       {
           "history_id": "mongodb_object_id_here"
       }
    
    All data will be retrieved from the database using the history_id.
    Supports all formats:
    - formula_result (old format with phases, insights, warnings, compliance)
    - formula_data with formula/insights (new revised format)
    - formula_data with ingredient_selection/optimized_formula (old format within formula_data)
    - basic_mode_result (basic mode format)
    
    RESPONSE:
    {
        "success": true,
        "presentation_id": "gamma_presentation_id",
        "download_url": "https://...",
        "edit_url": "https://...",
        "message": "Presentation generated successfully"
    }
    """
    print(f"\n{'='*80}")
    print(f"[DEBUG] 🚀 API CALL: /api/make-wish/generate-ppt")
    print(f"[DEBUG] Request received at: {datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()}")
    print(f"[DEBUG] Request type: {type(request)}")
    print(f"[DEBUG] Request data: {request.model_dump(exclude_none=True) if hasattr(request, 'model_dump') else request}")
    print(f"{'='*80}\n")
    
    try:
        # Extract user_id from JWT token
        user_id_value = current_user.get("user_id") or current_user.get("_id")
        if not user_id_value:
            raise HTTPException(status_code=400, detail="User ID not found in JWT token")
        
        # Get wish data from database using history_id
        history_id = request.history_id
        if not history_id:
            raise HTTPException(status_code=400, detail="history_id is required")
        
        # Validate ObjectId
        if not ObjectId.is_valid(history_id):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid history_id format. Expected MongoDB ObjectId, got: {history_id[:50]}"
            )
        
        print(f"[DEBUG] 🔍 Looking for history_id: {history_id}")
        print(f"[DEBUG] 🔍 Using user_id: {user_id_value}")
        
        # First, check if document exists (without user_id filter) for better error messages
        doc_exists = await wish_history_col.find_one({"_id": ObjectId(history_id)})
        if not doc_exists:
            raise HTTPException(
                status_code=404,
                detail=f"History item not found with id: {history_id}"
            )
        
        # Check if user_id matches
        doc_user_id = doc_exists.get("user_id")
        if str(doc_user_id) != str(user_id_value):
            print(f"[DEBUG] ❌ User ID mismatch! Document user_id: {doc_user_id}, Request user_id: {user_id_value}")
            raise HTTPException(
                status_code=403,
                detail=f"History item belongs to a different user. Document user_id: {doc_user_id}, Your user_id: {user_id_value}"
            )
        
        # Fetch from database with user_id filter
        history_doc = await wish_history_col.find_one({
            "_id": ObjectId(history_id),
            "user_id": user_id_value
        })
        
        if not history_doc:
            raise HTTPException(
                status_code=404,
                detail=f"History item not found or doesn't belong to user"
            )
        
        # Extract wish response data from history
        # Check if it's the new format (formula_data), old format (formula_result), or basic mode (basic_mode_result)
        if "formula_data" in history_doc:
            # New format (revised make wish - advanced mode)
            formula_data = history_doc.get("formula_data") or {}
            # Ensure formula_data is a dict (handle None case)
            if not isinstance(formula_data, dict):
                formula_data = {}
            
            # Check if it's the new revised format (has 'formula' and 'insights') or old format within formula_data
            if "formula" in formula_data or "insights" in formula_data:
                # New revised format structure
                wish_response_data = {
                    "wish_data": history_doc.get("wish_data") or history_doc.get("parsed_data") or {},
                    "formula": formula_data.get("formula", {}) if isinstance(formula_data, dict) else {},
                    "insights": formula_data.get("insights", {}) if isinstance(formula_data, dict) else {},
                    "manufacturing": formula_data.get("manufacturing", {}) if isinstance(formula_data, dict) else {},
                    "cost_analysis": formula_data.get("cost_analysis", {}) if isinstance(formula_data, dict) else {},
                    "compliance": formula_data.get("compliance", {}) if isinstance(formula_data, dict) else {}
                }
            else:
                # Old format within formula_data (backward compatibility)
                wish_response_data = {
                    "wish_data": history_doc.get("wish_data") or history_doc.get("parsed_data") or {},
                    "ingredient_selection": formula_data.get("ingredient_selection", {}) if isinstance(formula_data, dict) else {},
                    "optimized_formula": formula_data.get("optimized_formula", {}) if isinstance(formula_data, dict) else {},
                    "manufacturing": formula_data.get("manufacturing", {}) if isinstance(formula_data, dict) else {},
                    "cost_analysis": formula_data.get("cost_analysis", {}) if isinstance(formula_data, dict) else {},
                    "compliance": formula_data.get("compliance", {}) if isinstance(formula_data, dict) else {}
                }
            # Also include parsed_data if available (for new format)
            if "parsed_data" in history_doc:
                wish_response_data["parsed_data"] = history_doc.get("parsed_data")
        elif "formula_result" in history_doc:
                # Old format (make wish) - formula_result contains the full response
                formula_result = history_doc.get("formula_result", {})
                # Ensure it has the expected structure
                if not isinstance(formula_result, dict):
                    formula_result = {}
                
                # Map formula_result structure to expected format
                # formula_result has: name, version, cost, costTarget, ph, texture, shelfLife, phases, insights, warnings, compliance
                wish_response_data = {
                    "wish_data": history_doc.get("wish_data") or {},
                    "formula_result": formula_result,  # Keep original for reference
                    # Map to optimized_formula structure for compatibility
                    "optimized_formula": {
                        "optimized_formula": {
                            "name": formula_result.get("name", ""),
                            "total_percentage": 100.0,  # Will calculate from phases
                            "estimated_cost_per_g": formula_result.get("cost", 0) / 100 if formula_result.get("cost") else 0,
                            "target_ph": formula_result.get("ph", {})
                        },
                        "ingredients": _extract_ingredients_from_phases(formula_result.get("phases", [])),
                        "phases": formula_result.get("phases", []),
                        "insights": formula_result.get("insights", []),
                        "warnings": formula_result.get("warnings", []),
                        "cost_breakdown": {
                            "total_per_g": formula_result.get("cost", 0) / 100 if formula_result.get("cost") else 0,
                            "cost_vs_target": "within_range" if _check_cost_in_range(
                                formula_result.get("cost", 0),
                                formula_result.get("costTarget", {})
                            ) else "outside_range"
                        }
                    },
                    "compliance": formula_result.get("compliance", {})
                }
        elif "basic_mode_result" in history_doc:
            # Basic mode format - basic_mode_result contains the simplified formula
            basic_result = history_doc.get("basic_mode_result") or {}
            # Ensure basic_result is a dict (handle None case)
            if not isinstance(basic_result, dict):
                basic_result = {}
            
            # Extract data from basic_mode_result structure
            # basic_mode_result has: extractedParameters, activeOptions, formula, businessNumbers, etc.
            formula_data = basic_result.get("formula", {})
            technical_formula = formula_data.get("technicalFormula", {}) if isinstance(formula_data, dict) else {}
            business_numbers = basic_result.get("businessNumbers", {}) if isinstance(basic_result, dict) else {}
            
            wish_response_data = {
                "wish_data": history_doc.get("wish_data") or history_doc.get("parsed_data") or {},
                "basic_mode_result": basic_result,  # Keep full basic_mode_result for reference
                # Map to standard structure for compatibility
                "ingredient_selection": {
                    "formula_name": formula_data.get("formulaName", ""),
                    "formula_type": basic_result.get("extractedParameters", {}).get("productType", ""),
                    "ingredients": _extract_ingredients_from_basic_mode(basic_result)
                },
                "optimized_formula": {
                    "optimized_formula": {
                        "name": formula_data.get("formulaName", ""),
                        "total_percentage": 100.0,
                        "estimated_cost_per_g": technical_formula.get("totalCostPer100g", 0) / 100 if technical_formula.get("totalCostPer100g") else 0
                    },
                    "ingredients": _extract_ingredients_from_basic_mode(basic_result),
                    "phases": technical_formula.get("phases", []),
                    "insights": _extract_insights_from_basic_mode(basic_result),
                    "warnings": _extract_warnings_from_basic_mode(basic_result)
                },
                "manufacturing": basic_result.get("manufacturing", {}),
                "cost_analysis": _extract_cost_analysis_from_basic_mode(basic_result, business_numbers),
                "compliance": basic_result.get("compliance", {})
            }
            # Include parsed_data if available
            if "parsed_data" in history_doc:
                wish_response_data["parsed_data"] = history_doc.get("parsed_data")
        else:
            # No formula data found - check if we can still create a presentation from parsed_data
            if "parsed_data" in history_doc or "wish_data" in history_doc:
                # Use parsed_data/wish_data to create a basic presentation
                wish_response_data = {
                    "wish_data": history_doc.get("wish_data") or history_doc.get("parsed_data") or {},
                    "ingredient_selection": {},
                    "optimized_formula": {},
                    "manufacturing": {},
                    "cost_analysis": {},
                    "compliance": {}
                }
                if "parsed_data" in history_doc:
                    wish_response_data["parsed_data"] = history_doc.get("parsed_data")
                print(f"[DEBUG] ⚠️ No formula data found, using parsed_data/wish_data only")
            else:
                raise HTTPException(
                    status_code=400,
                    detail="History item does not contain formula data or wish data. Please generate a formula first."
                )
        
        print(f"[DEBUG] ✅ Fetched wish data from history_id: {history_id}")
        print(f"[DEBUG] History doc keys: {list(history_doc.keys())}")
        print(f"[DEBUG] Has formula_data: {'formula_data' in history_doc}")
        print(f"[DEBUG] Has formula_result: {'formula_result' in history_doc}")
        print(f"[DEBUG] Has basic_mode_result: {'basic_mode_result' in history_doc}")
        print(f"[DEBUG] Has wish_data: {'wish_data' in history_doc}")
        print(f"[DEBUG] Has parsed_data: {'parsed_data' in history_doc}")
        if "formula_data" in history_doc:
            formula_data = history_doc.get("formula_data", {})
            print(f"[DEBUG] formula_data keys: {list(formula_data.keys()) if isinstance(formula_data, dict) else 'Not a dict'}")
        print(f"[DEBUG] wish_response_data keys: {list(wish_response_data.keys()) if isinstance(wish_response_data, dict) else 'Not a dict'}")
        print(f"[DEBUG] Data structure: wish_data={bool(wish_response_data.get('wish_data'))}, "
              f"ingredient_selection={bool(wish_response_data.get('ingredient_selection'))}, "
              f"optimized_formula={bool(wish_response_data.get('optimized_formula'))}, "
              f"formula={bool(wish_response_data.get('formula'))}, "
              f"insights={bool(wish_response_data.get('insights'))}, "
              f"basic_mode_result={bool(wish_response_data.get('basic_mode_result'))}, "
              f"parsed_data={bool(wish_response_data.get('parsed_data'))}")
        
        # Validate that we have at least some data
        # Check if we have any meaningful data (wish_data, ingredient_selection, optimized_formula, etc.)
        print(f"[DEBUG] 🔍 Validating wish_response_data...")
        print(f"[DEBUG] wish_response_data type: {type(wish_response_data)}")
        print(f"[DEBUG] wish_response_data is None: {wish_response_data is None}")
        
        if wish_response_data:
            print(f"[DEBUG] wish_response_data keys: {list(wish_response_data.keys()) if isinstance(wish_response_data, dict) else 'Not a dict'}")
            if isinstance(wish_response_data, dict):
                for key, value in wish_response_data.items():
                    if isinstance(value, dict):
                        print(f"[DEBUG]   {key}: dict with {len(value)} keys")
                    elif isinstance(value, list):
                        print(f"[DEBUG]   {key}: list with {len(value)} items")
                    else:
                        print(f"[DEBUG]   {key}: {type(value).__name__} = {str(value)[:100]}")
        
        has_wish_data = wish_response_data and isinstance(wish_response_data, dict) and bool(wish_response_data.get("wish_data"))
        has_ingredient_selection = wish_response_data and isinstance(wish_response_data, dict) and bool(wish_response_data.get("ingredient_selection"))
        has_optimized_formula = wish_response_data and isinstance(wish_response_data, dict) and bool(wish_response_data.get("optimized_formula"))
        has_parsed_data = wish_response_data and isinstance(wish_response_data, dict) and bool(wish_response_data.get("parsed_data"))
        # New format checks
        has_formula = wish_response_data and isinstance(wish_response_data, dict) and bool(wish_response_data.get("formula"))
        has_insights = wish_response_data and isinstance(wish_response_data, dict) and bool(wish_response_data.get("insights"))
        # Basic mode format check
        has_basic_mode_result = wish_response_data and isinstance(wish_response_data, dict) and bool(wish_response_data.get("basic_mode_result"))
        
        # For old format, formula_result might have data directly (check if it's a non-empty dict)
        is_non_empty_dict = wish_response_data and isinstance(wish_response_data, dict) and len(wish_response_data) > 0
        
        print(f"[DEBUG] Validation checks: has_wish_data={has_wish_data}, has_ingredient_selection={has_ingredient_selection}, "
              f"has_optimized_formula={has_optimized_formula}, has_parsed_data={has_parsed_data}, "
              f"has_formula={has_formula}, has_insights={has_insights}, has_basic_mode_result={has_basic_mode_result}, "
              f"is_non_empty_dict={is_non_empty_dict}")
        
        # For old format, check if formula_result has nested data
        has_nested_data = False
        if wish_response_data and isinstance(wish_response_data, dict):
            # Check if any value is a non-empty dict or list
            for key, value in wish_response_data.items():
                if isinstance(value, dict) and len(value) > 0:
                    has_nested_data = True
                    break
                elif isinstance(value, list) and len(value) > 0:
                    has_nested_data = True
                    break
        
        has_any_data = (
            has_wish_data or 
            has_ingredient_selection or 
            has_optimized_formula or 
            has_parsed_data or
            has_formula or  # New format
            has_insights or  # New format
            has_basic_mode_result or  # Basic mode format
            has_nested_data or
            is_non_empty_dict
        )
        
        print(f"[DEBUG] Final validation: has_any_data={has_any_data}")
        
        if not wish_response_data or not has_any_data:
            error_detail = "Invalid wish data. Missing required fields. "
            if wish_response_data and isinstance(wish_response_data, dict):
                error_detail += f"Found keys: {list(wish_response_data.keys())}. "
            error_detail += "The history item must contain formula data (formula/insights for new format, ingredient_selection/optimized_formula for old format, basic_mode_result for basic mode, formula_result for old format, or wish_data/parsed_data)."
            print(f"[DEBUG] ❌ Validation failed: {error_detail}")
            raise HTTPException(
                status_code=400,
                detail=error_detail
            )
        
        print(f"[DEBUG] ✅ Validation passed!")
        
        # ========================================================================
        # MODULAR FLOW: Make a Wish Data → Claude → Gamma → PPT
        # ========================================================================
        
        # Step 1: Format wish data as structured text
        print(f"[DEBUG] 📝 Step 1: Formatting wish data for analysis...")
        print(f"[DEBUG] 📋 wish_response_data structure:")
        print(f"[DEBUG]   Keys: {list(wish_response_data.keys()) if isinstance(wish_response_data, dict) else 'Not a dict'}")
        if isinstance(wish_response_data, dict):
            for key in ["wish_data", "parsed_data", "ingredient_selection", "optimized_formula"]:
                value = wish_response_data.get(key)
                if value:
                    print(f"[DEBUG]   {key}: {type(value).__name__} with {len(str(value))} chars")
                else:
                    print(f"[DEBUG]   {key}: None or empty")
        
        formatted_wish_data = format_wish_data_for_gamma(wish_response_data)
        print(f"[DEBUG] ✅ Formatted data length: {len(formatted_wish_data)} characters")
        print(f"[DEBUG] 📋 First 1000 chars of formatted data:")
        print(f"{formatted_wish_data[:1000]}...")
        print(f"[DEBUG] 📋 Last 1000 chars of formatted data:")
        print(f"...{formatted_wish_data[-1000:]}")
        
        # Step 2: Send to Claude to generate business strategy prompt
        print(f"[DEBUG] 🤖 Step 2: Sending to Claude to generate business strategy prompt...")
        business_strategy_prompt = await generate_business_strategy_prompt(
            data_text=formatted_wish_data,
            data_type="cosmetic_formulation",
            custom_instructions=None
        )
        print(f"[DEBUG] ✅ Claude prompt generated ({len(business_strategy_prompt)} characters)")
        print(f"[DEBUG] 📋 Full Claude-generated prompt (will be sent to Gamma):")
        print(f"{'='*80}")
        print(f"{business_strategy_prompt}")
        print(f"{'='*80}")
        
        # Step 3: Generate PPT using Gamma API with Claude's prompt
        print(f"[DEBUG] 🚀 Step 3: Generating PPT with Gamma API...")
        result = await generate_ppt_from_data(
            data_text=formatted_wish_data,
            prompt=business_strategy_prompt,
            tone="professional, strategic, business-focused, investor-ready",
            audience="business executives, investors, stakeholders, strategic planners, C-level executives",
            num_slides=15,  # Fixed to 15 slides for Make a Wish presentations
            export_format="pptx",
            language="en"
        )
        
        print(f"[DEBUG] ✅ PPT Generation complete!")
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Unexpected error generating PPT: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

