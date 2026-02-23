"""
Credit Deduction Service
========================

Reusable service for deducting credits across all features.
Uses an enum for credit keys to ensure consistency and easy extension.
Third-party API base URL from env; paths are defined here for reuse.
"""

import os
from enum import Enum
from typing import Optional
import httpx

# Third-party credits API paths (base URL from CREDITS_API_BASE_URL in env)
CREDITS_API_PATH_DEDUCT = "/api/v1/credits/deduct"


class CreditKey(str, Enum):
    """
    Enum for credit deduction keys.
    Each feature should have its own key(s) for different operations.
    
    Usage:
        CreditKey.MAKE_WISH_GENERATE.value  # Returns "make-wish-generate"
    """
    # Make a Wish feature
    MAKE_WISH_GENERATE = "make-wish-generate"
    
    # Add more keys here as you integrate credit deduction for other features:
    # MARKET_RESEARCH_BASIC = "market-research-basic"
    # MARKET_RESEARCH_ADVANCED = "market-research-advanced"
    # FORMULATION_DECODE = "formulation-decode"
    # PRODUCT_COMPARISON = "product-comparison"
    # etc.


async def deduct_credits(
    user_id: str,
    reference_id: str,
    credit_key: CreditKey,
    transaction_type: Optional[str] = None,
    description: Optional[str] = None,
    bearer_token: Optional[str] = None
) -> Optional[dict]:
    """
    Deduct credits for a user operation.
    Sends a DeductCreditsRequest body: { "taskKey": "<credit_key>" }.
    The API identifies the user from the JWT in Authorization: Bearer <token>.
    
    Args:
        user_id: User ID (for logging)
        reference_id: Reference ID (e.g., history_id) for logging
        credit_key: Credit key from CreditKey enum → sent as taskKey
        transaction_type: Optional; unused in request body (kept for caller compatibility)
        description: Optional; unused in request body (kept for caller compatibility)
        bearer_token: Optional. If set, sent as Authorization header (e.g. "Bearer <jwt>") for auth.
    
    Returns:
        Dict with keys: deducted (bool), creditsDeducted (int), creditsRemaining (int)
        from the API response data when status is 200.
        Returns None if the credits API endpoint doesn't exist (404).
    
    Raises:
        Exception: If credit deduction API call fails (except 404, which returns None)
    """
    # Get third-party credits API base URL from environment (required)
    base_url = (os.getenv("CREDITS_API_BASE_URL") or "").rstrip("/")
    if not base_url:
        raise Exception(
            "CREDITS_API_BASE_URL environment variable is required. "
            "Please set it to your third-party credits API base URL (e.g. https://api.skintruth.in)."
        )
    credit_api_url = f"{base_url}{CREDITS_API_PATH_DEDUCT}"
    
    # Use enum value as the task key (API expects DeductCreditsRequest with taskKey only)
    task_key = credit_key.value
    
    headers: dict = {}
    if bearer_token and bearer_token.strip():
        headers["Authorization"] = (
            bearer_token
            if bearer_token.strip().lower().startswith("bearer ")
            else f"Bearer {bearer_token.strip()}"
        )
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload: dict = {"taskKey": task_key}
            
            response = await client.post(
                credit_api_url,
                json=payload,
                headers=headers or None
            )
            
            if response.status_code == 200:
                body = response.json()
                data = body.get("data") or {}
                result = {
                    "deducted": data.get("deducted", True),
                    "creditsDeducted": data.get("creditsDeducted", 0),
                    "creditsRemaining": data.get("creditsRemaining", 0),
                }
                print(f"✅ [CREDITS] Successfully deducted credits for user {user_id} (taskKey: {task_key}, reference: {reference_id})")
                return result
            elif response.status_code == 404:
                # Credits API endpoint doesn't exist - log warning but don't fail
                print(f"⚠️ [CREDITS] Credits API endpoint not found (404) - credit deduction skipped")
                return None
            else:
                error_msg = f"Credit deduction API returned status {response.status_code}: {response.text}"
                print(f"⚠️ [CREDITS] {error_msg}")
                raise Exception(error_msg)
                
    except httpx.TimeoutException:
        error_msg = f"Credit deduction API timeout for user {user_id} (taskKey: {task_key})"
        print(f"❌ [CREDITS] {error_msg}")
        raise Exception(error_msg)
    except Exception as e:
        error_msg = f"Error deducting credits: {str(e)}"
        print(f"❌ [CREDITS] {error_msg}")
        raise Exception(error_msg) from e

