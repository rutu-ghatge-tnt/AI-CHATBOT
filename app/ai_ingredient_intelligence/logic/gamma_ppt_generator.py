"""
Gamma API PPT Generator
=======================

This module handles PowerPoint presentation generation using Gamma API.
It's a generic module that can be used with any data source.

FLOW:
1. Receives formatted data text and prompt
2. Calls Gamma API to generate presentation
3. Returns presentation URLs (download, edit)
"""

import os
import httpx
from typing import Dict, Any, Optional
from fastapi import HTTPException


# Gamma API configuration
GAMMA_API_KEY = os.getenv("GAMMA_API_KEY")
GAMMA_API_BASE_URL = "https://public-api.gamma.app/v1.0"
GAMMA_GENERATE_ENDPOINT = f"{GAMMA_API_BASE_URL}/generations"


async def generate_ppt_from_data(
    data_text: str,
    prompt: str,
    tone: str = "professional, strategic, business-focused, investor-ready",
    audience: str = "business executives, investors, stakeholders, strategic planners, C-level executives",
    num_slides: int = 25,
    export_format: str = "pptx",
    language: str = "en"
) -> Dict[str, Any]:
    """
    Generate PowerPoint presentation from data using Gamma API.
    
    Args:
        data_text: Formatted text containing all data for the presentation
        prompt: Business strategy prompt (from Claude or default)
        tone: Presentation tone
        audience: Target audience
        num_slides: Number of slides to generate
        export_format: Export format (pptx, pdf)
        language: Language code
    
    Returns:
        dict: {
            "success": bool,
            "presentation_id": str,
            "download_url": str,
            "edit_url": str,
            "message": str,
            "gamma_response": dict
        }
    
    Raises:
        HTTPException: If Gamma API key is not set or API call fails
    """
    
    # Check if Gamma API key is configured
    if not GAMMA_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="GAMMA_API_KEY environment variable not set. Please configure it in your .env file."
        )
    
    print(f"[GAMMA] 🚀 Generating PPT presentation...")
    print(f"[GAMMA] Data text length: {len(data_text)} characters")
    print(f"[GAMMA] Prompt length: {len(prompt)} characters")
    print(f"[GAMMA] Number of slides: {num_slides}")
    
    # Gamma API has a 5000 character limit for additionalInstructions
    MAX_PROMPT_LENGTH = 5000
    
    # Include tone and audience in additionalInstructions if provided (as part of the prompt)
    if tone or audience:
        tone_audience_note = ""
        if tone:
            tone_audience_note += f"\n\nTone: {tone}"
        if audience:
            tone_audience_note += f"\n\nTarget Audience: {audience}"
        
        # Add to prompt if there's room
        if len(prompt) + len(tone_audience_note) <= MAX_PROMPT_LENGTH:
            prompt = prompt + tone_audience_note
            print(f"[GAMMA] ✅ Added tone/audience to prompt ({len(prompt)} total chars)")
        else:
            print(f"[GAMMA] ⚠️ Cannot add tone/audience to prompt (would exceed limit)")
    
    if len(prompt) > MAX_PROMPT_LENGTH:
        print(f"[GAMMA] ⚠️ Prompt exceeds {MAX_PROMPT_LENGTH} character limit ({len(prompt)} chars). Truncating...")
        # Try to truncate at a sentence boundary
        truncated = prompt[:MAX_PROMPT_LENGTH]
        # Find the last sentence ending (., !, ?) before the limit
        last_period = truncated.rfind('.')
        last_exclamation = truncated.rfind('!')
        last_question = truncated.rfind('?')
        last_sentence_end = max(last_period, last_exclamation, last_question)
        
        # If we found a sentence boundary within the last 200 chars, use it
        if last_sentence_end > MAX_PROMPT_LENGTH - 200:
            prompt = truncated[:last_sentence_end + 1]
            print(f"[GAMMA] ✅ Truncated at sentence boundary: {len(prompt)} characters")
        else:
            # Otherwise, truncate at word boundary
            last_space = truncated.rfind(' ')
            if last_space > MAX_PROMPT_LENGTH - 100:
                prompt = truncated[:last_space] + "..."
                print(f"[GAMMA] ✅ Truncated at word boundary: {len(prompt)} characters")
            else:
                prompt = truncated + "..."
                print(f"[GAMMA] ✅ Truncated at character limit: {len(prompt)} characters")
    
    # Prepare Gamma API request
    # Note: Gamma API only accepts: inputText, format, exportAs, textMode, numCards, additionalInstructions
    # Removed: tone, audience, amount, language (not supported by Gamma API - included in prompt instead)
    # Removed: imageOptions - not supported by Gamma API
    gamma_request_payload = {
        "inputText": data_text,
        "format": "presentation",
        "exportAs": export_format,
        "textMode": "generate",
        "numCards": num_slides,
        "additionalInstructions": prompt
    }
    
    # Call Gamma API
    async with httpx.AsyncClient(timeout=300.0) as client:
        try:
            response = await client.post(
                GAMMA_GENERATE_ENDPOINT,
                headers={
                    "X-API-KEY": GAMMA_API_KEY,
                    "Content-Type": "application/json"
                },
                json=gamma_request_payload
            )
            
            print(f"[GAMMA] API Response Status: {response.status_code}")
            
            if response.status_code not in [200, 201]:
                error_text = response.text
                try:
                    error_json = response.json()
                    error_text = str(error_json)
                except:
                    pass
                
                print(f"[GAMMA] ❌ API Error: {error_text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Gamma API error: {error_text}"
                )
            
            # Parse response
            try:
                gamma_response = response.json()
            except Exception as e:
                print(f"[GAMMA] ❌ Failed to parse response: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Gamma API returned invalid JSON: {response.text[:200]}"
                )
            
            print(f"[GAMMA] ✅ Presentation generated successfully")
            print(f"[GAMMA] Full response: {gamma_response}")
            
            # Extract presentation details
            generation_id = gamma_response.get("generationId") or gamma_response.get("generation_id") or gamma_response.get("id")
            presentation_id = gamma_response.get("presentation_id") or generation_id or "unknown"
            
            # Try to get URLs from response
            download_url = gamma_response.get("download_url") or gamma_response.get("url") or gamma_response.get("file_path") or gamma_response.get("file")
            edit_url = gamma_response.get("edit_url") or gamma_response.get("edit_path") or gamma_response.get("editUrl")
            
            # If we have generationId but no URLs, poll the status endpoint with retries
            if generation_id and not download_url:
                print(f"[GAMMA] 🔍 Generation ID found: {generation_id}, but no URLs. Polling status endpoint...")
                
                # Poll status endpoint with retries (Gamma may need time to process)
                # Gamma presentations can take 1-5 minutes depending on complexity
                import asyncio
                max_retries = 40  # Increased to 40 attempts (2 minutes total)
                retry_delay = 3  # seconds
                
                for attempt in range(max_retries):
                    try:
                        status_url = f"{GAMMA_API_BASE_URL}/generations/{generation_id}"
                        print(f"[GAMMA] Polling attempt {attempt + 1}/{max_retries}: {status_url}")
                        
                        status_response = await client.get(
                            status_url,
                            headers={
                                "X-API-KEY": GAMMA_API_KEY,
                                "Content-Type": "application/json"
                            },
                            timeout=30.0
                        )
                        
                        print(f"[GAMMA] Status response code: {status_response.status_code}")
                        
                        if status_response.status_code == 200:
                            status_data = status_response.json()
                            print(f"[GAMMA] Status response data: {status_data}")
                            
                            # Extract URLs from status response - try various field names
                            download_url = (
                                status_data.get("download_url") or 
                                status_data.get("url") or 
                                status_data.get("file_path") or 
                                status_data.get("file") or
                                status_data.get("presentation_url") or
                                status_data.get("downloadUrl")
                            )
                            
                            edit_url = (
                                status_data.get("edit_url") or 
                                status_data.get("edit_path") or 
                                status_data.get("editUrl") or
                                status_data.get("presentation_edit_url")
                            )
                            
                            presentation_id = (
                                status_data.get("presentation_id") or 
                                status_data.get("id") or 
                                status_data.get("presentationId") or
                                presentation_id
                            )
                            
                            # Check status per Gamma API docs: "pending" or "completed"
                            status = status_data.get("status")
                            
                            if status == "completed":
                                # When status is "completed", Gamma returns the presentation data
                                # Per Gamma API docs, the response includes:
                                # - exportUrl: Direct download URL for PPTX/PDF
                                # - gammaUrl: URL to view/edit the presentation
                                # - gammaId: The presentation ID
                                
                                # Extract exportUrl (download URL) - this is the direct download link
                                download_url = (
                                    status_data.get("exportUrl") or  # Primary field per Gamma API
                                    status_data.get("downloadUrl") or
                                    status_data.get("url") or
                                    status_data.get("presentationUrl") or
                                    status_data.get("file") or
                                    download_url
                                )
                                
                                # Extract gammaUrl (view/edit URL) - this is the presentation URL
                                edit_url = (
                                    status_data.get("gammaUrl") or  # Primary field per Gamma API
                                    status_data.get("editUrl") or
                                    status_data.get("editPath") or
                                    status_data.get("presentationUrl") or
                                    status_data.get("url") or
                                    edit_url
                                )
                                
                                # Update presentation_id - use gammaId from response
                                presentation_id = (
                                    status_data.get("gammaId") or  # Primary field per Gamma API
                                    status_data.get("id") or
                                    status_data.get("presentationId") or
                                    presentation_id
                                )
                                
                                # Log what we found
                                print(f"[GAMMA] ✅ Status: completed")
                                print(f"[GAMMA]   Response keys: {list(status_data.keys())}")
                                print(f"[GAMMA]   download_url: {download_url}")
                                print(f"[GAMMA]   edit_url: {edit_url}")
                                print(f"[GAMMA]   presentation_id: {presentation_id}")
                                
                                # If we have URLs or presentation data, we're done
                                if download_url or edit_url or status_data.get("id"):
                                    break
                                else:
                                    # Status is completed but no URLs - might need to check nested structure
                                    print(f"[GAMMA] ⚠️ Status completed but no URLs found. Checking nested data...")
                                    # Sometimes the presentation data is nested
                                    for key in ["data", "presentation", "result", "gamma"]:
                                        if key in status_data and isinstance(status_data[key], dict):
                                            nested = status_data[key]
                                            download_url = download_url or nested.get("url") or nested.get("downloadUrl")
                                            edit_url = edit_url or nested.get("editUrl") or nested.get("editPath")
                                            if download_url or edit_url:
                                                print(f"[GAMMA] ✅ Found URLs in nested '{key}' object")
                                                break
                                    
                                    if download_url or edit_url:
                                        break
                                    
                            elif status == "pending":
                                print(f"[GAMMA] ⏳ Status: pending - Generation in progress, waiting {retry_delay}s...")
                                if attempt < max_retries - 1:
                                    await asyncio.sleep(retry_delay)
                                continue
                            else:
                                # Unknown status or error
                                print(f"[GAMMA] ⚠️ Unknown status: {status}")
                                if status and "fail" in status.lower() or status and "error" in status.lower():
                                    print(f"[GAMMA] ❌ Generation failed")
                                    break
                                if attempt < max_retries - 1:
                                    await asyncio.sleep(retry_delay)
                        elif status_response.status_code == 404:
                            print(f"[GAMMA] ⚠️ Generation not found yet (404), waiting {retry_delay}s...")
                            if attempt < max_retries - 1:
                                await asyncio.sleep(retry_delay)
                        else:
                            print(f"[GAMMA] ⚠️ Status endpoint returned {status_response.status_code}: {status_response.text[:200]}")
                            if attempt < max_retries - 1:
                                await asyncio.sleep(retry_delay)
                                
                    except Exception as e:
                        print(f"[GAMMA] ⚠️ Error polling status (attempt {attempt + 1}): {e}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay)
            
            # If still no URLs after polling, provide helpful message
            if not download_url and not edit_url:
                print(f"[GAMMA] ⚠️ Warning: Could not retrieve URLs after polling (status still 'pending'). Generation ID: {generation_id}")
                print(f"[GAMMA] 💡 The presentation is still being generated (can take 1-5 minutes). You can:")
                print(f"[GAMMA]    1. Wait a few minutes and check status manually:")
                print(f"[GAMMA]       GET {GAMMA_API_BASE_URL}/generations/{generation_id}")
                print(f"[GAMMA]       Header: X-API-KEY: <your-api-key>")
                print(f"[GAMMA]    2. Check your Gamma dashboard at https://gamma.app")
                print(f"[GAMMA]    3. Once status is 'completed', the response will contain the presentation URLs")
            
            return {
                "success": True,
                "presentation_id": presentation_id,
                "download_url": download_url,
                "edit_url": edit_url,
                "generation_id": generation_id,
                "message": (
                    "Presentation generation initiated successfully. " +
                    ("Use the URLs above to access your presentation." if (download_url or edit_url) else 
                     f"Use generationId '{generation_id}' to check status via Gamma API: GET {GAMMA_API_BASE_URL}/generations/{generation_id}")
                ),
                "gamma_response": gamma_response
            }
            
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=504,
                detail="Gamma API request timed out. Please try again."
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error connecting to Gamma API: {str(e)}"
            )
        except HTTPException:
            raise
        except Exception as e:
            print(f"[GAMMA] ❌ Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail=f"Unexpected error generating presentation: {str(e)}"
            )


def is_gamma_available() -> bool:
    """
    Check if Gamma API is available (API key is set).
    
    Returns:
        bool: True if Gamma API key is configured
    """
    return GAMMA_API_KEY is not None and GAMMA_API_KEY != ""

