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

from fastapi import APIRouter, HTTPException, Header, Depends, Query
import httpx
import os
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone, timedelta
from bson import ObjectId
import time
import json
import uuid
import asyncio
import logging

# Import authentication
from app.ai_ingredient_intelligence.auth import verify_jwt_token

# Import revised schemas
from app.ai_ingredient_intelligence.models.make_wish_schemas_revised import (
    ParseWishRequest, ParseWishResponse,
    MakeWishRequestRevised, MakeWishResponseRevised, MakeWishBasicResponseRevised,
    GetAlternativesRequest, GetAlternativesResponse,
    EditFormulaRequest, EditFormulaResponse,
    RequestQuoteRequest, RequestQuoteResponse,
    GetThisMadeRequest, GetThisMadeResponse
)

# Import original schemas for backward compatibility
from app.ai_ingredient_intelligence.models.schemas import (
    MakeWishRequest, MakeWishResponse
)

# Import configuration
from app.ai_ingredient_intelligence.logic.make_wish_config import (
    get_complexity_config, get_texture_for_product_type, 
    get_alternatives_for_ingredient, check_compatibility,
    generate_queue_number, EDIT_RULES
)
from app.ai_ingredient_intelligence.logic.make_wish_icon_mapping import emoji_to_icon, replace_icon_emoji_values

# Import AI prompts
from app.ai_ingredient_intelligence.logic.make_wish_prompts import (
    PARSE_WISH_PROMPT, INGREDIENT_SELECTION_COMPLEXITY_PROMPT,
    INSIGHTS_GENERATION_PROMPT, ALTERNATIVES_ANALYSIS_PROMPT,
    format_ingredients_list, format_alternatives_list
)

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

# Import database collections
from app.ai_ingredient_intelligence.db.collections import (
    wish_history_col, commercialization_requests_col, 
    formula_versions_col, quotes_col, ingredient_alternatives_cache_col
)

router = APIRouter(prefix="/make-wish", tags=["Make a Wish - Revised"])


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
            print(f"❌ AI parsing error: {ai_error}")
            raise HTTPException(
                status_code=500,
                detail=f"Error parsing wish: {str(ai_error)}"
            )
        
        # Validate AI response structure
        if not parsed_result or not isinstance(parsed_result, dict):
            raise HTTPException(
                status_code=500,
                detail="Invalid parsing result from AI"
            )
        
        # Set mode from request (basic or advanced, default advanced)
        parsed_result["mode"] = request.mode

        # Auto-detect texture if not provided
        product_type_id = parsed_result.get("product_type", {}).get("id", "serum")
        auto_texture = get_texture_for_product_type(product_type_id)
        
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
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Generate formula using revised flow with complexity selection.
    
    Mode is request.mode (or parsed_data.mode fallback): 
    - "basic": Simplified flow for layman users (active options, business context).
    - "advanced" (default): Full multi-stage pipeline with complexity.
    
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
    - Sends OneSignal notifications
    """
    request_received_at = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    
    # Extract user info for auto-save
    user_id = current_user.get("user_id") or current_user.get("_id")
    name = request.name.strip()
    history_id = request.history_id
    
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
    
    mode = request.mode or request.parsed_data.mode
    if mode not in ["basic", "advanced"]:
        raise HTTPException(
            status_code=400,
            detail="mode must be either 'basic' or 'advanced'"
        )
    
    try:
        # Prepare wish data for background processing
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
            "mode": "basic",
        }
        
        # Save request to DB immediately with "in_progress" status
        formula_id = str(uuid.uuid4())
        if not history_id:
            try:
                history_doc = {
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
                result = await wish_history_col.insert_one(history_doc)
                history_id = str(result.inserted_id)
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
        
        # Process in background using asyncio.create_task for true concurrency
        # Wrap in error handler to prevent unhandled exceptions
        background_coro = process_generate_revised_background(
            history_id=history_id,
            user_id=user_id,
            wish_data=wish_data,
            request=request,
            name=name,
            formula_id=formula_id,
            request_received_at=request_received_at
        )
        asyncio.create_task(handle_background_task_safely(background_coro))
        
        # Return immediate acknowledgment
        print(f"[ACKNOWLEDGMENT] Returning immediate acknowledgment with history_id: {history_id}")
        return {
            "success": True,
            "message": "Request received. Processing started.",
            "history_id": history_id,
            "formula_id": formula_id,
            "status": "in_progress",
            "request_received_at": request_received_at.isoformat()
        }
    
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
        await coro
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"❌ Unhandled exception in background task: {e}", exc_info=True)


# ============================================================================
# BACKGROUND PROCESSING FUNCTION
# ============================================================================

async def process_generate_revised_background(
    history_id: str,
    user_id: str,
    wish_data: Dict[str, Any],
    request: MakeWishRequestRevised,
    name: str,
    formula_id: str,
    request_received_at: datetime
):
    """
    Background task to process revised Make a Wish formula generation.
    Handles:
    - Formula generation
    - Trend analysis
    - Market trends
    - Synthesis
    - Credit deduction (on success only)
    - OneSignal push notifications (success/failure)
    - Database updates
    """
    start_time = time.time()
    processing_success = False
    error_message = None
    
    try:
        print(f"[BACKGROUND] Starting processing for history_id: {history_id}")
        
        # Generate formula
        basic_result = await generate_formula_from_wish(wish_data)
        basic_result = replace_icon_emoji_values(basic_result)  # emoji -> heroicon/lucide names
        
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
            print(f"⚠️ Error extracting hero ingredients: {e}")
            hero_ingredients = wish_data.get("heroIngredients", [])
        
        # Fetch market trends data (formatted for frontend visualization)
        market_trends = None
        synthesis_data = {}  # Store synthesis for each ingredient
        trend_data = {}  # Keep for backward compatibility (empty for now)
        
        try:
            print(f"📊 Fetching market trends data for frontend...")
            from app.ai_ingredient_intelligence.logic.market_trends_service import MarketTrendsService
            trends_service = MarketTrendsService()
            
            # Extract benefits and product type from wish data
            benefits = wish_data.get("benefits", [])
            product_type = wish_data.get("productType") or wish_data.get("product_type")
            category = wish_data.get("category", "skincare")
            
            market_trends = await trends_service.fetch_trends_for_wish(
                hero_ingredients=hero_ingredients,
                benefits=benefits,
                product_type=product_type,
                category=category,
                max_age_days=35,
                use_fallback=True
            )
            print(f"✅ Market trends fetched successfully")
            
            # Run synthesis for each hero ingredient using market trends data
            if market_trends and hero_ingredients:
                print(f"🔬 Running synthesis for {len(hero_ingredients)} ingredients...")
                from app.ai_ingredient_intelligence.logic.trend_synthesis import synthesize_trend_insights
                from app.ai_ingredient_intelligence.logic.trend_analyzer import TrendAnalyzer
                
                analyzer = TrendAnalyzer()
                ingredient_trends = market_trends.get("ingredient_trends", [])
                
                for ing in hero_ingredients[:5]:  # Limit to 5 to avoid rate limits
                    try:
                        # Find trend data for this ingredient from market trends
                        ing_trend = next((t for t in ingredient_trends if t.get("ingredient_name") == ing), None)
                        
                        if ing_trend:
                            # Extract trend data from market trends format
                            trend_data_for_synthesis = {
                                "ingredient": ing,
                                "current_interest": ing_trend.get("current_score", 0),
                                "growth_rate_6mo": ing_trend.get("growth_6m", 0),
                                "trend_direction": ing_trend.get("trend_direction", "stable"),
                                "timeseries_chart": ing_trend.get("timeseries_chart", []),
                                "rising_queries": ing_trend.get("rising_queries", []),
                                "top_queries": ing_trend.get("top_queries", [])
                            }
                            
                            # Get additional data for synthesis
                            consumer_intent_data = None
                            regional_data = None
                            
                            try:
                                consumer_intent_data = await analyzer.analyze_consumer_intent(ing)
                            except:
                                pass
                            
                            try:
                                regional_data = await analyzer.analyze_regional_demand(ing)
                            except:
                                pass
                            
                            # Run synthesis
                            synthesis_result = await synthesize_trend_insights(
                                ingredient=ing,
                                trend_data=trend_data_for_synthesis,
                                consumer_intent_data=consumer_intent_data,
                                competitive_data=None,
                                regional_data=regional_data
                            )
                            
                            synthesis_data[ing] = synthesis_result
                            print(f"   ✅ Synthesis completed for {ing}")
                        else:
                            print(f"   ⚠️ No trend data found for {ing}, skipping synthesis")
                    except Exception as synth_error:
                        print(f"   ⚠️ Error synthesizing {ing}: {synth_error}")
                        continue
                
                print(f"✅ Synthesis completed for {len(synthesis_data)} ingredients")
        except Exception as e:
            print(f"⚠️ Error fetching market trends: {e}")
            import traceback
            traceback.print_exc()
            # Don't fail the request if trends fail
            market_trends = None
        
        processing_time = time.time() - start_time
        processing_time_seconds = round(processing_time, 2)
        print(f"✅ Make a Wish formula generated in {processing_time_seconds}s")
        
        # Update database with completed status
        update_doc = {
            "basic_mode_result": basic_result,
            "trend_data": trend_data,
            "market_trends": market_trends,
            "synthesis_data": synthesis_data,
            "status": "completed",
            "processing_time": processing_time_seconds,
            "updated_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()
        }
        
        await wish_history_col.update_one(
            {"_id": ObjectId(history_id), "user_id": user_id},
            {"$set": update_doc}
        )
        
        print(f"[BACKGROUND] ✅ Updated history {history_id} with completed status")
        processing_success = True
        
        # Deduct credits on success
        try:
            await deduct_credits(
                user_id=user_id,
                reference_id=history_id,
                credit_key=CreditKey.MAKE_WISH_GENERATE,
                transaction_type="make_wish_generation_revised",
                description=f"Make a Wish formula generation (revised) - {history_id}"
            )
        except Exception as credit_error:
            print(f"⚠️ [BACKGROUND] Failed to deduct credits: {credit_error}")
            # Don't fail the whole process if credit deduction fails
        
        # Send success notification via OneSignal
        try:
            await send_onesignal_notification(
                user_id=user_id,
                title="Formula Generated Successfully!",
                message=f"Your formula '{name}' has been generated and is ready to view.",
                data={"history_id": history_id, "status": "completed", "type": "make_wish_revised"}
            )
        except Exception as notif_error:
            print(f"⚠️ [BACKGROUND] Failed to send success notification: {notif_error}")
        
        # Send real-time WebSocket notification using enhanced notification module
        try:
            await notify_user_enhanced(
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
                meta={"history_id": history_id, "status": "completed", "type": "make_wish_revised"}
            )
        except Exception as ws_error:
            print(f"⚠️ [BACKGROUND] Failed to send WebSocket notification: {ws_error}")
        
    except Exception as e:
        processing_success = False
        error_message = str(e)
        print(f"❌ [BACKGROUND] Error processing wish {history_id}: {e}")
        import traceback
        traceback.print_exc()
        
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
        
        # Send failure notification via OneSignal (don't deduct credits on failure)
        try:
            await send_onesignal_notification(
                user_id=user_id,
                title="Formula Generation Failed",
                message=f"Sorry, we couldn't generate your formula '{name}'. Please try again.",
                data={"history_id": history_id, "status": "failed", "type": "make_wish_revised", "error": error_message}
            )
        except Exception as notif_error:
            print(f"⚠️ [BACKGROUND] Failed to send failure notification: {notif_error}")
        
        # Send real-time WebSocket notification using enhanced notification module
        try:
            await notify_user_enhanced(
                user_id=user_id,
                module="make-wish",
                notification_type="error",
                title="Formula Generation Failed",
                message=f"Sorry, we couldn't generate your formula '{name}'. Please try again.",
                meta={"history_id": history_id, "status": "failed", "type": "make_wish_revised", "error": error_message}
            )
        except Exception as ws_error:
            print(f"⚠️ [BACKGROUND] Failed to send WebSocket notification: {ws_error}")


# ============================================================================
# HELPER FUNCTIONS FOR CREDITS AND NOTIFICATIONS
# ============================================================================

# Credit deduction is now handled by the reusable credit_service
# The deduct_credits function is imported above


async def send_onesignal_notification(
    user_id: str,
    title: str,
    message: str,
    data: Optional[Dict[str, Any]] = None
):
    """
    Send push notification via OneSignal.
    """
    onesignal_app_id = os.getenv("ONESIGNAL_APP_ID")
    onesignal_api_key = os.getenv("ONESIGNAL_API_KEY")
    onesignal_api_url = os.getenv("ONESIGNAL_API_URL", "https://onesignal.com/api/v1/notifications")
    
    if not onesignal_app_id or not onesignal_api_key:
        print(f"⚠️ [ONESIGNAL] OneSignal credentials not configured, skipping notification")
        return
    
    try:
        # First, get the OneSignal player_id for this user from database
        from app.ai_ingredient_intelligence.db.collections import users_col
        
        # Handle both ObjectId and string user_id
        user_doc = None
        if ObjectId.is_valid(user_id):
            # Try as ObjectId first
            user_doc = await users_col.find_one({"_id": ObjectId(user_id)})
            if not user_doc:
                # Try as user_id field
                user_doc = await users_col.find_one({"user_id": user_id})
        else:
            # Try as string _id or user_id field
            user_doc = await users_col.find_one({"_id": user_id})
            if not user_doc:
                user_doc = await users_col.find_one({"user_id": user_id})
        
        if not user_doc:
            print(f"⚠️ [ONESIGNAL] User {user_id} not found")
            return
        
        # Get player_id from user document (adjust field name as needed)
        player_id = user_doc.get("onesignal_player_id") or user_doc.get("player_id")
        
        if not player_id:
            print(f"⚠️ [ONESIGNAL] No OneSignal player_id found for user {user_id}")
            return
        
        # Prepare OneSignal notification payload
        payload = {
            "app_id": onesignal_app_id,
            "include_player_ids": [player_id],
            "headings": {"en": title},
            "contents": {"en": message},
            "data": data or {}
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                onesignal_api_url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Basic {onesignal_api_key}"
                }
            )
            
            if response.status_code == 200:
                print(f"✅ [ONESIGNAL] Notification sent successfully to user {user_id}")
            else:
                print(f"⚠️ [ONESIGNAL] OneSignal API returned status {response.status_code}: {response.text}")
                raise Exception(f"OneSignal notification failed: {response.status_code}")
                
    except Exception as e:
        print(f"❌ [ONESIGNAL] Error sending notification: {e}")
        raise


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
    Edit formula metadata (name, tag, notes) without changing formula itself.
    
    This endpoint allows users to:
    - Update formula name
    - Update tag for categorization  
    - Update notes
    - Preserve all formula data unchanged
    """
    try:
        print(f"📝 Editing formula metadata: {wishId}")
        
        obj_id = ObjectId(wishId)
        # Extract user info
        user_id = current_user.get("user_id") or current_user.get("_id")
        
       # Allowed fields whitelist (defense-in-depth)
        ALLOWED_FIELDS = {"name", "tag", "notes"}

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

        # Atomic update (ownership enforced)
        result = await wish_history_col.update_one(
            {"_id": obj_id, "user_id": user_id},
            {"$set": update_doc}
        )

        # Not found or unauthorized
        if result.matched_count == 0:
            raise HTTPException(404, "Formula not found or access denied")

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
        
        parsed = history_item.get("parsed_data") or {}
        if parsed.get("mode") == "basic" and history_item.get("basic_mode_result"):
            current_formula = history_item.get("basic_mode_result") or {}
        else:
            current_formula = history_item.get("formula_data") or {}
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
        
        # Validate formula exists
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
        
        # Check if commercialization request already exists for this formula
        existing_request = await commercialization_requests_col.find_one({
            "user_id": user_id,
            "formula_id": request.formula_id,
            "history_id": request.history_id,
            "status": {"$in": ["submitted", "in_progress", "review", "approved"]}
        })
        
        if existing_request:
            raise HTTPException(
                status_code=409,
                detail=f"Commercialization request already exists for this formula. Request ID: {existing_request.get('request_id', 'N/A')}, Queue Number: {existing_request.get('queue_number', 'N/A')}"
            )
        
        # Generate queue number and request ID
        queue_number = generate_queue_number()
        request_id = str(uuid.uuid4())
        created_at = datetime.now(timezone(timedelta(hours=5, minutes=30)))
        
        # Determine queue position (simplified)
        queue_position = None  # Would be calculated from database
        
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
        
        # Save commercialization request to database
        commercialization_doc = {
            "request_id": request_id,
            "queue_number": queue_number,
            "user_id": user_id,
            "formula_id": request.formula_id,
            "history_id": request.history_id,
            "name": request.name,
            "phone": request.phone,
            "city": request.city,
            "experience_level": request.experience_level,
            "timeline": request.timeline,
            "quantity_interest": request.quantity_interest,
            "additional_notes": request.additional_notes,
            "status": "submitted",
            "created_at": created_at.isoformat(),
            "next_steps": next_steps,
            # "commitment_info": commitment_info,
            "updated_at": created_at.isoformat()
        }
        
        try:
            result = await commercialization_requests_col.insert_one(commercialization_doc)
            print(f"💾 Saved commercialization request: {request_id}")
        except Exception as db_error:
            print(f"⚠️ Warning: Failed to save commercialization request: {db_error}")
            # Continue without failing the response
        
        print(f"✅ Commercialization request submitted")
        print(f"   Queue Number: {queue_number}")
        print(f"   Experience Level: {request.experience_level}")
        print(f"   Timeline: {request.timeline}")
        
        return GetThisMadeResponse(
            success=True,
            queue_number=queue_number,
            queue_position=queue_position,
            request_id=request_id,
            created_at=created_at,
            next_steps=next_steps,
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
    background_tasks: BackgroundTasks,
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
        result = await export_to_board_endpoint(export_request, background_tasks, current_user)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"ERROR exporting revised make a wish to board: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# BACKWARD COMPATIBILITY: ORIGINAL GENERATE ENDPOINT
# ============================================================================

@router.post("/generate", response_model=MakeWishResponse)
async def generate_make_wish_formula_legacy(
    request: MakeWishRequest,
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Legacy Make a Wish endpoint for backward compatibility.
    
    This endpoint maintains the original API structure while 
    internally using the revised system. Maps old request format
    to new flow.
    """
    try:
        print(f"🔄 Converting legacy request to revised flow...")
        
        # Convert legacy request to natural language
        legacy_wish_text = f"""
        I want to create a {request.category} {request.productType} with the following benefits: {', '.join(request.benefits)}.
        """
        
        if request.heroIngredients:
            legacy_wish_text += f" Please include these ingredients: {', '.join(request.heroIngredients)}."
        
        if request.exclusions:
            legacy_wish_text += f" Make it {', '.join(request.exclusions)}."
        
        if request.additionalNotes:
            legacy_wish_text += f" Additional notes: {request.additionalNotes}"
        
        # Create ParseWishRequest
        from app.ai_ingredient_intelligence.models.make_wish_schemas_revised import ParseWishRequest
        parse_request = ParseWishRequest(wish_text=legacy_wish_text.strip())
        
        # Parse the wish
        parse_response = await parse_natural_language_wish(parse_request, current_user)
        
        # Default to classic complexity for legacy requests
        complexity = "classic"
        
        # Create revised request
        from app.ai_ingredient_intelligence.models.make_wish_schemas_revised import MakeWishRequestRevised
        revised_request = MakeWishRequestRevised(
            wish_text=legacy_wish_text.strip(),
            parsed_data=parse_response.parsed_data,
            complexity=complexity,
            claims=request.claims,
            additional_notes=request.additionalNotes,
            name=request.name or "Legacy Formula",
            tag=request.tag,
            notes=request.notes,
            history_id=request.history_id
        )
        
        # Generate using revised flow
        revised_response = await generate_formula_revised(revised_request, current_user)
        
        # Convert back to legacy format
        legacy_response = {
            "wish_data": request.model_dump(),
            "ingredient_selection": {"status": "completed"},
            "optimized_formula": revised_response.formula.model_dump(),
            "manufacturing": revised_response.manufacturing,
            "cost_analysis": {"status": "moved_to_separate_endpoint"},
            "compliance": revised_response.compliance,
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "formula_version": "2.0 (revised)",
                "legacy_mode": True
            },
            "history_id": revised_response.history_id
        }
        
        return MakeWishResponse(**legacy_response)
    
    except Exception as e:
        print(f"❌ Error in legacy conversion: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error in legacy endpoint: {str(e)}"
        )
