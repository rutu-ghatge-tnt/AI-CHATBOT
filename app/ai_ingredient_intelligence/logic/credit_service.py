"""
Credit Deduction Service
========================

Reusable service for deducting credits across all features.
Uses an enum for credit keys to ensure consistency and easy extension.
"""

import os
from enum import Enum
from typing import Optional
import httpx


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
    description: Optional[str] = None
) -> bool:
    """
    Deduct credits for a user operation.
    
    Args:
        user_id: User ID who performed the operation
        reference_id: Reference ID (e.g., history_id, request_id) for tracking
        credit_key: Credit key from CreditKey enum (determines amount to deduct)
        transaction_type: Optional transaction type for logging (defaults to credit_key)
        description: Optional description for the transaction
    
    Returns:
        True if credits were successfully deducted, False otherwise
    
    Raises:
        Exception: If credit deduction API call fails
    """
    # Get API configuration from environment
    api_prefix = os.getenv("API_PREFIX", "/api")
    base_url = os.getenv("BASE_URL", "http://localhost:8000")
    
    # Construct credit deduction endpoint
    credit_api_url = f"{base_url}{api_prefix}/credits/deduct"
    
    # Use enum value as the key
    key = credit_key.value
    
    # Default transaction type and description if not provided
    if not transaction_type:
        transaction_type = key.replace("-", "_")
    if not description:
        description = f"Credit deduction for {key} - {reference_id}"
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "key": key,
                "user_id": user_id,
                "reference_id": reference_id,
                "transaction_type": transaction_type,
                "description": description
            }
            
            response = await client.post(
                credit_api_url,
                json=payload
            )
            
            if response.status_code == 200:
                print(f"✅ [CREDITS] Successfully deducted credits for user {user_id} (key: {key}, reference: {reference_id})")
                return True
            else:
                error_msg = f"Credit deduction API returned status {response.status_code}: {response.text}"
                print(f"⚠️ [CREDITS] {error_msg}")
                raise Exception(error_msg)
                
    except httpx.TimeoutException:
        error_msg = f"Credit deduction API timeout for user {user_id} (key: {key})"
        print(f"❌ [CREDITS] {error_msg}")
        raise Exception(error_msg)
    except Exception as e:
        error_msg = f"Error deducting credits: {str(e)}"
        print(f"❌ [CREDITS] {error_msg}")
        raise Exception(error_msg) from e

