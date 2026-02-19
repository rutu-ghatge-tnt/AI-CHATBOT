"""
URL Extraction API Endpoints
============================

This module handles URL extraction endpoints extracted from analyze_inci.py for better modularity.
Endpoints:
- POST /extract-ingredients-from-url - Extract ingredients from URL (no analysis)
- POST /analyze-url - Extract and analyze ingredients from URL

NOTE: Original endpoints in analyze_inci.py remain functional for backward compatibility.
"""

from fastapi import APIRouter, HTTPException, Depends
import time
from typing import List, Optional, Dict
from datetime import datetime, timezone, timedelta
from bson import ObjectId

# Import authentication
from app.ai_ingredient_intelligence.auth import verify_jwt_token

# Import logic modules
from app.ai_ingredient_intelligence.logic.url_fetcher import extract_ingredients_from_url_cached
from app.ai_ingredient_intelligence.logic.matcher import match_inci_names
from app.ai_ingredient_intelligence.logic.bis_rag import get_bis_cautions_for_ingredients
from app.ai_ingredient_intelligence.logic.cas_api import get_synonyms_batch
from app.ai_ingredient_intelligence.logic.category_computer import (
    fetch_and_compute_categories
)
from app.ai_ingredient_intelligence.logic.distributor_fetcher import fetch_distributors_for_branded_ingredients
# Import schemas
from app.ai_ingredient_intelligence.models.schemas import (
    ExtractIngredientsResponse,
    AnalyzeInciResponse,
    AnalyzeInciItem,
    InciGroup
)

# Import database collections
from app.ai_ingredient_intelligence.db.collections import decode_history_col
from app.ai_ingredient_intelligence.db.mongodb import db

router = APIRouter(tags=["URL Extraction"])


@router.post("/extract-ingredients-from-url", response_model=ExtractIngredientsResponse)
async def extract_ingredients_from_url(
    payload: dict,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Extract ingredients from a product URL.
    
    This endpoint ONLY extracts ingredients - it does NOT analyze them.
    After extraction, use the extracted ingredients list with /api/analyze-inci endpoint.
    
    Request body:
    {
        "url": "https://example.com/product/..."
    }
    
    Returns:
    {
        "ingredients": ["Water", "Glycerin", ...],
        "extracted_text": "Full scraped text...",
        "platform": "amazon",
        "url": "https://...",
        "processing_time": 5.123
    }
    """
    print(f"\n{'='*80}")
    print(f"[DEBUG] 🚀 API CALL: /api/extract-ingredients-from-url")
    print(f"[DEBUG] Request received at: {datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()}")
    print(f"[DEBUG] Payload keys: {list(payload.keys())}")
    if "url" in payload:
        print(f"[DEBUG] URL: {payload['url']}")
    print(f"{'='*80}\n")
    
    start = time.time()
    scraper = None
    
    try:
        # Validate payload
        if "url" not in payload:
            print(f"[DEBUG] ❌ Error: Missing required field: url")
            raise HTTPException(status_code=400, detail="Missing required field: url")
        
        url = payload["url"]
        print(f"[DEBUG] Processing URL: {url}")
        if not isinstance(url, str) or not url.strip():
            raise HTTPException(status_code=400, detail="url must be a non-empty string")
        
        # Validate URL format
        if not url.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="Invalid URL format. Must start with http:// or https://")
        
        # Extract ingredients from URL with caching
        print(f"Scraping URL: {url}")
        extraction_result = await extract_ingredients_from_url_cached(url)
        
        ingredients = extraction_result["ingredients"]
        extracted_text = extraction_result["extracted_text"]
        platform = extraction_result.get("platform", "unknown")
        is_estimated = extraction_result.get("is_estimated", False)
        source = extraction_result.get("source", "url_extraction")
        product_name = extraction_result.get("product_name")
        
        if not ingredients:
            # Check if it was an access denied issue
            if "access denied" in extracted_text.lower() or "forbidden" in extracted_text.lower() or "403" in extracted_text.lower():
                raise HTTPException(
                    status_code=403,
                    detail="Access denied by the website. Some e-commerce sites (like Nykaa) block automated requests. Please try: 1) Copy the ingredient list manually and paste it in INCI List mode, or 2) Try a different product URL from Amazon or Flipkart."
                )
            raise HTTPException(
                status_code=404, 
                detail="No ingredients found on the product page. Please ensure the page contains ingredient information."
            )
        
        # Generate appropriate message based on source
        message = None
        if is_estimated and source == "ai_search":
            message = f"Unable to extract ingredients directly from the URL. These are estimated ingredients found via AI search based on the product: {product_name or 'detected product'}. Please verify these ingredients match the actual product formulation."
        
        print(f"Extracted {len(ingredients)} ingredients from {platform} (estimated: {is_estimated})")
        
        # Clean up scraper
        if scraper:
            try:
                await scraper.close()
            except:
                pass
        
        return ExtractIngredientsResponse(
            ingredients=ingredients,
            extracted_text=extracted_text,
            platform=platform,
            url=url,
            processing_time=round(time.time() - start, 3),
            is_estimated=is_estimated,
            source=source,
            product_name=product_name,
            message=message
        )
        
    except HTTPException:
        if scraper:
            try:
                await scraper.close()
            except:
                pass
        raise
    except Exception as e:
        error_msg = str(e)
        error_type = type(e).__name__
        
        # Print full traceback to server console
        print(f"\n{'='*60}")
        print(f"ERROR in extract_ingredients_from_url: {error_type}")
        print(f"Message: {error_msg}")
        print(f"{'='*60}")
        import traceback
        traceback.print_exc()
        print(f"{'='*60}\n")
        
        # Try to close scraper on error
        if scraper:
            try:
                await scraper.close()
            except:
                pass
        
        # Provide more helpful error messages
        if "no meaningful text extracted" in error_msg.lower() or "failed to scrape url" in error_msg.lower():
            raise HTTPException(
                status_code=422,
                detail=f"Unable to extract content from the URL. The page could not be scraped successfully. "
                       f"Possible reasons: 1) The page requires JavaScript that didn't load properly, "
                       f"2) The page is blocking automated access (bot detection), 3) The page structure is different than expected, "
                       f"4) The page content is primarily images/media without text, or 5) Network/timeout issues. "
                       f"Please try a different URL or provide ingredients directly as INCI text."
            )
        elif "chrome" in error_msg.lower() or "webdriver" in error_msg.lower() or "driver" in error_msg.lower():
            raise HTTPException(
                status_code=500, 
                detail=f"Browser automation error: {error_msg}. Please ensure Chrome browser is installed. If Chrome is installed, ChromeDriver will be downloaded automatically on first use."
            )
        elif "claude" in error_msg.lower() or "anthropic" in error_msg.lower():
            raise HTTPException(
                status_code=500,
                detail=f"AI service error: {error_msg}. Please check CLAUDE_API_KEY environment variable."
            )
        elif "timeout" in error_msg.lower():
            raise HTTPException(
                status_code=500,
                detail=f"Request timeout: {error_msg}. The website may be slow or blocking requests. Please try again."
            )
        else:
            # Return full error for debugging
            raise HTTPException(
                status_code=500, 
                detail=f"{error_type}: {error_msg}"
            )


@router.post("/analyze-url", response_model=AnalyzeInciResponse)
async def analyze_url(
    payload: dict,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Extract ingredients from a product URL and analyze them with automatic history saving.
    
    Auto-saving behavior:
    - If name is provided, automatically saves to decode history
    - Saves with "in_progress" status before analysis
    - Updates with "completed" status and analysis_result after analysis
    - Saving errors don't fail the analysis (graceful degradation)
    - If history_id is provided, updates existing history item instead of creating new one
    
    Request body:
    {
        "url": "https://example.com/product/...",
        "name": "Product Name" (optional, for auto-saving),
        "tag": "optional-tag" (optional),
        "notes": "User notes" (optional),
        "expected_benefits": "Expected benefits" (optional),
        "history_id": "existing_history_id" (optional, if frontend already created history item)
    }
    
    Authentication:
    - Requires JWT token in Authorization header
    - User ID is automatically extracted from the JWT token
    
    The endpoint will:
    1. Scrape the URL to extract text content
    2. Use AI to extract ingredient list from the text
    3. Analyze the extracted ingredients
    4. Return the analysis results with extracted text
    """
    print(f"\n{'='*80}")
    print(f"[DEBUG] 🚀 API CALL: /api/analyze-url")
    print(f"[DEBUG] Request received at: {datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()}")
    print(f"[DEBUG] Payload keys: {list(payload.keys())}")
    if "url" in payload:
        print(f"[DEBUG] URL: {payload['url']}")
    print(f"{'='*80}\n")
    
    start = time.time()
    scraper = None
    history_id = None
    
    # Extract user_id from JWT token (already verified by verify_jwt_token)
    user_id_value = current_user.get("user_id") or current_user.get("_id") or payload.get("user_id")
    print(f"[DEBUG] User ID extracted: {user_id_value}")
    name = payload.get("name", "").strip()
    tag = payload.get("tag")
    notes = payload.get("notes", "")
    expected_benefits = payload.get("expected_benefits")
    
    # 🔹 Check if history_id is provided (frontend may have already created a history item)
    provided_history_id = payload.get("history_id")
    if provided_history_id:
        # Validate the provided history_id
        try:
            if ObjectId.is_valid(provided_history_id):
                # Verify the history item exists and belongs to the user
                existing_history = await decode_history_col.find_one({
                    "_id": ObjectId(provided_history_id),
                    "user_id": user_id_value
                })
                if existing_history:
                    history_id = provided_history_id
                    print(f"[AUTO-SAVE] Using existing history_id: {history_id}")
                else:
                    print(f"[AUTO-SAVE] Warning: Provided history_id {provided_history_id} not found or doesn't belong to user, creating new one")
                    provided_history_id = None  # Reset to None so we create a new one
            else:
                print(f"[AUTO-SAVE] Warning: Invalid history_id format: {provided_history_id}, creating new one")
                provided_history_id = None
        except Exception as e:
            print(f"[AUTO-SAVE] Warning: Error validating history_id: {e}, creating new one")
            provided_history_id = None
    
    try:
        # Validate payload
        if "url" not in payload:
            raise HTTPException(status_code=400, detail="Missing required field: url")
        
        url = payload["url"]
        if not isinstance(url, str) or not url.strip():
            raise HTTPException(status_code=400, detail="url must be a non-empty string")
        
        # Validate URL format
        if not url.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="Invalid URL format. Must start with http:// or https://")
        
        # 🔹 Auto-save: Save initial state with "in_progress" status if user_id provided and no existing history_id
        # Name is required for auto-save
        if user_id_value and not history_id:
            try:
                # Name is required
                if not name:
                    raise HTTPException(status_code=400, detail="name is required for auto-save")
                
                # Truncate name if too long
                if len(name) > 100:
                    name = name[:97] + "..."
                
                # 🔹 BUG FIX: Check if a history item with the same input_data (URL) already exists for this user
                # This prevents creating duplicate history items when the same analysis is run multiple times
                existing_history_item = await decode_history_col.find_one({
                    "user_id": user_id_value,
                    "input_type": "url",
                    "input_data": url
                }, sort=[("created_at", -1)])  # Get the most recent one
                
                if existing_history_item:
                    history_id = str(existing_history_item["_id"])
                    print(f"[AUTO-SAVE] Found existing history item with same URL, reusing history_id: {history_id}")
                    # Update the existing item's status to "in_progress" if it was completed/failed
                    if existing_history_item.get("status") in ["completed", "failed"]:
                        await decode_history_col.update_one(
                            {"_id": existing_history_item["_id"]},
                            {"$set": {"status": "in_progress", "name": name}}
                        )
                        print(f"[AUTO-SAVE] Reset existing history item {history_id} status to 'in_progress'")
                else:
                    history_doc = {
                        "user_id": user_id_value,
                        "name": name,
                        "tag": tag,
                        "input_type": "url",
                        "input_data": url,
                        "status": "in_progress",
                        "notes": notes,
                        "expected_benefits": expected_benefits,
                        "created_at": (datetime.now(timezone(timedelta(hours=5, minutes=30)))).isoformat()
                    }
                    result = await decode_history_col.insert_one(history_doc)
                    history_id = str(result.inserted_id)
                    print(f"[AUTO-SAVE] Saved initial state with history_id: {history_id}")
            except Exception as e:
                print(f"[AUTO-SAVE] Warning: Failed to save initial state: {e}")
                # Continue with analysis even if saving fails
        
        # Extract ingredients from URL with caching
        print(f"Scraping URL: {url}")
        extraction_result = await extract_ingredients_from_url_cached(url)
        
        ingredients = extraction_result["ingredients"]
        extracted_text = extraction_result["extracted_text"]
        platform = extraction_result.get("platform", "unknown")
        
        if not ingredients:
            raise HTTPException(
                status_code=404, 
                detail="No ingredients found on the product page. Please ensure the page contains ingredient information."
            )
        
        print(f"Extracted {len(ingredients)} ingredients from {platform}")
        
        # OPTIMIZED: Run CAS synonyms and BIS cautions in parallel (they're independent)
        import asyncio
        print("Retrieving synonyms from CAS API and BIS cautions in parallel...")
        synonyms_task = get_synonyms_batch(ingredients)
        bis_cautions_task = get_bis_cautions_for_ingredients(ingredients)
        
        # Wait for both to complete
        synonyms_map, bis_cautions = await asyncio.gather(synonyms_task, bis_cautions_task, return_exceptions=True)
        
        # Handle exceptions
        if isinstance(synonyms_map, Exception):
            print(f"Warning: Error getting synonyms: {synonyms_map}")
            synonyms_map = {}
        if isinstance(bis_cautions, Exception):
            print(f"Warning: Error getting BIS cautions: {bis_cautions}")
            bis_cautions = {}
        
        print(f"Found synonyms for {len([k for k, v in synonyms_map.items() if v])} ingredients")
        if bis_cautions:
            print(f"[OK] Retrieved BIS cautions for {len(bis_cautions)} ingredients: {list(bis_cautions.keys())}")
        else:
            print("[WARNING] No BIS cautions retrieved - this may indicate an issue with the BIS retriever")
        
        # Match ingredients using new flow
        matched_raw, general_ingredients, ingredient_tags, unable_to_decode = await match_inci_names(ingredients, synonyms_map)
        
        # Convert to objects
        items: List[AnalyzeInciItem] = [AnalyzeInciItem(**m) for m in matched_raw]

        # OPTIMIZED: Run categories and distributors fetching in parallel (they're independent)
        print("Fetching ingredient categories and distributor information in parallel...")
        categories_task = fetch_and_compute_categories(items)
        distributors_task = fetch_distributors_for_branded_ingredients(items)
        
        # Wait for both to complete
        categories_result, distributor_info = await asyncio.gather(
            categories_task, 
            distributors_task, 
            return_exceptions=True
        )
        
        # Handle exceptions
        if isinstance(categories_result, Exception):
            print(f"Warning: Error fetching categories: {categories_result}")
            inci_categories, items_processed = {}, items
        else:
            inci_categories, items_processed = categories_result
        
        if isinstance(distributor_info, Exception):
            print(f"Warning: Error fetching distributors: {distributor_info}")
            distributor_info = {}
        
        print(f"Found categories for {len(inci_categories)} INCI names")
        if distributor_info:
            print(f"Found distributors for {len(distributor_info)} branded ingredients")
        else:
            print("No distributor information found")

        # Group items by exact matched_inci (same INCI names = same group)
        from collections import defaultdict
        from app.ai_ingredient_intelligence.models.schemas import InciGroup
        
        detected_dict = defaultdict(list)
        for item in items_processed:
            # Use sorted tuple as key to group items with exact same INCI names
            key = tuple(sorted(item.matched_inci))
            detected_dict[key].append(item)

        detected: List[InciGroup] = [
            InciGroup(
                inci_list=list(key),
                items=val,
                count=len(val)
            )
            for key, val in detected_dict.items()
        ]
        # Sort by number of INCI: more INCI first (grouped ingredients at top), then individual ingredients below
        # Primary sort: number of INCI (descending - more INCI first)
        # Secondary sort: alphabetically by first INCI name
        detected.sort(key=lambda x: (-len(x.inci_list), x.inci_list[0].lower() if x.inci_list else ""))

        # Filter out water-related BIS cautions
        filtered_bis_cautions = None
        if bis_cautions:
            filtered_bis_cautions = {}
            water_related_keywords = ['water', 'aqua']
            for ingredient, cautions in bis_cautions.items():
                ingredient_lower = ingredient.lower()
                is_water_related = any(water_term in ingredient_lower for water_term in water_related_keywords)
                if not is_water_related:
                    filtered_bis_cautions[ingredient] = cautions

        # Build response
        response = AnalyzeInciResponse(
            detected=detected,
            unable_to_decode=unable_to_decode,
            processing_time=round(time.time() - start, 3),
            bis_cautions=filtered_bis_cautions if filtered_bis_cautions else None,
            categories=inci_categories if inci_categories else None,
            distributor_info=distributor_info if distributor_info else None,
            history_id=history_id if history_id else None,
        )
        
        # 🔹 Auto-save: Update history with "completed" status and analysis_result
        if history_id and user_id_value:
            try:
                # Convert response to dict for storage
                analysis_result_dict = response.model_dump(exclude_none=True) if hasattr(response, "model_dump") else response.dict(exclude_none=True)
                
                update_doc = {
                    "status": "completed",
                    "analysis_result": analysis_result_dict
                }
                
                await decode_history_col.update_one(
                    {"_id": ObjectId(history_id), "user_id": user_id_value},
                    {"$set": update_doc}
                )
                print(f"[AUTO-SAVE] Updated history {history_id} with completed status")
            except Exception as e:
                print(f"[AUTO-SAVE] Warning: Failed to update history: {e}")
                # Don't fail the response if saving fails
        
        return response
        
    except HTTPException:
        # Update history status to "failed" if we have history_id
        if history_id and user_id_value:
            try:
                await decode_history_col.update_one(
                    {"_id": ObjectId(history_id), "user_id": user_id_value},
                    {"$set": {"status": "failed"}}
                )
            except:
                pass
        if scraper:
            try:
                await scraper.close()
            except:
                pass
        raise
    except Exception as e:
        # Update history status to "failed" if we have history_id
        if history_id and user_id_value:
            try:
                await decode_history_col.update_one(
                    {"_id": ObjectId(history_id), "user_id": user_id_value},
                    {"$set": {"status": "failed"}}
                )
            except:
                pass
        print(f"Error in analyze_url: {e}")
        # Try to close browser on error
        if scraper:
            try:
                await scraper.close()
            except:
                pass
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {str(e)}")

