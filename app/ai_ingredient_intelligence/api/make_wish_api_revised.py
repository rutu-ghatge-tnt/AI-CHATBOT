"""
Revised Make A Wish API Endpoints (January 2025)
================================================

This module implements the new API endpoints for the revised Make A Wish flow:
- POST /parse-wish (Stage 1)
- POST /generate (Stage 2 - revised) 
- POST /get-alternatives (Stage 3)
- POST /edit-formula (Stage 4)
- POST /request-quote (Stage 5)
- POST /get-this-made (Stage 6)

The new flow features natural language parsing, complexity selection, 
ingredient alternatives, formula editing, and commercialization.

All AI operations use Claude Opus (claude-opus-4-5-20251101) for optimal quality.
"""

from fastapi import APIRouter, HTTPException, Header, Depends, Query, BackgroundTasks, Body
import httpx
import os
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone, timedelta
from bson import ObjectId as BSONObjectId
# Alias for backward compatibility
ObjectId = BSONObjectId
import time
import json
import uuid
import asyncio
import logging
from pydantic import BaseModel, Field

# Semaphore to limit concurrent background tasks and prevent event loop blocking
# Initialize lazily in async context to ensure event loop exists
_background_task_semaphore = None

async def get_background_task_semaphore():
    """Get or create the background task semaphore (must be called in async context)."""
    global _background_task_semaphore
    if _background_task_semaphore is None:
        # Increased to 10 to allow more concurrent tasks without blocking other API calls
        _background_task_semaphore = asyncio.Semaphore(10)
    return _background_task_semaphore

# Import authentication
from app.ai_ingredient_intelligence.auth import verify_jwt_token

# Import revised schemas
from app.ai_ingredient_intelligence.models.make_wish_schemas_revised import (
    ParseWishRequest, ParseWishResponse,
    MakeWishRequestRevised, MakeWishResponseRevised,
    MakeWishBasicResponseRevised,
    MarketTrendsAcceptedResponse,
    MarketPositionAcceptedResponse,
    GetAlternativesRequest, GetAlternativesResponse,
    EditFormulaRequest, EditFormulaResponse,
    RequestQuoteRequest, RequestQuoteResponse,
    GetThisMadeRequest, GetThisMadeResponse
)

# Legacy imports removed - using revised schemas only

# Import configuration
from app.ai_ingredient_intelligence.logic.make_wish_config import (
    get_complexity_config, get_texture_for_product_type, 
    get_alternatives_for_ingredient, check_compatibility,
    generate_queue_number, EDIT_RULES
)
from app.ai_ingredient_intelligence.logic.make_wish_icon_mapping import emoji_to_icon, replace_icon_emoji_values

# Import AI prompts
from app.ai_ingredient_intelligence.logic.make_wish_prompts import PARSE_WISH_PROMPT

# Import existing generator
from app.ai_ingredient_intelligence.logic.make_wish_generator import (
    call_ai_with_claude, generate_formula_from_wish
)

# Import credit service
from app.ai_ingredient_intelligence.logic.credit_service import (
    deduct_credits,
    CreditKey
)

# Import WebSocket notification helper (enhanced version)
from app.ai_ingredient_intelligence.logic.websocket_notifications import notify_user_enhanced
from app.ai_ingredient_intelligence.models.notification_schemas import NotificationAction

# Import trend analyzer for market intelligence
from app.ai_ingredient_intelligence.logic.trend_analyzer import TrendAnalyzer
# synthesize_trend_insights removed - not used (code is commented out in fetch_trend_data_for_ingredients)
from app.ai_ingredient_intelligence.logic.market_trends_storage import (
    get_stored_trend_data_for_ingredients
)
from app.ai_ingredient_intelligence.logic.market_trends_service import MarketTrendsService
from app.ai_ingredient_intelligence.logic.market_position_service import fetch_market_position_from_external_products

# Import packaging data
from app.ai_ingredient_intelligence.logic.packaging_data import (
    get_all_packaging_options,
    get_packaging_options_by_category,
    get_packaging_by_size
)

# Import Gamma PPT and Claude prompt generators
from app.ai_ingredient_intelligence.logic.gamma_ppt_generator import (
    generate_ppt_from_data,
    is_gamma_available
)
from app.ai_ingredient_intelligence.logic.claude_prompt_generator import generate_business_strategy_prompt

# Import database collections
from app.ai_ingredient_intelligence.db.collections import (
    wish_history_col, 
    formula_versions_col, quotes_col, ingredient_alternatives_cache_col,
    qms_queries_col  # Single source of truth for commercialization requests
)

router = APIRouter(prefix="/make-wish", tags=["Make a Wish - Revised"])


# ============================================================================
# HELPER FUNCTION: FETCH TREND DATA FOR HERO INGREDIENTS
# ============================================================================

async def fetch_trend_data_for_ingredients(hero_ingredients: List[str]) -> Dict[str, Any]:
    """
    Fetch trend analysis and synthesis data for hero ingredients.
    Runs internally as part of make-wish generation.
    
    First tries to fetch from stored database data (pre-fetched by scheduled script).
    Falls back to API calls only if stored data is not available.
    
    Args:
        hero_ingredients: List of hero ingredient names
        
    Returns:
        Dictionary with trend data for each ingredient:
        {
            "ingredient_name": {
                "analyze": {...},
                "synthesis": {...}
            }
        }
    """
    trend_data = {}
    
    if not hero_ingredients:
        return trend_data
    
    print(f"📊 Fetching trend data for {len(hero_ingredients)} hero ingredients...")
    
    # First, try to get stored data from database
    print(f"   🔍 Checking stored trend data...")
    stored_data = await get_stored_trend_data_for_ingredients(hero_ingredients, max_age_days=30)
    
    # Track which ingredients have stored data
    ingredients_with_stored_data = []
    ingredients_needing_api = []
    
    for ingredient in hero_ingredients:
        if not ingredient or not ingredient.strip():
            continue
        
        clean_ingredient = ingredient.split("(")[0].strip()
        
        # Check if we have stored data for this ingredient
        stored_trend_data = stored_data.get(ingredient) or stored_data.get(clean_ingredient)
        
        if stored_trend_data:
            print(f"   ✅ Found stored data for: {clean_ingredient}")
            # Use stored data
            trend_data[ingredient] = {
                "analyze": stored_trend_data.get("analyze"),
                "synthesis": stored_trend_data.get("synthesis"),
                "consumer_intent": stored_trend_data.get("consumer_intent"),
                "competitive": stored_trend_data.get("competitive"),
                "regional": stored_trend_data.get("regional"),
                "source": "stored"  # Mark as from stored data
            }
            ingredients_with_stored_data.append(ingredient)
        else:
            print(f"   ⚠️  No stored data found for: {clean_ingredient}")
            ingredients_needing_api.append(ingredient)
    
    print(f"   📊 Summary: {len(ingredients_with_stored_data)} from storage, {len(ingredients_needing_api)} need API calls")
    
    # If all ingredients have stored data, return early
    if not ingredients_needing_api:
        print(f"✅ All trend data retrieved from storage")
        return trend_data
    
    # For ingredients without stored data, skip API calls for now
    # (API calls will be enabled once data document is provided)
    print(f"   ⏭️  Skipping API calls for {len(ingredients_needing_api)} ingredients (no stored data available)")
    print(f"   ℹ️  These ingredients will not have trend data until the scheduled script runs with data")
    
    # Mark ingredients without stored data as missing
    for ingredient in ingredients_needing_api:
        if not ingredient or not ingredient.strip():
            continue
        
        clean_ingredient = ingredient.split("(")[0].strip()
        print(f"   ⚠️  No trend data available for: {clean_ingredient}")
        
        trend_data[ingredient] = {
            "analyze": None,
            "synthesis": None,
            "source": "missing",
            "note": "No stored data available. Trend data will be available after scheduled script runs."
        }
    
    # TODO: Once data document is provided, uncomment the API fallback code below
    # This will enable real-time API calls as a fallback when stored data is not available
    """
    # Fallback to API calls for ingredients without stored data
    analyzer = TrendAnalyzer()
    
    for ingredient in ingredients_needing_api:
        if not ingredient or not ingredient.strip():
            continue
            
        try:
            # Clean ingredient name (remove parentheses and extra text)
            clean_ingredient = ingredient.split("(")[0].strip()
            
            print(f"   Analyzing trends for: {clean_ingredient}")
            
            # Fetch trend analysis with retry logic and alternative queries
            analyze_data = None
            max_retries = 2
            
            # For ingredients with potentially low search volume (like UV filters), try alternative search queries
            search_queries = [clean_ingredient]  # Start with original
            
            # Add context-based queries for better results
            ingredient_lower = clean_ingredient.lower()
            if any(term in ingredient_lower for term in ["octinoxate", "avobenzone", "octisalate", "octocrylene", "zinc oxide", "titanium dioxide"]):
                # UV filters - try with sunscreen context
                search_queries.append(f"{clean_ingredient} sunscreen")
                search_queries.append(f"sunscreen with {clean_ingredient}")
            
            # Try each search query variant
            for search_query in search_queries:
                if analyze_data and isinstance(analyze_data, dict) and "error" not in analyze_data:
                    break  # Success, stop trying
                    
                for retry in range(max_retries):
                    try:
                        analyze_data = await analyzer.analyze_ingredient_trend(
                            search_query,
                            time_range="today 12-m"
                        )
                        if analyze_data and "error" in analyze_data:
                            error_msg = analyze_data.get('error', 'Unknown error')
                            # If it's an "insufficient search volume" error, try next query variant
                            if "insufficient search volume" in error_msg.lower() or "no timeline data" in error_msg.lower():
                                if search_query != search_queries[-1]:  # Not the last query
                                    print(f"   ⚠️ Low search volume for '{search_query}', trying alternatives...")
                                    analyze_data = None
                                    break  # Try next query
                                else:
                                    print(f"   ⚠️ All query variants failed - insufficient search volume for {clean_ingredient}")
                                    analyze_data = None
                                    break
                            # Retry on temporary errors
                            elif retry < max_retries - 1 and ("temporarily unavailable" in error_msg.lower() or "rate limit" in error_msg.lower()):
                                print(f"   ⚠️ Temporary error for '{search_query}' (attempt {retry + 1}): {error_msg}")
                                import asyncio
                                await asyncio.sleep(2 * (retry + 1))  # Exponential backoff
                                continue
                            else:
                                print(f"   ⚠️ Analyze error for '{search_query}': {error_msg}")
                                analyze_data = None
                                break  # Try next query
                        elif analyze_data and isinstance(analyze_data, dict):
                            # Success - got valid data
                            if search_query != clean_ingredient:
                                print(f"   ✅ Successfully analyzed using alternative query: '{search_query}'")
                            else:
                                print(f"   ✅ Successfully analyzed '{clean_ingredient}'")
                            break
                    except Exception as e:
                        print(f"   ⚠️ Error analyzing '{search_query}' (attempt {retry + 1}): {str(e)}")
                        if retry < max_retries - 1:
                            import asyncio
                            await asyncio.sleep(2 * (retry + 1))  # Exponential backoff
                            continue
                        analyze_data = None
                
                if analyze_data and isinstance(analyze_data, dict) and "error" not in analyze_data:
                    break  # Success, stop trying queries
            
            # Fetch synthesis (includes analyze + consumer intent + competitive + regional)
            synthesis_data = None
            try:
                # Get additional data for synthesis
                consumer_intent_data = None
                competitive_data = None
                regional_data = None
                
                try:
                    consumer_intent_data = await analyzer.analyze_consumer_intent(clean_ingredient)
                    if consumer_intent_data and "error" in consumer_intent_data:
                        consumer_intent_data = None
                except:
                    pass
                
                try:
                    competitive_data = await analyzer.analyze_competitive_landscape(f"{clean_ingredient} serum")
                    if competitive_data and "error" in competitive_data:
                        competitive_data = None
                except:
                    pass
                
                try:
                    regional_data = await analyzer.analyze_regional_demand(clean_ingredient, "today 12-m")
                    if regional_data and "error" in regional_data:
                        regional_data = None
                except:
                    pass
                
                # Synthesize all data
                safe_analyze = analyze_data if (analyze_data and isinstance(analyze_data, dict) and "error" not in analyze_data) else None
                safe_consumer = consumer_intent_data if (consumer_intent_data and isinstance(consumer_intent_data, dict) and "error" not in consumer_intent_data) else None
                safe_competitive = competitive_data if (competitive_data and isinstance(competitive_data, dict) and "error" not in competitive_data) else None
                safe_regional = regional_data if (regional_data and isinstance(regional_data, dict) and "error" not in regional_data) else None
                
                # Only synthesize if we have at least some data
                has_data = safe_analyze or safe_consumer or safe_competitive or safe_regional
                if has_data:
                    synthesis_result = await synthesize_trend_insights(
                        clean_ingredient,
                        safe_analyze,
                        safe_consumer,
                        safe_competitive,
                        safe_regional
                    )
                    if synthesis_result and synthesis_result.get("synthesis"):
                        synthesis_data = synthesis_result.get("synthesis")
                    elif synthesis_result and synthesis_result.get("error"):
                        print(f"   ⚠️ Synthesis error for {clean_ingredient}: {synthesis_result.get('error')}")
            except Exception as e:
                print(f"   ⚠️ Error synthesizing {clean_ingredient}: {str(e)}")
            
            # Store trend data for this ingredient
            # Only store if we have at least synthesis data (synthesis can work with partial data)
            if synthesis_data or analyze_data:
                trend_data[ingredient] = {
                    "analyze": analyze_data,
                    "synthesis": synthesis_data
                }
            else:
                # If both failed, still store but with error info
                print(f"   ⚠️ Both analyze and synthesis failed for {ingredient}")
                trend_data[ingredient] = {
                    "analyze": None,
                    "synthesis": None,
                    "error": "Failed to fetch trend data - API may be temporarily unavailable or ingredient has insufficient search volume"
                }
            
        except Exception as e:
            print(f"   ❌ Failed to fetch trend data for {ingredient}: {str(e)}")
            import traceback
            traceback.print_exc()
            trend_data[ingredient] = {
                "analyze": None,
                "synthesis": None,
                "error": f"Exception: {str(e)}"
            }
    """
    
    print(f"✅ Completed trend analysis for {len(trend_data)} ingredients")
    return trend_data


# ============================================================================
# STAGE 1: PARSE WISH ENDPOINT
# ============================================================================

@router.post("/parse-wish", response_model=ParseWishResponse)
async def parse_natural_language_wish(
    request: ParseWishRequest,
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Parse natural language wish into structured data.
    
    This endpoint analyzes user's natural language description and extracts:
    - Category (skincare/haircare)
    - Product type with confidence
    - Detected ingredients
    - Benefits and exclusions
    - Auto-detected texture
    - Compatibility issues
    - Clarification questions if needed
    """
    start_time = time.time()
    
    try:
        # Validate minimum length
        if len(request.wish_text.strip()) < 30:
            raise HTTPException(
                status_code=400,
                detail="Wish text must be at least 30 characters long"
            )
        
        print(f"🔍 Parsing natural language wish...")
        print(f"   Wish: {request.wish_text[:100]}...")
        
        # Call AI to parse the wish
        try:
            parsed_result = await call_ai_with_claude(
                system_prompt="You are a cosmetic formulation expert AI. Analyze natural language wishes and extract structured information.",
                user_prompt=PARSE_WISH_PROMPT.format(wish_text=request.wish_text),
                prompt_type="parse_wish"
            )
            
            # Debug: Log the AI response
            print(f"🤖 AI Response received:")
            print(f"   Type: {type(parsed_result)}")
            if isinstance(parsed_result, dict):
                print(f"   Keys: {list(parsed_result.keys())}")
                if 'compatibility_issues' in parsed_result:
                    issues = parsed_result['compatibility_issues']
                    print(f"   Compatibility Issues: {len(issues) if isinstance(issues, list) else 'N/A'}")
                    if isinstance(issues, list) and issues:
                        first_issue = issues[0]
                        if isinstance(first_issue, dict):
                            print(f"   First Issue Keys: {list(first_issue.keys())}")
                        else:
                            print(f"   First Issue (not dict): {type(first_issue).__name__}")
            
        except Exception as ai_error:
            timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
            print(f"❌ [PARSE-WISH] [{timestamp}] AI parsing error: {ai_error}")
            import traceback
            traceback.print_exc()
            # Provide more helpful error message
            error_detail = str(ai_error)
            if "JSON" in error_detail or "json" in error_detail.lower():
                error_detail = "AI returned invalid JSON format. Please try again or rephrase your wish."
            raise HTTPException(
                status_code=500,
                detail=f"Error parsing wish: {error_detail}"
            )
        
        # Validate AI response structure
        if not parsed_result or not isinstance(parsed_result, dict):
            raise HTTPException(
                status_code=500,
                detail="Invalid parsing result from AI"
            )
        
        # Auto-detect texture if not provided
        product_type_id = parsed_result.get("product_type", {}).get("id", "serum")
        auto_texture_raw = get_texture_for_product_type(product_type_id)
        
        # Transform texture to match schema (texture_id -> id, add auto_selected)
        auto_texture = {
            "id": auto_texture_raw.get("texture_id", "gel"),
            "label": auto_texture_raw.get("label", "Balanced Texture"),
            "auto_selected": True
        }
        
        # Update parsed data with auto-detected texture
        if "auto_texture" not in parsed_result:
            parsed_result["auto_texture"] = auto_texture
        
        # Check for additional compatibility issues
        detected_ingredients = [ing.get("name", "") if isinstance(ing, dict) else str(ing) for ing in parsed_result.get("detected_ingredients", [])]
        def _normalize_compatibility_issue(item: Any) -> Dict[str, Any]:
            """Map any issue dict (AI or check_compatibility) to CompatibilityIssue shape."""
            if isinstance(item, str):
                return {
                    "severity": "warning",
                    "title": item,
                    "problem": item,
                    "solution": None,
                    "ingredients_involved": None,
                }
            if not isinstance(item, dict):
                return {"severity": "warning", "title": None, "problem": None, "solution": None, "ingredients_involved": None}
            # Map issue/ingredients (config) and problem/title/description (AI) to schema fields
            text = (
                item.get("problem")
                or item.get("issue")
                or item.get("title")
                or item.get("description")
                or ""
            )
            ingredients = item.get("ingredients_involved") or item.get("ingredients")
            return {
                "severity": item.get("severity") or "warning",
                "title": item.get("title") or (text[:80] + "..." if len(text) > 80 else text) or None,
                "problem": item.get("problem") or item.get("issue") or text or None,
                "solution": item.get("solution"),
                "ingredients_involved": ingredients,
            }

        raw_issues = parsed_result.get("compatibility_issues", [])
        compatibility_issues = []
        for item in raw_issues if isinstance(raw_issues, list) else []:
            compatibility_issues.append(_normalize_compatibility_issue(item))

        # Add any additional compatibility checks (normalize so response has problem/ingredients_involved)
        additional_issues = check_compatibility(detected_ingredients)
        for issue in additional_issues:
            normalized = _normalize_compatibility_issue(issue)
            if normalized not in compatibility_issues:
                compatibility_issues.append(normalized)
        
        parsed_result["compatibility_issues"] = compatibility_issues
        
        # Transform needs_clarification to ensure proper format
        needs_clarification = parsed_result.get("needs_clarification", [])
        if needs_clarification:
            transformed_clarifications = []
            for item in needs_clarification:
                if isinstance(item, str):
                    # Convert string to dictionary format
                    transformed_clarifications.append({
                        "question": item,
                        "reason": f"Clarification needed for: {item}"
                    })
                elif isinstance(item, dict):
                    # Already in correct format
                    transformed_clarifications.append(item)
                else:
                    # Skip invalid items
                    continue
            
            parsed_result["needs_clarification"] = transformed_clarifications
        
        processing_time = time.time() - start_time
        print(f"✅ Wish parsed in {processing_time:.2f}s")
        print(f"   Category: {parsed_result.get('category', 'unknown')}")
        print(f"   Product Type: {parsed_result.get('product_type', {}).get('name', 'unknown')}")
        print(f"   Ingredients Detected: {len(parsed_result.get('detected_ingredients', []))}")
        print(f"   Compatibility Issues: {len(compatibility_issues)}")
        print(f"   Compatibility Issues: {compatibility_issues}")
        
        return ParseWishResponse(
            success=True,
            parsed_data=parsed_result,
            compatibility_issues=compatibility_issues
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Unexpected error parsing wish: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


# ============================================================================
# STAGE 2: REVISED GENERATE ENDPOINT
# ============================================================================

@router.post("/generate-revised", response_model=MakeWishBasicResponseRevised)
async def generate_formula_revised(
    request: MakeWishRequestRevised,
    current_user: dict = Depends(verify_jwt_token),
    authorization: Optional[str] = Header(None, alias="Authorization")
):
    """
    Generate formula using basic mode flow.
    
    This endpoint creates a formula based on:
    - Parsed natural language wish
    - Selected complexity level (minimalist/classic/luxe)
    - Auto-detected texture
    - Active ingredient options with business context
    
    NOW WITH ASYNC PATTERN:
    - Saves request to DB immediately
    - Returns history_id instantly
    - Processes in background
    - Deducts credits on success
    - Sends WebSocket notifications
    """
    timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*80}")
    print(f"🚀 [MAIN] [{timestamp}] ========================================")
    print(f"🚀 [MAIN] [{timestamp}] /generate-revised ENDPOINT CALLED")
    print(f"🚀 [MAIN] [{timestamp}] ========================================")
    
    request_received_at = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    
    # Extract user info for auto-save
    user_id = current_user.get("user_id") or current_user.get("_id")
    name = request.name.strip()
    history_id = request.history_id
    
    print(f"📋 [MAIN] [{timestamp}] Request details:")
    print(f"   - User ID: {user_id}")
    print(f"   - Name: {name}")
    print(f"   - History ID: {history_id}")
    print(f"   - Complexity: {request.complexity}")
    print(f"{'='*80}\n")
    
    # Validate required fields
    if not name:
        raise HTTPException(
            status_code=400,
            detail="name is required for formula generation"
        )
    
    if request.complexity not in ["minimalist", "classic", "luxe"]:
        raise HTTPException(
            status_code=400,
            detail="complexity must be one of: minimalist, classic, luxe"
        )
    
    try:
        timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
        print(f"🔑 [MAIN] [{timestamp}] Generating IDs...")
        # Generate IDs immediately
        formula_id = str(uuid.uuid4())
        if not history_id:
            # Generate MongoDB ObjectId upfront
            history_id = str(ObjectId())
        print(f"✅ [MAIN] [{timestamp}] IDs generated - formula_id: {formula_id}, history_id: {history_id}")
        
        # CRITICAL: Save to DB FIRST so detail API can find it immediately
        # This is a quick operation and ensures the record exists
        if not request.history_id:
            try:
                history_doc = {
                    "_id": ObjectId(history_id),
                    "mode": "basic",
                    "user_id": user_id,
                    "name": name,
                    "tag": request.tag,
                    "additional_notes": request.additional_notes,
                    "wish_text": request.wish_text,
                    "parsed_data": request.parsed_data.model_dump(),
                    "complexity": request.complexity,
                    "formula_id": formula_id,
                    "formula_data": None,
                    "basic_mode_result": None,
                    "status": "in_progress",
                    "request_received_at": request_received_at.isoformat(),
                    "created_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat(),
                    "updated_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()
                }
                await wish_history_col.insert_one(history_doc)
                print(f"[AUTO-SAVE] Saved initial state with history_id: {history_id}")
            except Exception as e:
                print(f"[AUTO-SAVE] Error: Failed to save initial state: {e}")
                import traceback
                traceback.print_exc()
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to save request: {str(e)}"
                )
        else:
            # Update existing history record to in_progress
            try:
                update_doc = {
                    "status": "in_progress",
                    "request_received_at": request_received_at.isoformat(),
                    "updated_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()
                }
                await wish_history_col.update_one(
                    {"_id": ObjectId(history_id), "user_id": user_id},
                    {"$set": update_doc}
                )
                print(f"[AUTO-SAVE] Updated existing history {history_id} to in_progress")
            except Exception as e:
                print(f"[AUTO-SAVE] Warning: Failed to update history: {e}")
        
        # NOW start background task for heavy processing (formula generation, trends, etc.)
        timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
        print(f"🚀 [MAIN] [{timestamp}] Creating background task for history_id: {history_id}")
        background_coro = process_generate_revised_background_with_semaphore(
            history_id=history_id,
            user_id=user_id,
            request=request,
            name=name,
            formula_id=formula_id,
            request_received_at=request_received_at,
            is_new_history=not bool(request.history_id),
            bearer_token=authorization
        )
        # Fire and forget - don't await, don't store reference
        task = asyncio.create_task(handle_background_task_safely(background_coro))
        print(f"✅ [MAIN] [{timestamp}] Background task created and scheduled (task_id: {id(task)})")
        
        # Return immediate acknowledgment (DB already saved, processing in background)
        # Response model requires: success, formula_id, history_id
        # Note: success=True means "request accepted", NOT "formula completed"
        # The actual completion notification is sent via WebSocket when background task finishes
        response = MakeWishBasicResponseRevised(
            success=True,
            formula_id=formula_id,
            history_id=history_id
        )
        print(f"📤 [MAIN] [{timestamp}] Returning response: success={response.success}, formula_id={response.formula_id}, history_id={response.history_id}")
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Unexpected error in generate_formula_revised: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


# ============================================================================
# BACKGROUND TASK ERROR HANDLER
# ============================================================================

async def handle_background_task_safely(coro):
    """
    Wrapper to safely execute background tasks and catch any unhandled exceptions.
    """
    try:
        timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
        print(f"🔄 [BACKGROUND] [{timestamp}] Background task wrapper started")
        await coro
        timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
        print(f"✅ [BACKGROUND] [{timestamp}] Background task wrapper completed successfully")
    except Exception as e:
        timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
        logger = logging.getLogger(__name__)
        logger.error(f"❌ [BACKGROUND] [{timestamp}] Unhandled exception in background task: {e}", exc_info=True)
        print(f"❌ [BACKGROUND] [{timestamp}] Unhandled exception in background task: {e}")
        import traceback
        traceback.print_exc()


async def process_generate_revised_background_with_semaphore(
    history_id: str,
    user_id: str,
    request: MakeWishRequestRevised,
    name: str,
    formula_id: str,
    request_received_at: datetime,
    is_new_history: bool = True,
    bearer_token: Optional[str] = None
):
    """
    Wrapper that acquires semaphore before running background task.
    This prevents too many concurrent tasks from blocking the event loop.
    """
    timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
    print(f"🔒 [BACKGROUND] [{timestamp}] Waiting for semaphore for history_id: {history_id}")
    semaphore = await get_background_task_semaphore()
    async with semaphore:
        timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
        print(f"✅ [BACKGROUND] [{timestamp}] Semaphore acquired for history_id: {history_id}, starting processing...")
        # Yield control to event loop before starting heavy work
        await asyncio.sleep(0)
        await process_generate_revised_background(
            history_id=history_id,
            user_id=user_id,
            request=request,
            name=name,
            formula_id=formula_id,
            request_received_at=request_received_at,
            is_new_history=is_new_history,
            bearer_token=bearer_token
        )
        timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
        print(f"🔓 [BACKGROUND] [{timestamp}] Semaphore released for history_id: {history_id}")


# ============================================================================
# BACKGROUND PROCESSING FUNCTION
# ============================================================================

async def process_generate_revised_background(
    history_id: str,
    user_id: str,
    request: MakeWishRequestRevised,
    name: str,
    formula_id: str,
    request_received_at: datetime,
    is_new_history: bool = True,
    bearer_token: Optional[str] = None
):
    """
    Background task to process revised Make a Wish formula generation.
    Handles:
    - Prepare wish_data (moved from main endpoint for speed)
    - Database save/update (first thing, to get real MongoDB ObjectId if needed)
    - Formula generation
    - Trend analysis
    - Market trends
    - Synthesis
    - Credit deduction (on success only)
    - WebSocket notifications (success/failure)
    - Database updates
    """
    start_time = time.time()
    processing_success = False
    error_message = None
    
    try:
        timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
        print(f"🚀 [BACKGROUND] [{timestamp}] ========================================")
        print(f"🚀 [BACKGROUND] [{timestamp}] STARTING processing for history_id: {history_id}")
        print(f"🚀 [BACKGROUND] [{timestamp}] User: {user_id}, Formula ID: {formula_id}")
        print(f"🚀 [BACKGROUND] [{timestamp}] ========================================")
        
        # Prepare wish data (moved here from main endpoint to return ASAP)
        cost_by_complexity = {"minimalist": (30, 40), "classic": (40, 60), "luxe": (60, 100)}
        cost_min, cost_max = cost_by_complexity.get(request.complexity, (40, 60))
        wish_data = {
            "category": request.parsed_data.category,
            "productType": request.parsed_data.product_type.id or request.parsed_data.product_type.name,
            "benefits": request.parsed_data.detected_benefits,
            "exclusions": request.parsed_data.detected_exclusions,
            "heroIngredients": [ing.name for ing in request.parsed_data.detected_ingredients],
            "texture": request.parsed_data.auto_texture.label,
            "costMin": cost_min,
            "costMax": cost_max,
            "claims": request.claims or [],
            "targetAudience": request.parsed_data.detected_skin_types or request.parsed_data.detected_hair_concerns,
            "additionalNotes": request.additional_notes or "",
        }
        
        # DB is already saved in main endpoint, so we can skip saving here
        # Just log that we're starting processing
        timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
        print(f"📝 [BACKGROUND] [{timestamp}] DB already saved, starting formula generation...")
        
        # Yield control to event loop before starting heavy work
        await asyncio.sleep(0)
        
        # Generate formula using basic mode (from dev)
        timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
        print(f"🤖 [BACKGROUND] [{timestamp}] Calling AI to generate formula...")
        basic_result = await generate_formula_from_wish(wish_data)
        timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
        print(f"✅ [BACKGROUND] [{timestamp}] Formula generation completed!")
        basic_result = replace_icon_emoji_values(basic_result)  # emoji -> heroicon/lucide names
        
        # Yield control after formula generation
        await asyncio.sleep(0)
        
        # Extract hero ingredients for trend analysis
        hero_ingredients = []
        try:
            # Try to get from activeOptions -> recommendedFormula -> heroActives
            active_options = basic_result.get("activeOptions", {})
            recommended_formula = active_options.get("recommendedFormula", {})
            hero_actives = recommended_formula.get("heroActives", [])
            hero_ingredients = [ing.get("name", "") for ing in hero_actives if ing.get("name")]

            # Fallback to detected ingredients from wish_data
            if not hero_ingredients:
                hero_ingredients = wish_data.get("heroIngredients", [])
        except Exception as e:
            print(f"⚠️ [BACKGROUND] Error extracting hero ingredients: {e}")
            hero_ingredients = wish_data.get("heroIngredients", [])

        # Fetch trend data for hero ingredients (detailed analysis)
        trend_data = {}
        if hero_ingredients:
            try:
                timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
                print(f"📊 [BACKGROUND] [{timestamp}] Fetching trend data for {len(hero_ingredients)} hero ingredients...")
                trend_data = await fetch_trend_data_for_ingredients(hero_ingredients)
                timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
                print(f"✅ [BACKGROUND] [{timestamp}] Trend data fetched successfully")
            except Exception as e:
                print(f"⚠️ [BACKGROUND] Error fetching trend data: {e}")
                import traceback
                traceback.print_exc()

        # Market trends removed - use standalone /market-trends endpoint instead

        processing_time = time.time() - start_time
        processing_time_seconds = round(processing_time, 2)
        print(f"✅ Make a Wish formula generated in {processing_time_seconds}s")
        
        # Update database with completed status (including trend data)
        update_doc = {
            "basic_mode_result": basic_result,
            "trend_data": trend_data,  # Store trend analysis data
            "status": "completed",
            "processing_time": processing_time_seconds,
            "updated_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()
        }
        
        await wish_history_col.update_one(
            {"_id": ObjectId(history_id), "user_id": user_id},
            {"$set": update_doc}
        )
        
        timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
        print(f"💾 [BACKGROUND] [{timestamp}] Updating database with completed status...")
        print(f"[BACKGROUND] ✅ Updated history {history_id} with completed status")
        processing_success = True
        
        # Verify the status was actually updated to "completed" before sending notifications
        verify_doc = await wish_history_col.find_one({"_id": ObjectId(history_id)})
        if not verify_doc or verify_doc.get("status") != "completed":
            print(f"⚠️ [BACKGROUND] Status not confirmed as 'completed', skipping notifications")
            return
        
        # Deduct credits on success (gracefully handle if credits API doesn't exist)
        deduct_credits_result = None
        try:
            deduct_credits_result = await deduct_credits(
                user_id=user_id,
                reference_id=history_id,
                credit_key=CreditKey.MAKE_WISH_GENERATE,
                transaction_type="make_wish_generation_revised",
                description=f"Make a Wish formula generation (revised) - {history_id}",
                bearer_token=bearer_token
            )
            if deduct_credits_result is None:
                print(f"ℹ️ [BACKGROUND] Credit deduction skipped (credits API not available)")
        except Exception as credit_error:
            print(f"⚠️ [BACKGROUND] Failed to deduct credits: {credit_error}")
            # Don't fail the whole process if credit deduction fails
        
        # Build notification data; include credit info when available
        notification_data = {
            "history_id": history_id,
            "status": "completed",
            "type": "make_wish_revised"
        }
        
        # Add credit info to notification data - CRITICAL: Always include credit info in notification
        if deduct_credits_result:
            # Use actual values from third-party API response (not hardcoded)
            credits_deducted = deduct_credits_result.get("creditsDeducted")
            credits_remaining = deduct_credits_result.get("creditsRemaining")
            deducted = deduct_credits_result.get("deducted", True)
            
            # Ensure values are not None (convert to 0 if None)
            if credits_deducted is None:
                credits_deducted = 0
            if credits_remaining is None:
                credits_remaining = 0
            
            print(f"💰 [BACKGROUND] Credit info from API: deducted={credits_deducted}, remaining={credits_remaining}")
            print(f"💰 [BACKGROUND] Full deduct_credits_result: {deduct_credits_result}")
            
            # Add credit info in multiple places to ensure it's accessible
            # 1. Nested in deduct_credits object (for structured access)
            notification_data["deduct_credits"] = {
                "deducted": bool(deducted),
                "creditsDeducted": int(credits_deducted),
                "creditsRemaining": int(credits_remaining),
            }
            
            # 2. Also at top level of meta for direct access (for backward compatibility)
            notification_data["creditsDeducted"] = int(credits_deducted)
            notification_data["creditsRemaining"] = int(credits_remaining)
            notification_data["deducted"] = bool(deducted)
            
            print(f"💰 [BACKGROUND] Credit info added to notification_data: {notification_data.get('deduct_credits')}")
        else:
            print(f"⚠️ [BACKGROUND] No credit deduction result available - credit info not included in notification")
        
        # Send real-time WebSocket notification using enhanced notification module (ONLY after completion)
        try:
            notification_result = await notify_user_enhanced(
                user_id=user_id,
                module="make-wish",
                notification_type="success",
                title="Formula Generated Successfully!",
                message=f"Your formula '{name}' has been generated and is ready to view.",
                action=NotificationAction(
                    label="View Formula",
                    kind="route",
                    to=f"/make-wish/{history_id}"
                ),
                meta=notification_data,
                send_websocket=True
            )
            # Log the notification that was sent to verify credit info is included
            notification_dict = notification_result.model_dump() if hasattr(notification_result, 'model_dump') else {}
            print(f"✅ [BACKGROUND] Success notification sent via WebSocket")
            print(f"📋 [BACKGROUND] Full notification meta: {notification_dict.get('meta', {})}")
            if notification_dict.get('meta', {}).get('deduct_credits'):
                print(f"✅ [BACKGROUND] Credit info confirmed in notification: {notification_dict.get('meta', {}).get('deduct_credits')}")
            else:
                print(f"⚠️ [BACKGROUND] WARNING: Credit info NOT found in notification meta!")
        except Exception as ws_error:
            print(f"⚠️ [BACKGROUND] Failed to send WebSocket notification: {ws_error}")
        
    except Exception as e:
        processing_success = False
        error_message = str(e)
        timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
        print(f"❌ [BACKGROUND] [{timestamp}] ========================================")
        print(f"❌ [BACKGROUND] [{timestamp}] ERROR processing wish {history_id}: {e}")
        print(f"❌ [BACKGROUND] [{timestamp}] Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        print(f"❌ [BACKGROUND] [{timestamp}] ========================================")
        
        # Update database with failed status
        try:
            update_doc = {
                "status": "failed",
                "error_message": error_message,
                "updated_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()
            }
            
            await wish_history_col.update_one(
                {"_id": ObjectId(history_id), "user_id": user_id},
                {"$set": update_doc}
            )
        except Exception as db_error:
            print(f"❌ [BACKGROUND] Failed to update failed status: {db_error}")
        
        # Send real-time WebSocket notification using enhanced notification module
        try:
            await notify_user_enhanced(
                user_id=user_id,
                module="make-wish",
                notification_type="error",
                title="Formula Generation Failed",
                message=f"Sorry, we couldn't generate your formula '{name}'. Please try again.",
                meta={"history_id": history_id, "status": "failed", "type": "make_wish_revised", "error": error_message},
                send_websocket=True
            )
        except Exception as ws_error:
            print(f"⚠️ [BACKGROUND] Failed to send WebSocket notification: {ws_error}")


# ============================================================================
# HELPER FUNCTIONS FOR CREDITS AND NOTIFICATIONS
# ============================================================================

# Credit deduction is now handled by the reusable credit_service
# The deduct_credits function is imported above


# ============================================================================
# STAGE 3: GET ALTERNATIVES ENDPOINT
# ============================================================================

@router.post("/get-alternatives", response_model=GetAlternativesResponse)
async def get_ingredient_alternatives(
    request: GetAlternativesRequest,
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Get alternative ingredients for a specific hero ingredient.
    
    This endpoint provides alternatives for ingredients with:
    - Detailed descriptions and benefits
    - Cost impact analysis
    - Complexity compatibility
    - Usage considerations
    """
    try:
        print(f"🔄 Getting alternatives for: {request.ingredient_name}")
        
        # Get alternatives from database
        alternatives_data = get_alternatives_for_ingredient(request.ingredient_name)
        
        if not alternatives_data:
            raise HTTPException(
                status_code=404,
                detail=f"No alternatives found for {request.ingredient_name}"
            )
        
        # Filter alternatives by complexity
        all_alternatives = alternatives_data.get("variants", [])
        compatible_alternatives = [
            alt for alt in all_alternatives 
            if request.complexity in alt.get("complexity", [])
        ]
        
        # Find current variant
        current_variant = None
        if request.current_variant:
            for alt in all_alternatives:
                if alt.get("name") == request.current_variant or alt.get("inci") == request.current_variant:
                    current_variant = alt
                    break
        
        # Default to first variant if current not found
        if not current_variant and all_alternatives:
            current_variant = all_alternatives[0]
        
        # Format response
        response_data = {
            "success": True,
            "ingredient_name": request.ingredient_name,
            "current": {
                "name": current_variant.get("name", "Unknown"),
                "inci_name": current_variant.get("inci", "Unknown"),
                "icon": current_variant.get("icon", emoji_to_icon(current_variant.get("emoji", "🧪"), "flask")),
                "description": current_variant.get("description", ""),
                "benefit_tag": current_variant.get("benefit", ""),
                "suggested_percentage": current_variant.get("percentage", ""),
                "cost_impact": "similar",
                "complexity_fit": current_variant.get("complexity", []),
                "considerations": current_variant.get("considerations", "")
            },
            "alternatives": [
                {
                    "name": alt.get("name", "Unknown"),
                    "inci_name": alt.get("inci", "Unknown"),
                    "icon": alt.get("icon", emoji_to_icon(alt.get("emoji", "🌿"), "leaf")),
                    "description": alt.get("description", ""),
                    "benefit_tag": alt.get("benefit", ""),
                    "suggested_percentage": alt.get("percentage", ""),
                    "cost_impact": alt.get("cost_tier", "similar"),
                    "complexity_fit": alt.get("complexity", []),
                    "considerations": alt.get("considerations", "")
                }
                for alt in compatible_alternatives
                if alt != current_variant  # Exclude current from alternatives
            ]
        }
        
        print(f"✅ Found {len(response_data['alternatives'])} alternatives")
        
        return GetAlternativesResponse(**response_data)
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error getting alternatives: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting alternatives: {str(e)}"
        )

# STAGE 4.5: EDIT METADATA ENDPOINT
# ============================================================================

@router.patch("/{wishId}", response_model=dict)
async def edit_formula_metadata(
    wishId: str,
    request: dict,
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Edit formula metadata (name, tag, additional_notes) without changing formula itself.
    
    This endpoint allows users to:
    - Update formula name
    - Update tag for categorization  
    - Update additional_notes
    - Preserve all formula data unchanged
    """
    try:
        print(f"📝 Editing formula metadata: {wishId}")
        
        obj_id = ObjectId(wishId)
        # Extract user info
        user_id = current_user.get("user_id") or current_user.get("_id")
        
       # Allowed fields whitelist (defense-in-depth)
        ALLOWED_FIELDS = {"name", "tag", "additional_notes"}

          # Filter allowed fields only
        data = {k: v for k, v in request.items() if k in ALLOWED_FIELDS and v is not None}

        # Trim name
        if "name" in data and isinstance(data["name"], str):
            data["name"] = data["name"].strip()

        # No valid fields
        if not data:
            raise HTTPException(400, "No valid fields provided")

        # Build update document
        update_doc = {
            **data,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        # Get the wish item before update to get the name for notification
        wish_item = await wish_history_col.find_one({"_id": obj_id, "user_id": user_id})
        
        if not wish_item:
            raise HTTPException(404, "Formula not found or access denied")
        
        # Use updated name if name was changed, otherwise use existing name
        wish_name = data.get("name") if "name" in data else wish_item.get("name", "Wish")
        
        # Atomic update (ownership enforced)
        result = await wish_history_col.update_one(
            {"_id": obj_id, "user_id": user_id},
            {"$set": update_doc}
        )

        # Not found or unauthorized
        if result.matched_count == 0:
            raise HTTPException(404, "Formula not found or access denied")

        # Send notification for successful metadata update
        try:
            await notify_user_enhanced(
                user_id=user_id,
                module="make-wish",
                notification_type="success",
                title="Formula Updated!",
                message=f"Your formula '{wish_name}' metadata has been updated successfully.",
                action=NotificationAction(
                    label="View Formula",
                    kind="route",
                    to=f"/make-wish/{wishId}"
                ),
                meta={
                    "history_id": wishId,
                    "status": "updated",
                    "type": "make_wish_metadata_updated",
                    "updated_fields": list(data.keys()),
                    "wish_name": wish_name
                },
                send_websocket=False
            )
            print(f"✅ [METADATA UPDATE] Notification sent for formula metadata update: {wishId}")
        except Exception as notify_error:
            print(f"⚠️ [METADATA UPDATE] Failed to send notification: {notify_error}")
            # Don't fail the request if notification fails

        return {
            "success": True,
            "message": "Updated successfully"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error editing metadata: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


# ============================================================================
# STAGE 4: EDIT FORMULA ENDPOINT
# ============================================================================

@router.post("/edit-formula", response_model=EditFormulaResponse)
async def edit_formula(
    request: EditFormulaRequest,
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Edit a generated formula by adding, removing, or swapping ingredients.
    
    This endpoint allows users to:
    - Add new ingredients
    - Remove existing ingredients (with restrictions)
    - Swap ingredients for alternatives
    - Adjust ingredient percentages
    - Auto-rebalance formula after edits
    """
    try:
        print(f"✏️ Editing formula: {request.formula_id}")
        
        # Retrieve current formula from history
        user_id = current_user.get("user_id") or current_user.get("_id")
        history_item = await wish_history_col.find_one({
            "_id": ObjectId(request.history_id),
            "user_id": user_id,
            "formula_id": request.formula_id
        })
        
        if not history_item:
            raise HTTPException(
                status_code=404,
                detail="Formula not found or access denied"
            )
        
        # Always use basic_mode_result (only one mode now)
        current_formula = history_item.get("basic_mode_result") or {}
        current_complexity = history_item.get("complexity", "classic")
        
        # Validate operations
        validation_result = {
            "is_valid": True,
            "errors": [],
            "warnings": []
        }
        
        # Get complexity limits
        complexity_config = get_complexity_config(current_complexity)
        max_total = complexity_config["max_ingredients"]
        max_actives = complexity_config["active_slots"]
        
        # Track changes
        updated_ingredients = []
        removed_count = 0
        added_count = 0
        
        # Process operations
        for i, operation in enumerate(request.operations):
            op_type = operation.type
            
            if op_type == "remove":
                ingredient_id = operation.ingredient_id
                
                # Check if ingredient can be removed
                if ingredient_id in EDIT_RULES["cannot_remove"]:
                    validation_result["errors"].append({
                        "operation_index": i,
                        "message": f"Cannot remove {ingredient_id} - required for safety"
                    })
                    validation_result["is_valid"] = False
                elif ingredient_id in EDIT_RULES["warn_on_remove"]:
                    validation_result["warnings"].append({
                        "operation_index": i,
                        "message": f"Removing {ingredient_id} may affect stability"
                    })
                
                removed_count += 1
                
            elif op_type == "add":
                new_ingredient = operation.new_ingredient
                
                # Check complexity limits
                current_count = len(current_formula.get("ingredients", []))
                if current_count + added_count - removed_count >= max_total:
                    validation_result["errors"].append({
                        "operation_index": i,
                        "message": f"Cannot add ingredient - exceeds {current_complexity} complexity limit of {max_total}"
                    })
                    validation_result["is_valid"] = False
                
                added_count += 1
                
            elif op_type == "swap":
                # Swapping is essentially remove + add
                added_count += 1
                
            elif op_type == "adjust_percentage":
                # Percentage adjustments are generally valid
                pass
            else:
                validation_result["errors"].append({
                    "operation_index": i,
                    "message": f"Unknown operation type: {op_type}"
                })
                validation_result["is_valid"] = False
        
        if not validation_result["is_valid"]:
            return EditFormulaResponse(
                success=False,
                formula_id=request.formula_id,
                validation=validation_result,
                updated_formula=None,
                warnings=[w["message"] for w in validation_result["warnings"]]
            )
        
        # Apply operations (simplified for demo)
        # In production, this would be more sophisticated with actual ingredient database
        updated_formula = current_formula.copy()
        
        # Add operation notes
        operation_summary = f"Applied {len(request.operations)} operations: {', '.join([op.type for op in request.operations])}"
        
        print(f"✅ Formula edited successfully")
        print(f"   Operations: {len(request.operations)}")
        print(f"   Warnings: {len(validation_result['warnings'])}")
        
        return EditFormulaResponse(
            success=True,
            formula_id=request.formula_id,
            validation=validation_result,
            updated_formula=None,  # Would return actual updated formula
            warnings=[w["message"] for w in validation_result["warnings"]] + [operation_summary]
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error editing formula: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error editing formula: {str(e)}"
        )


# ============================================================================
# STAGE 5: REQUEST QUOTE ENDPOINT
# ============================================================================

@router.post("/request-quote", response_model=RequestQuoteResponse)
async def request_manufacturing_quote(
    request: RequestQuoteRequest,
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Get manufacturing cost quote for a formula.
    
    This endpoint provides:
    - Cost analysis for different quantities
    - Pricing guidance and MRP recommendations
    - Packaging cost estimates
    - Investment breakdown
    """
    try:
        print(f"💰 Generating quote for formula: {request.formula_id}")
        
        # Retrieve formula from history
        user_id = current_user.get("user_id") or current_user.get("_id")
        history_item = await wish_history_col.find_one({
            "_id": ObjectId(request.history_id),
            "user_id": user_id,
            "formula_id": request.formula_id
        })
        
        if not history_item:
            raise HTTPException(
                status_code=404,
                detail="Formula not found or access denied"
            )
        
        # Generate quote ID
        quote_id = str(uuid.uuid4())
        generated_at = datetime.now(timezone(timedelta(hours=5, minutes=30)))
        valid_until = generated_at + timedelta(days=7)  # Valid for 7 days
        
        # Calculate costs (simplified for demo)
        base_cost_per_100g = 45.50  # Base formula cost
        
        quotes = []
        for quantity in request.quantity_options:
            # Cost calculations
            raw_material_cost = base_cost_per_100g * (quantity / 100)
            packaging_cost_per_unit = 5.0 if request.include_packaging else 0
            total_cost_per_unit = raw_material_cost + packaging_cost_per_unit
            
            # Pricing guidance
            suggested_mrp = int(total_cost_per_unit * 4.5)  # 4.5x margin
            suggested_mrp_range = f"₹{int(suggested_mrp * 0.8)} - ₹{int(suggested_mrp * 1.2)}"
            estimated_margin = f"{int((suggested_mrp / total_cost_per_unit - 1) * 100)}%"
            
            total_investment = total_cost_per_unit * quantity
            total_investment_breakdown = {
                "raw_materials": raw_material_cost * quantity,
                "packaging": packaging_cost_per_unit * quantity,
                "total": total_investment
            }
            
            quotes.append({
                "quantity": quantity,
                "raw_material_cost_per_unit": raw_material_cost,
                "packaging_cost_per_unit": packaging_cost_per_unit,
                "total_cost_per_unit": total_cost_per_unit,
                "suggested_mrp": f"₹{suggested_mrp}",
                "suggested_mrp_range": suggested_mrp_range,
                "estimated_margin": estimated_margin,
                "total_investment": f"₹{int(total_investment):,}",
                "total_investment_breakdown": total_investment_breakdown
            })
        
        # Pricing guidance
        pricing_guidance = {
            "positioning": "Premium but accessible",
            "competitor_range": "₹399 - ₹799 for similar products",
            "recommended_mrp": f"₹{quotes[0]['suggested_mrp']}",
            "margin_explanation": f"At {quotes[0]['suggested_mrp']}, you'll have a healthy {quotes[0]['estimated_margin']} margin after accounting for manufacturing, packaging, and marketing costs."
        }
        
        print(f"✅ Quote generated successfully")
        print(f"   Quote ID: {quote_id}")
        print(f"   Quantities: {request.quantity_options}")
        print(f"   Valid until: {valid_until.strftime('%Y-%m-%d')}")
        
        # Save quote to database
        quote_doc = {
            "quote_id": quote_id,
            "formula_id": request.formula_id,
            "history_id": request.history_id,
            "user_id": user_id,
            "quantity_options": request.quantity_options,
            "include_packaging": request.include_packaging,
            "packaging_type": request.packaging_type,
            "quotes": quotes,
            "pricing_guidance": pricing_guidance,
            "generated_at": generated_at.isoformat(),
            "valid_until": valid_until.isoformat(),
            "status": "active",
            "created_at": generated_at.isoformat()
        }
        
        try:
            result = await quotes_col.insert_one(quote_doc)
            print(f"💾 Saved quote: {quote_id}")
        except Exception as db_error:
            print(f"⚠️ Warning: Failed to save quote: {db_error}")
            # Continue without failing the response
        
        return RequestQuoteResponse(
            success=True,
            formula_id=request.formula_id,
            quote_id=quote_id,
            generated_at=generated_at,
            valid_until=valid_until,
            quotes=quotes,
            pricing_guidance=pricing_guidance
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error generating quote: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error generating quote: {str(e)}"
        )


# ============================================================================
# STAGE 6: GET THIS MADE ENDPOINT
# ============================================================================

@router.post("/get-this-made", response_model=GetThisMadeResponse)
async def submit_commercialization_request(
    request: GetThisMadeRequest,
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Submit commercialization request for a formula.
    
    This endpoint:
    - Assigns queue number
    - Creates commercialization profile
    - Provides next steps
    - Sets up commitment information
    """
    try:
        print(f"🚀 Submitting commercialization request...")
        
        # Validate history_id format (MongoDB ObjectId must be 24 hex characters)
        if not request.history_id or len(request.history_id) != 24:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid history_id format. Expected 24-character MongoDB ObjectId, got: '{request.history_id}' (length: {len(request.history_id) if request.history_id else 0})"
            )
        
        # Validate formula exists
        user_id = current_user.get("user_id") or current_user.get("_id")
        
        # Try to convert to ObjectId with better error handling
        try:
            history_obj_id = ObjectId(request.history_id)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid history_id format: '{request.history_id}'. Must be a valid MongoDB ObjectId (24 hex characters). Error: {str(e)}"
            )
        
        # First, find the history item by _id and user_id
        history_item = await wish_history_col.find_one({
            "_id": history_obj_id,
            "user_id": user_id
        })
        
        if not history_item:
            raise HTTPException(
                status_code=404,
                detail="Formula not found or access denied"
            )
        
        # Extract formula_id from document (check both root level and parsed_data)
        formula_id_from_doc = (
            history_item.get("formula_id") 
            or history_item.get("parsed_data", {}).get("formula_id")
        )
        
        # Use formula_id from document if available, otherwise use the one from request
        # This handles cases where formula_id is stored in parsed_data instead of root
        formula_id_to_use = formula_id_from_doc or request.formula_id
        
        if not formula_id_to_use:
            raise HTTPException(
                status_code=400,
                detail="Formula ID not found in document and not provided in request"
            )
        
        # If document has formula_id and it differs from request, use the document's one
        if formula_id_from_doc and formula_id_from_doc != request.formula_id:
            print(f"⚠️ Formula ID mismatch: Document has '{formula_id_from_doc}', Request has '{request.formula_id}'. Using document's formula_id.")
            formula_id_to_use = formula_id_from_doc
        
        # Check if QMS query already exists for this formula
        existing_query = await qms_queries_col.find_one({
            "user_id": user_id,
            "formula_id": formula_id_to_use,
            "wish_id": request.history_id,  # Check by wish_id (history_id)
            "status": {"$nin": ["completed", "cancelled"]}  # Active queries only
        })
        
        if existing_query:
            display_id = existing_query.get("display_id", "N/A")
            raise HTTPException(
                status_code=409,
                detail=f"Commercialization request already exists for this formula. Query ID: {display_id}"
            )
        
        # Generate queue number (for display purposes) - simple sequential starting from 221
        queue_number = await generate_queue_number()
        created_at = datetime.now(timezone(timedelta(hours=5, minutes=30)))
        
        # Define next steps based on experience level
        next_steps = []
        if request.experience_level == "dreaming":
            next_steps = [
                {
                    "order": 1,
                    "icon": "phone-arrow-up-right",  # Consultation
                    "title": "Consultation Call",
                    "description": "Our formulation expert will call you to understand your vision and requirements",
                    "estimated_timeline": "1-2 business days"
                },
                {
                    "order": 2,
                    "icon": "beaker",  # Sample development
                    "title": "Sample Development",
                    "description": "We'll create and test samples based on your formula",
                    "estimated_timeline": "2-3 weeks"
                },
                {
                    "order": 3,
                    "icon": "document-check",  # Regulatory review
                    "title": "Regulatory Review",
                    "description": "Complete compliance and documentation review",
                    "estimated_timeline": "1 week"
                },
                {
                    "order": 4,
                    "icon": "building-office-2",  # Production planning
                    "title": "Production Planning",
                    "description": "Finalize manufacturing specifications and schedule",
                    "estimated_timeline": "1 week"
                }
            ]
        elif request.experience_level == "ready":
            next_steps = [
                {
                    "order": 1,
                    "icon": "beaker",
                    "title": "Sample Batch",
                    "description": "Create production samples for your approval",
                    "estimated_timeline": "1-2 weeks"
                },
                {
                    "order": 2,
                    "icon": "document-text",
                    "title": "Final Documentation",
                    "description": "Prepare all manufacturing and compliance documents",
                    "estimated_timeline": "3-5 days"
                },
                {
                    "order": 3,
                    "icon": "factory",  # Requires Heroicons v2 custom or fallback
                    "title": "Production Start",
                    "description": "Begin manufacturing your product",
                    "estimated_timeline": "2-3 weeks"
                }
            ]
        else:
            next_steps = [
                {
                    "order": 1,
                    "icon": "chat-bubble-left-right",
                    "title": "Discovery Call",
                    "description": "Let's discuss your product goals and timeline",
                    "estimated_timeline": "1-2 business days"
                },
                {
                    "order": 2,
                    "icon": "chart-bar",
                    "title": "Feasibility Analysis",
                    "description": "Technical and commercial viability assessment",
                    "estimated_timeline": "1 week"
                }
            ]
        
        # Commitment information
        # commitment_info = {
        #     "amount": 5000,
        #     "currency": "INR",
        #     "refundable": True,
        #     "refund_policy": "100% refundable if you decide not to proceed after consultation",
        #     "platform_charges": "No platform charges",
        #     "purpose": "To ensure dedicated time and resources for your project"
        # }
        
        # ========================================================================
        # CREATE QMS QUERY (Single source of truth - replaces commercialization_requests)
        # ========================================================================
        query_id = None
        query_display_id = None
        try:
            from app.ai_ingredient_intelligence.api.qms_utils import create_query_from_commercialization
            
            # DEBUG: Log the entire request to see what frontend is sending
            print(f"🔍 [DEBUG] get-this-made request received:")
            print(f"   payment_id from request: {request.payment_id}")
            print(f"   payment_id type: {type(request.payment_id)}")
            print(f"   request dict: {request.model_dump()}")
            
            # Get formula name from wish_history
            formula_name = history_item.get("name") or history_item.get("formula_name") or "Custom Formula"
            
            # Ensure additional_notes is a string (not array)
            additional_notes_str = None
            if request.additional_notes:
                if isinstance(request.additional_notes, list):
                    additional_notes_str = ", ".join(str(note) for note in request.additional_notes)
                else:
                    additional_notes_str = str(request.additional_notes)
            
            # Handle payment_id - fetch from existing query if not provided, or create if valid ObjectId
            payment_id_to_store = None
            print(f"🔍 [DEBUG] Checking payment_id: {request.payment_id}")
            
            # First, check if we have a query_id in wish_history - if so, fetch payment_id from that query
            query_id_from_history = history_item.get("query_id")
            if not request.payment_id and query_id_from_history:
                try:
                    print(f"🔍 [DEBUG] Found query_id in wish_history: {query_id_from_history}, fetching payment_id...")
                    existing_query_by_id = await qms_queries_col.find_one({
                        "_id": ObjectId(query_id_from_history),
                        "user_id": user_id
                    })
                    if existing_query_by_id and existing_query_by_id.get("payment_id"):
                        payment_id_from_query = existing_query_by_id.get("payment_id")
                        print(f"✅ [DEBUG] Found payment_id from query_id {query_id_from_history}: {payment_id_from_query}")
                        payment_id_to_store = str(payment_id_from_query) if payment_id_from_query else None
                except Exception as e:
                    print(f"⚠️ [DEBUG] Error fetching payment_id from query_id: {e}")
            
            if request.payment_id:
                # Payment ID provided in request - validate and use it
                try:
                    payment_obj_id = ObjectId(request.payment_id)
                    # Check if payment document exists
                    from app.ai_ingredient_intelligence.db.collections import qms_payments_col
                    existing_payment = await qms_payments_col.find_one({"_id": payment_obj_id})
                    if not existing_payment:
                        print(f"⚠️ Payment document not found for ID: {request.payment_id}, creating placeholder...")
                        # Create a placeholder payment document
                        payment_doc = {
                            "_id": payment_obj_id,
                            "user_id": user_id,
                            "amount": 0,  # Will be updated when actual payment is processed
                            "currency": "INR",
                            "status": "created",
                            "created_at": datetime.now(timezone(timedelta(hours=5, minutes=30)))
                        }
                        await qms_payments_col.insert_one(payment_doc)
                        print(f"✅ Created placeholder payment document: {request.payment_id}")
                    payment_id_to_store = request.payment_id
                    print(f"✅ [DEBUG] payment_id validated and stored: {payment_id_to_store}")
                except Exception as e:
                    # payment_id is not a valid ObjectId, store it as-is (might be a reference ID)
                    print(f"⚠️ payment_id '{request.payment_id}' is not a valid ObjectId, storing as string: {e}")
                    payment_id_to_store = request.payment_id
            else:
                # No payment_id in request - fetch from queries collection (source of truth)
                print(f"⚠️ [DEBUG] No payment_id provided in request - checking queries collection...")
                try:
                    # Check for any query (even completed/cancelled) for this formula/history_id
                    # Queries collection is the source of truth for payment_id
                    # We check by wish_id (history_id) to find related queries
                    any_query = await qms_queries_col.find_one({
                        "user_id": user_id,
                        "wish_id": request.history_id,  # Check by wish_id (history_id)
                    }, sort=[("created_at", -1)])  # Get most recent query
                    
                    if any_query and any_query.get("payment_id"):
                        payment_id_from_query = any_query.get("payment_id")
                        print(f"✅ [DEBUG] Found payment_id in queries collection (query: {any_query.get('display_id', 'N/A')}): {payment_id_from_query}")
                        payment_id_to_store = str(payment_id_from_query) if payment_id_from_query else None
                    else:
                        print(f"ℹ️ [DEBUG] No payment_id found in queries collection for this formula/history_id")
                        payment_id_to_store = None
                except Exception as e:
                    print(f"⚠️ [DEBUG] Error checking queries collection for payment_id: {e}")
                    import traceback
                    traceback.print_exc()
                    payment_id_to_store = None
            
            print(f"🔍 [DEBUG] payment_id_to_store before creating query: {payment_id_to_store}")
            
            # Create query with all form fields
            query_id = await create_query_from_commercialization(
                user_id=user_id,
                wish_history_id=request.history_id,
                formula_id=formula_id_to_use,  # Use the formula_id from document or request
                formula_name=formula_name,
                experience_level=request.experience_level,
                timeline=request.timeline,
                quantity_interest=request.quantity_interest,
                additional_notes=additional_notes_str,  # Ensure it's a string
                payment_id=payment_id_to_store,  # Pass payment_id (validated/created above)
                queue_number=queue_number,  # Pass queue number to store in query
                user_name=request.name,  # Store user name from form
                user_phone=request.phone,  # Store user phone from form
                user_city=request.city,  # Store user city from form
                user_email=request.email,  # Store user email from form
                user_pincode=request.pincode  # Store user pincode from form
            )
            
            # Get query display_id for logging and response
            if query_id:
                query_obj = await qms_queries_col.find_one({"_id": ObjectId(query_id)})
                if query_obj:
                    query_display_id = query_obj.get("display_id")
                    print(f"✅ Created QMS query: {query_display_id} (Queue: {queue_number})")
                    
                    # Update wish_history to mark it as converted to query (store query_id and payment_id)
                    try:
                        update_fields = {
                            "query_id": query_id,
                            "updated_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()
                        }
                        # Add payment_id if provided
                        if request.payment_id:
                            update_fields["payment_id"] = request.payment_id
                        # Add additional_notes if provided (as string)
                        if additional_notes_str:
                            update_fields["additional_notes"] = additional_notes_str
                        
                        await wish_history_col.update_one(
                            {"_id": ObjectId(request.history_id), "user_id": user_id},
                            {"$set": update_fields}
                        )
                        print(f"✅ Updated wish_history with query_id: {query_id}" + (f" and payment_id: {request.payment_id}" if request.payment_id else ""))
                    except Exception as history_update_error:
                        print(f"⚠️ Warning: Failed to update wish_history: {history_update_error}")
                        # Don't fail the request if history update fails
            
        except Exception as qms_error:
            print(f"❌ Failed to create QMS query: {qms_error}")
            import traceback
            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create commercialization request: {str(qms_error)}"
            )
        
        # Ensure query_display_id is set (fallback if query creation failed)
        if not query_display_id and query_id:
            # Try to fetch display_id one more time
            try:
                query_obj = await qms_queries_col.find_one({"_id": ObjectId(query_id)})
                if query_obj:
                    query_display_id = query_obj.get("display_id")
            except Exception as e:
                print(f"⚠️ Warning: Could not fetch display_id: {e}")
        
        print(f"✅ Commercialization request submitted")
        print(f"   Queue Number: {queue_number}")
        print(f"   Query ID: {query_display_id or query_id or 'N/A'}")
        print(f"   Experience Level: {request.experience_level}")
        print(f"   Timeline: {request.timeline}")
        
        # Validate that we have at least query_id before returning
        if not query_id:
            raise HTTPException(
                status_code=500,
                detail="Failed to create QMS query. Please try again."
            )
        
        return GetThisMadeResponse(
            success=True,
            queue_number=queue_number,
            request_id=query_display_id or f"QRY-{query_id[:8]}",  # Fallback to partial ID if display_id missing
            created_at=created_at,
            next_steps=next_steps,
            query_id=query_id,
            query_display_id=query_display_id,
            # commitment_info=commitment_info
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error submitting commercialization request: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error submitting request: {str(e)}"
        )


# ============================================================================
# EXPORT ENDPOINTS
# ============================================================================

@router.post("/export-to-inspiration-board")
async def export_make_wish_revised_to_board(
    request: dict,
    current_user: dict = Depends(verify_jwt_token)
):
    """Export revised make a wish formulations to inspiration board"""
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
                    feature_type="make_wish_revised",
                    history_ids=history_ids
                )
            ]
        )
        
        # Call the inspiration boards export endpoint
        from app.ai_ingredient_intelligence.api.inspiration_boards import export_to_board_endpoint
        result = await export_to_board_endpoint(export_request, current_user)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"ERROR exporting revised make a wish to board: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ADDITIONAL ENDPOINTS: Packaging, PPT Generation, Market Trends
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
        "success": true,
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
        },
        "count": 10
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
# MARKET TRENDS: HELPER AND BACKGROUND TASKS
# ============================================================================

def _extract_market_trends_context(history_doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract hero_ingredients, benefits, product_type, category, parsed_data, and name from wish_history doc.
    Returns None if parsed_data is missing or both hero_ingredients and benefits are empty.
    """
    parsed_data = history_doc.get("parsed_data") or {}
    wish_data = history_doc.get("wish_data") or {}
    hero_ingredients = []
    detected_ingredients = parsed_data.get("detected_ingredients", [])
    if detected_ingredients:
        hero_ingredients = [
            ing.get("name", str(ing)) if isinstance(ing, dict) else str(ing)
            for ing in detected_ingredients
        ]
    else:
        hero_ingredients = (
            parsed_data.get("hero_ingredients") or
            wish_data.get("hero_ingredients") or
            history_doc.get("hero_ingredients") or
            []
        )
    benefits = (
        parsed_data.get("detected_benefits") or
        parsed_data.get("benefits") or
        wish_data.get("benefits") or
        history_doc.get("benefits") or
        []
    )
    product_type_obj = parsed_data.get("product_type", {})
    if isinstance(product_type_obj, dict):
        product_type = product_type_obj.get("id") or product_type_obj.get("name") or None
    else:
        product_type = str(product_type_obj) if product_type_obj else None
    if not product_type:
        product_type = wish_data.get("product_type") or history_doc.get("product_type") or None
    category = (
        parsed_data.get("category") or
        wish_data.get("category") or
        history_doc.get("category") or
        "skincare"
    )
    name = (history_doc.get("name") or history_doc.get("wish_text") or "Wish")[:80]
    if not parsed_data or (not hero_ingredients and not benefits):
        return None
    return {
        "hero_ingredients": hero_ingredients,
        "benefits": benefits,
        "product_type": product_type,
        "category": category,
        "parsed_data": parsed_data,
        "name": name,
    }


async def process_market_trends_background_with_semaphore(
    history_id: str,
    user_id: str,
    max_age_days: int,
    use_fallback: bool,
):
    """Acquire semaphore then run market trends background task (same pattern as generate-revised)."""
    timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
    print(f"🔒 [BACKGROUND-MT] [{timestamp}] Waiting for semaphore for history_id: {history_id}")
    semaphore = await get_background_task_semaphore()
    async with semaphore:
        await asyncio.sleep(0)
        await process_market_trends_background(
            history_id=history_id,
            user_id=user_id,
            max_age_days=max_age_days,
            use_fallback=use_fallback,
        )
    timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
    print(f"🔓 [BACKGROUND-MT] [{timestamp}] Semaphore released for history_id: {history_id}")


async def process_market_trends_background(
    history_id: str,
    user_id: str,
    max_age_days: int,
    use_fallback: bool,
):
    """
    Background task: fetch market trends, save to wish_history, send WebSocket notifications.
    Same notification pattern as generate-revised (success with action to view, error with message).
    """
    timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
    print(f"🚀 [BACKGROUND-MT] [{timestamp}] Starting market trends for history_id: {history_id}")
    error_message = None
    try:
        history_doc = await wish_history_col.find_one({
            "_id": ObjectId(history_id),
            "user_id": user_id,
        })
        if not history_doc:
            error_message = "History item not found or access denied"
            await wish_history_col.update_one(
                {"_id": ObjectId(history_id)},
                {"$set": {
                    "market_trends_status": "failed",
                    "market_trends_error": error_message,
                    "updated_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat(),
                }}
            )
            await notify_user_enhanced(
                user_id=user_id,
                module="make-wish",
                notification_type="error",
                title="Market Trends Failed",
                message=error_message,
                meta={"history_id": history_id, "status": "failed", "type": "market_trends", "error": error_message},
                send_websocket=True,
            )
            return
        ctx = _extract_market_trends_context(history_doc)
        if not ctx:
            error_message = "parsed_data or hero ingredients/benefits missing. Parse the wish first."
            await wish_history_col.update_one(
                {"_id": ObjectId(history_id)},
                {"$set": {
                    "market_trends_status": "failed",
                    "market_trends_error": error_message,
                    "updated_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat(),
                }}
            )
            await notify_user_enhanced(
                user_id=user_id,
                module="make-wish",
                notification_type="error",
                title="Market Trends Failed",
                message=error_message,
                meta={"history_id": history_id, "status": "failed", "type": "market_trends", "error": error_message},
                send_websocket=True,
            )
            return
        trends_service = MarketTrendsService()
        trends_data = await trends_service.fetch_trends_for_wish(
            hero_ingredients=ctx["hero_ingredients"],
            benefits=ctx["benefits"],
            product_type=ctx["product_type"],
            category=ctx["category"],
            max_age_days=max_age_days,
            use_fallback=use_fallback,
            parsed_data=ctx["parsed_data"],
        )
        update_data = {
            "market_trends": trends_data,
            "market_trends_fetched_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat(),
            "market_trends_status": "completed",
            "updated_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat(),
        }
        await wish_history_col.update_one(
            {"_id": ObjectId(history_id)},
            {"$set": update_data},
        )
        print(f"✅ [BACKGROUND-MT] Market trends saved for history_id: {history_id}")
        notification_data = {
            "history_id": history_id,
            "status": "completed",
            "type": "market_trends",
        }
        await notify_user_enhanced(
            user_id=user_id,
            module="make-wish",
            notification_type="success",
            title="Market Trends Ready",
            message=f"Market trends for '{ctx['name']}' are ready to view.",
            action=NotificationAction(
                label="View Market Trends",
                kind="route",
                to=f"/make-wish/{history_id}",
            ),
            meta=notification_data,
            send_websocket=True,
        )
        print(f"✅ [BACKGROUND-MT] Success notification sent for history_id: {history_id}")
    except Exception as e:
        error_message = str(e)
        timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
        print(f"❌ [BACKGROUND-MT] [{timestamp}] Error: {e}")
        import traceback
        traceback.print_exc()
        try:
            await wish_history_col.update_one(
                {"_id": ObjectId(history_id), "user_id": user_id},
                {"$set": {
                    "market_trends_status": "failed",
                    "market_trends_error": error_message,
                    "updated_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat(),
                }},
            )
        except Exception as db_err:
            print(f"❌ [BACKGROUND-MT] Failed to update failed status: {db_err}")
        name = "Wish"
        try:
            doc = await wish_history_col.find_one({"_id": ObjectId(history_id)})
            if doc:
                name = (doc.get("name") or doc.get("wish_text") or name)[:80]
        except Exception:
            pass
        try:
            await notify_user_enhanced(
                user_id=user_id,
                module="make-wish",
                notification_type="error",
                title="Market Trends Failed",
                message=f"Sorry, we couldn't fetch market trends for '{name}'. Please try again.",
                meta={"history_id": history_id, "status": "failed", "type": "market_trends", "error": error_message},
                send_websocket=True,
            )
        except Exception as ws_error:
            print(f"⚠️ [BACKGROUND-MT] Failed to send WebSocket notification: {ws_error}")


# ============================================================================
# MARKET TRENDS ENDPOINT
# ============================================================================

@router.post("/market-trends/{history_id}", response_model=MarketTrendsAcceptedResponse)
async def fetch_market_trends(
    history_id: str,
    max_age_days: int = Query(35, description="Maximum age of cached data in days"),
    use_fallback: bool = Query(True, description="Whether to use SerpAPI if MongoDB has no data"),
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Request market trends for a wish (async, same pattern as generate-revised).
    
    Returns immediately with success and history_id. Processing runs in the background.
    When finished, market trends are saved to wish_history and a WebSocket notification
    is sent (success with "View Market Trends" or error). Use the same WebSocket channel
    as generate-revised (make-wish module).
    
    PATH PARAMETER:
    - history_id: MongoDB ObjectId of the wish history item
    
    QUERY PARAMETERS (optional):
    - max_age_days: Maximum age of cached data in days (default: 35)
    - use_fallback: Whether to use SerpAPI if MongoDB has no data (default: true)
    
    RESPONSE (immediate):
    - success: true (request accepted)
    - history_id: use to poll detail or listen for WebSocket notification
    """
    user_id_value = current_user.get("user_id") or current_user.get("_id")
    if not user_id_value:
        raise HTTPException(status_code=400, detail="User ID not found in JWT token")
    if not ObjectId.is_valid(history_id):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid history_id format. Expected MongoDB ObjectId, got: {history_id[:50]}"
        )
    history_doc = await wish_history_col.find_one({
        "_id": ObjectId(history_id),
        "user_id": user_id_value,
    })
    if not history_doc:
        raise HTTPException(status_code=404, detail="History item not found or doesn't belong to user")
    ctx = _extract_market_trends_context(history_doc)
    if not ctx:
        raise HTTPException(
            status_code=400,
            detail="parsed_data is required and at least one of hero ingredients or benefits. Parse the wish first using /parse-wish."
        )
    try:
        await wish_history_col.update_one(
            {"_id": ObjectId(history_id)},
            {"$set": {
                "market_trends_status": "in_progress",
                "updated_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat(),
            }},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set market trends status: {str(e)}")
    background_coro = process_market_trends_background_with_semaphore(
        history_id=history_id,
        user_id=user_id_value,
        max_age_days=max_age_days,
        use_fallback=use_fallback,
    )
    asyncio.create_task(handle_background_task_safely(background_coro))
    await asyncio.sleep(0)  # Yield so response is sent immediately and other requests aren't delayed
    return MarketTrendsAcceptedResponse(success=True, history_id=history_id, status="in_progress")


# ============================================================================
# MARKET POSITION (YOUR MARKET POSITION) - externalproducts collection
# ============================================================================

def _extract_market_position_context(history_doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract hero_ingredients, product_type, category, and your_product (from basic_mode_result) for market position.
    Returns None if no hero ingredients and formula not yet generated.
    """
    parsed_data = history_doc.get("parsed_data") or {}
    hero_ingredients = []
    for ing in parsed_data.get("detected_ingredients", []) or []:
        name = ing.get("name", str(ing)) if isinstance(ing, dict) else str(ing)
        if name:
            hero_ingredients.append(name)
    if not hero_ingredients:
        hero_ingredients = parsed_data.get("hero_ingredients") or history_doc.get("hero_ingredients") or []
    product_type_obj = parsed_data.get("product_type", {})
    product_type = product_type_obj.get("id") or product_type_obj.get("name") if isinstance(product_type_obj, dict) else str(product_type_obj) if product_type_obj else None
    category = parsed_data.get("category") or history_doc.get("category") or "skincare"
    name = (history_doc.get("name") or history_doc.get("wish_text") or "Wish")[:80]

    your_product = {}
    basic_result = history_doc.get("basic_mode_result")
    if basic_result and isinstance(basic_result, dict):
        formula = basic_result.get("formula", {}) or {}
        tech = formula.get("technicalFormula", {}) or {}
        cost_per_100g = tech.get("totalCostPer100g") or tech.get("total_cost_per_100g")
        your_product["formula_name"] = formula.get("formulaName") or formula.get("formula_name") or name
        your_product["cost_per_100g"] = cost_per_100g
        bn = formula.get("businessNumbers", {}) or {}
        rec_sizes = bn.get("packagingOptions", {}).get("recommendedSizes") or bn.get("recommendedSizes") or []
        if rec_sizes:
            first = rec_sizes[0]
            your_product["size"] = first.get("size", "30g") if isinstance(first, dict) else str(first)
        else:
            your_product["size"] = "30g"

    if not hero_ingredients and not your_product.get("formula_name"):
        return None
    return {
        "hero_ingredients": hero_ingredients,
        "product_type": product_type,
        "category": category,
        "your_product": your_product,
        "name": name,
    }


async def process_market_position_background_with_semaphore(
    history_id: str,
    user_id: str,
):
    """Acquire semaphore then run market position background task (same pattern as market-trends)."""
    timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
    print(f"🔒 [BACKGROUND-MP] [{timestamp}] Waiting for semaphore for history_id: {history_id}")
    semaphore = await get_background_task_semaphore()
    async with semaphore:
        await asyncio.sleep(0)
        await process_market_position_background(history_id=history_id, user_id=user_id)
    timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
    print(f"🔓 [BACKGROUND-MP] [{timestamp}] Semaphore released for history_id: {history_id}")


async def process_market_position_background(history_id: str, user_id: str):
    """
    Background task: fetch market position from externalproducts, save to wish_history, send WebSocket notification.
    Same notification pattern as market-trends.
    """
    timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
    print(f"🚀 [BACKGROUND-MP] [{timestamp}] Starting market position for history_id: {history_id}")
    error_message = None
    try:
        history_doc = await wish_history_col.find_one({"_id": ObjectId(history_id), "user_id": user_id})
        if not history_doc:
            error_message = "History item not found or access denied"
            await wish_history_col.update_one(
                {"_id": ObjectId(history_id)},
                {"$set": {
                    "market_position_status": "failed",
                    "market_position_error": error_message,
                    "updated_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat(),
                }}
            )
            await notify_user_enhanced(
                user_id=user_id,
                module="make-wish",
                notification_type="error",
                title="Market Position Failed",
                message=error_message,
                meta={"history_id": history_id, "status": "failed", "type": "market_position", "error": error_message},
                send_websocket=True,
            )
            return
        ctx = _extract_market_position_context(history_doc)
        if not ctx:
            error_message = "Hero ingredients or formula data missing. Generate the formula first or ensure parsed_data has detected_ingredients."
            await wish_history_col.update_one(
                {"_id": ObjectId(history_id)},
                {"$set": {
                    "market_position_status": "failed",
                    "market_position_error": error_message,
                    "updated_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat(),
                }}
            )
            await notify_user_enhanced(
                user_id=user_id,
                module="make-wish",
                notification_type="error",
                title="Market Position Failed",
                message=error_message,
                meta={"history_id": history_id, "status": "failed", "type": "market_position", "error": error_message},
                send_websocket=True,
            )
            return
        position_data = await fetch_market_position_from_external_products(
            hero_ingredients=ctx["hero_ingredients"],
            product_type=ctx.get("product_type"),
            category=ctx.get("category", "skincare"),
            your_product=ctx.get("your_product"),
        )
        await wish_history_col.update_one(
            {"_id": ObjectId(history_id)},
            {"$set": {
                "market_position": position_data,
                "market_position_fetched_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat(),
                "market_position_status": "completed",
                "updated_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat(),
            }}
        )
        print(f"✅ [BACKGROUND-MP] Market position saved for history_id: {history_id}")
        await notify_user_enhanced(
            user_id=user_id,
            module="make-wish",
            notification_type="success",
            title="Market Position Ready",
            message=f"Your market position for '{ctx.get('name', '')}' is ready to view.",
            action=NotificationAction(
                label="View Market Position",
                kind="route",
                to=f"/make-wish/{history_id}",
            ),
            meta={"history_id": history_id, "status": "completed", "type": "market_position"},
            send_websocket=True,
        )
    except Exception as e:
        error_message = str(e)
        print(f"❌ [BACKGROUND-MP] Market position failed: {error_message}")
        import traceback
        traceback.print_exc()
        try:
            await wish_history_col.update_one(
                {"_id": ObjectId(history_id)},
                {"$set": {
                    "market_position_status": "failed",
                    "market_position_error": error_message,
                    "updated_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat(),
                }}
            )
        except Exception:
            pass
        await notify_user_enhanced(
            user_id=user_id,
            module="make-wish",
            notification_type="error",
            title="Market Position Failed",
            message=f"Sorry, we couldn't fetch market position. Please try again.",
            meta={"history_id": history_id, "status": "failed", "type": "market_position", "error": error_message},
            send_websocket=True,
        )


@router.post("/market-position/{history_id}", response_model=MarketPositionAcceptedResponse)
async def fetch_market_position(
    history_id: str,
    current_user: dict = Depends(verify_jwt_token),
):
    """
    Request market position (Your Market Position) for a wish. Uses externalproducts collection only (no clause search).
    Same async pattern as /market-trends: returns immediately; data saved to wish_history and WebSocket notification when done.
    """
    user_id_value = current_user.get("user_id") or current_user.get("_id")
    if not user_id_value:
        raise HTTPException(status_code=400, detail="User ID not found in JWT token")
    if not ObjectId.is_valid(history_id):
        raise HTTPException(status_code=400, detail=f"Invalid history_id format. Expected MongoDB ObjectId, got: {history_id[:50]}")
    history_doc = await wish_history_col.find_one({"_id": ObjectId(history_id), "user_id": user_id_value})
    if not history_doc:
        raise HTTPException(status_code=404, detail="History item not found or doesn't belong to user")
    ctx = _extract_market_position_context(history_doc)
    if not ctx:
        raise HTTPException(
            status_code=400,
            detail="Hero ingredients or formula data missing. Generate the formula first or ensure parsed_data has detected_ingredients."
        )
    try:
        await wish_history_col.update_one(
            {"_id": ObjectId(history_id)},
            {"$set": {
                "market_position_status": "in_progress",
                "updated_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat(),
            }},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set market position status: {str(e)}")
    background_coro = process_market_position_background_with_semaphore(history_id=history_id, user_id=user_id_value)
    asyncio.create_task(handle_background_task_safely(background_coro))
    await asyncio.sleep(0)
    return MarketPositionAcceptedResponse(success=True, history_id=history_id, status="in_progress")


# ============================================================================
# PPT GENERATION ENDPOINT
# ============================================================================

# Helper functions for PPT generation
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
                "cost_per_kg": ing.get("cost", 0) * 1000 if ing.get("cost") else 0,
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
        phase_id = phase.get("id") or phase.get("phase", "")
        for ing in phase.get("ingredients", []):
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
    
    return {
        "raw_material_cost": {
            "total_per_100g": cost_per_100g,
            "total_per_unit": cost_per_100g  # Assuming 100g unit
        },
        "packaging_cost": business_numbers.get("packagingOptions", {}).get("total", 0) if business_numbers else 0,
        "total_cost": cost_per_100g + (business_numbers.get("packagingOptions", {}).get("total", 0) if business_numbers else 0)
    }


def format_wish_data_for_gamma(wish_data: Dict[str, Any]) -> str:
    """
    Format wish data dictionary into a readable text string for Gamma PPT generation.
    
    This function converts the structured wish data (formula, ingredients, costs, etc.)
    into a comprehensive text format that Gamma API can use to generate a presentation.
    
    Args:
        wish_data: Dictionary containing wish data, formula, ingredients, costs, etc.
        
    Returns:
        Formatted text string ready for Gamma API
    """
    import json
    
    sections = []
    
    # 1. Wish Data / Product Overview
    wish_info = wish_data.get("wish_data") or wish_data.get("parsed_data") or {}
    if wish_info:
        sections.append("=" * 80)
        sections.append("PRODUCT OVERVIEW")
        sections.append("=" * 80)
        if isinstance(wish_info, dict):
            for key, value in wish_info.items():
                if value and key not in ["_id", "created_at", "updated_at"]:
                    sections.append(f"{key.replace('_', ' ').title()}: {value}")
        else:
            sections.append(str(wish_info))
        sections.append("")
    
    # 2. Ingredient Selection
    ingredient_selection = wish_data.get("ingredient_selection", {})
    if ingredient_selection:
        sections.append("=" * 80)
        sections.append("INGREDIENT SELECTION")
        sections.append("=" * 80)
        
        formula_name = ingredient_selection.get("formula_name") or ingredient_selection.get("formulaName", "")
        if formula_name:
            sections.append(f"Formula Name: {formula_name}")
        
        formula_type = ingredient_selection.get("formula_type") or ingredient_selection.get("formulaType", "")
        if formula_type:
            sections.append(f"Product Type: {formula_type}")
        
        ingredients = ingredient_selection.get("ingredients", [])
        if ingredients:
            sections.append("\nSelected Ingredients:")
            for idx, ing in enumerate(ingredients, 1):
                if isinstance(ing, dict):
                    name = ing.get("name") or ing.get("ingredient", "")
                    percentage = ing.get("percentage") or ing.get("concentration", "")
                    category = ing.get("category") or ing.get("functional_category", "")
                    if name:
                        ing_text = f"  {idx}. {name}"
                        if percentage:
                            ing_text += f" ({percentage}%)"
                        if category:
                            ing_text += f" - {category}"
                        sections.append(ing_text)
                else:
                    sections.append(f"  {idx}. {ing}")
        sections.append("")
    
    # 3. Optimized Formula
    optimized_formula = wish_data.get("optimized_formula", {})
    if optimized_formula:
        sections.append("=" * 80)
        sections.append("OPTIMIZED FORMULA")
        sections.append("=" * 80)
        
        formula_details = optimized_formula.get("optimized_formula", {})
        if formula_details:
            name = formula_details.get("name", "")
            total_pct = formula_details.get("total_percentage", "")
            cost_per_g = formula_details.get("estimated_cost_per_g", "")
            target_ph = formula_details.get("target_ph", "")
            
            if name:
                sections.append(f"Formula Name: {name}")
            if total_pct:
                sections.append(f"Total Percentage: {total_pct}%")
            if cost_per_g:
                sections.append(f"Estimated Cost per Gram: ₹{cost_per_g:.4f}")
            if target_ph:
                sections.append(f"Target pH: {target_ph}")
        
        # Formula ingredients
        formula_ingredients = optimized_formula.get("ingredients", [])
        if formula_ingredients:
            sections.append("\nFormula Ingredients:")
            for idx, ing in enumerate(formula_ingredients, 1):
                if isinstance(ing, dict):
                    name = ing.get("name") or ing.get("ingredient", "")
                    percentage = ing.get("percentage") or ing.get("concentration", "")
                    phase = ing.get("phase", "")
                    if name:
                        ing_text = f"  {idx}. {name}"
                        if percentage:
                            ing_text += f" - {percentage}%"
                        if phase:
                            ing_text += f" (Phase: {phase})"
                        sections.append(ing_text)
                else:
                    sections.append(f"  {idx}. {ing}")
        
        # Phases
        phases = optimized_formula.get("phases", [])
        if phases:
            sections.append("\nFormula Phases:")
            for phase in phases:
                if isinstance(phase, dict):
                    phase_name = phase.get("name") or phase.get("phase", "")
                    phase_ingredients = phase.get("ingredients", [])
                    if phase_name:
                        sections.append(f"  {phase_name}:")
                        for ing in phase_ingredients:
                            if isinstance(ing, dict):
                                ing_name = ing.get("name", "")
                                ing_pct = ing.get("percentage", "")
                                if ing_name:
                                    sections.append(f"    - {ing_name}: {ing_pct}%")
                            else:
                                sections.append(f"    - {ing}")
        
        # Insights
        insights = optimized_formula.get("insights", [])
        if insights:
            sections.append("\nFormula Insights:")
            for insight in insights:
                if isinstance(insight, dict):
                    text = insight.get("text") or insight.get("insight", "")
                    if text:
                        sections.append(f"  • {text}")
                else:
                    sections.append(f"  • {insight}")
        
        # Warnings
        warnings = optimized_formula.get("warnings", [])
        if warnings:
            sections.append("\nWarnings:")
            for warning in warnings:
                if isinstance(warning, dict):
                    text = warning.get("text") or warning.get("warning", "")
                    if text:
                        sections.append(f"  ⚠ {text}")
                else:
                    sections.append(f"  ⚠ {warning}")
        
        sections.append("")
    
    # 4. Manufacturing Process
    manufacturing = wish_data.get("manufacturing", {})
    if manufacturing:
        sections.append("=" * 80)
        sections.append("MANUFACTURING PROCESS")
        sections.append("=" * 80)
        
        if isinstance(manufacturing, dict):
            process = manufacturing.get("process") or manufacturing.get("steps", [])
            if process:
                if isinstance(process, list):
                    sections.append("Manufacturing Steps:")
                    for idx, step in enumerate(process, 1):
                        if isinstance(step, dict):
                            step_text = step.get("step") or step.get("description", "")
                            if step_text:
                                sections.append(f"  {idx}. {step_text}")
                        else:
                            sections.append(f"  {idx}. {step}")
                else:
                    sections.append(str(process))
            
            temperature = manufacturing.get("temperature", "")
            mixing_time = manufacturing.get("mixing_time", "")
            if temperature:
                sections.append(f"Temperature: {temperature}")
            if mixing_time:
                sections.append(f"Mixing Time: {mixing_time}")
        else:
            sections.append(str(manufacturing))
        sections.append("")
    
    # 5. Cost Analysis
    cost_analysis = wish_data.get("cost_analysis", {})
    if cost_analysis:
        sections.append("=" * 80)
        sections.append("COST ANALYSIS")
        sections.append("=" * 80)
        
        if isinstance(cost_analysis, dict):
            total_cost = cost_analysis.get("total_cost") or cost_analysis.get("totalCost", "")
            cost_per_g = cost_analysis.get("cost_per_g") or cost_analysis.get("costPerGram", "")
            cost_per_100g = cost_analysis.get("cost_per_100g") or cost_analysis.get("costPer100g", "")
            packaging_cost = cost_analysis.get("packaging_cost") or cost_analysis.get("packagingCost", "")
            
            if cost_per_100g:
                sections.append(f"Cost per 100g: ₹{cost_per_100g:.2f}")
            if cost_per_g:
                sections.append(f"Cost per gram: ₹{cost_per_g:.4f}")
            if packaging_cost:
                sections.append(f"Packaging Cost: ₹{packaging_cost:.2f}")
            if total_cost:
                sections.append(f"Total Cost: ₹{total_cost:.2f}")
            
            # Cost breakdown
            cost_breakdown = cost_analysis.get("cost_breakdown", {})
            if cost_breakdown:
                sections.append("\nCost Breakdown:")
                for key, value in cost_breakdown.items():
                    if value:
                        sections.append(f"  {key.replace('_', ' ').title()}: ₹{value:.2f}")
        else:
            sections.append(str(cost_analysis))
        sections.append("")
    
    # 6. Compliance
    compliance = wish_data.get("compliance", {})
    if compliance:
        sections.append("=" * 80)
        sections.append("COMPLIANCE & REGULATIONS")
        sections.append("=" * 80)
        
        if isinstance(compliance, dict):
            for key, value in compliance.items():
                if value and key not in ["_id"]:
                    sections.append(f"{key.replace('_', ' ').title()}: {value}")
        else:
            sections.append(str(compliance))
        sections.append("")
    
    # Join all sections
    formatted_text = "\n".join(sections)
    
    # If we have very little content, try to format the entire dict as JSON
    if len(formatted_text.strip()) < 100 and wish_data:
        formatted_text = json.dumps(wish_data, indent=2, default=str)
    
    return formatted_text


class GeneratePPTRequest(BaseModel):
    """Request schema for PPT generation - only accepts history_id"""
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
        
        # Fetch from database
        history_doc = await wish_history_col.find_one({
            "_id": ObjectId(history_id),
            "user_id": user_id_value
        })
        
        if not history_doc:
            raise HTTPException(
                status_code=404,
                detail=f"History item not found or doesn't belong to user"
            )
        
        # Extract wish response data from history - supports all formats
        if "formula_data" in history_doc:
            formula_data = history_doc.get("formula_data") or {}
            if not isinstance(formula_data, dict):
                formula_data = {}
            
            if "formula" in formula_data or "insights" in formula_data:
                wish_response_data = {
                    "wish_data": history_doc.get("wish_data") or history_doc.get("parsed_data") or {},
                    "formula": formula_data.get("formula", {}) if isinstance(formula_data, dict) else {},
                    "insights": formula_data.get("insights", {}) if isinstance(formula_data, dict) else {},
                    "manufacturing": formula_data.get("manufacturing", {}) if isinstance(formula_data, dict) else {},
                    "cost_analysis": formula_data.get("cost_analysis", {}) if isinstance(formula_data, dict) else {},
                    "compliance": formula_data.get("compliance", {}) if isinstance(formula_data, dict) else {}
                }
            else:
                wish_response_data = {
                    "wish_data": history_doc.get("wish_data") or history_doc.get("parsed_data") or {},
                    "ingredient_selection": formula_data.get("ingredient_selection", {}) if isinstance(formula_data, dict) else {},
                    "optimized_formula": formula_data.get("optimized_formula", {}) if isinstance(formula_data, dict) else {},
                    "manufacturing": formula_data.get("manufacturing", {}) if isinstance(formula_data, dict) else {},
                    "cost_analysis": formula_data.get("cost_analysis", {}) if isinstance(formula_data, dict) else {},
                    "compliance": formula_data.get("compliance", {}) if isinstance(formula_data, dict) else {}
                }
            if "parsed_data" in history_doc:
                wish_response_data["parsed_data"] = history_doc.get("parsed_data")
        elif "formula_result" in history_doc:
            formula_result = history_doc.get("formula_result", {})
            if not isinstance(formula_result, dict):
                formula_result = {}
            
            wish_response_data = {
                "wish_data": history_doc.get("wish_data") or {},
                "formula_result": formula_result,
                "optimized_formula": {
                    "optimized_formula": {
                        "name": formula_result.get("name", ""),
                        "total_percentage": 100.0,
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
            basic_result = history_doc.get("basic_mode_result") or {}
            if not isinstance(basic_result, dict):
                basic_result = {}
            
            formula_data = basic_result.get("formula", {})
            technical_formula = formula_data.get("technicalFormula", {}) if isinstance(formula_data, dict) else {}
            business_numbers = basic_result.get("businessNumbers", {}) if isinstance(basic_result, dict) else {}
            
            wish_response_data = {
                "wish_data": history_doc.get("wish_data") or history_doc.get("parsed_data") or {},
                "basic_mode_result": basic_result,
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
            if "parsed_data" in history_doc:
                wish_response_data["parsed_data"] = history_doc.get("parsed_data")
        else:
            if "parsed_data" in history_doc or "wish_data" in history_doc:
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
            else:
                raise HTTPException(
                    status_code=400,
                    detail="History item does not contain formula data or wish data. Please generate a formula first."
                )
        
        # Format wish data for Gamma
        formatted_wish_data = format_wish_data_for_gamma(wish_response_data)
        
        # Generate business strategy prompt with Claude
        business_strategy_prompt = await generate_business_strategy_prompt(
            data_text=formatted_wish_data,
            data_type="cosmetic_formulation",
            custom_instructions=None
        )
        
        # Generate PPT using Gamma API
        result = await generate_ppt_from_data(
            data_text=formatted_wish_data,
            prompt=business_strategy_prompt,
            tone="professional, strategic, business-focused, investor-ready",
            audience="business executives, investors, stakeholders, strategic planners, C-level executives",
            num_slides=15,
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
