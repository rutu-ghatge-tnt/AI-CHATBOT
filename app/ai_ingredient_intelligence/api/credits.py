"""
Credits API Endpoint
====================

Global credit deduction service for all features.
This endpoint handles credit deduction for various operations across the platform.

ENDPOINTS:
- POST /api/credits/deduct - Deduct credits for a user operation
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any
from pydantic import BaseModel, Field

# Import authentication
from app.ai_ingredient_intelligence.auth import verify_jwt_token

# Import credit service
from app.ai_ingredient_intelligence.logic.credit_service import CreditKey

router = APIRouter(prefix="/credits", tags=["Credits"])


class DeductCreditsRequest(BaseModel):
    """Request schema for credit deduction"""
    taskKey: str = Field(..., description="Credit key identifying the operation (e.g., 'make-wish-generate')")


class DeductCreditsResponse(BaseModel):
    """Response schema for credit deduction"""
    success: bool = Field(..., description="Whether the operation was successful")
    data: Dict[str, Any] = Field(..., description="Credit deduction result")
    message: str = Field(..., description="Response message")


@router.post("/deduct", response_model=DeductCreditsResponse)
async def deduct_credits(
    request: DeductCreditsRequest,
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Deduct credits for a user operation.
    
    This is a global service that handles credit deduction for all features.
    The taskKey identifies which operation is being performed.
    
    REQUEST BODY:
    {
        "taskKey": "make-wish-generate"  // or other credit keys
    }
    
    RESPONSE:
    {
        "success": true,
        "data": {
            "deducted": true,
            "creditsDeducted": 10,
            "creditsRemaining": 90
        },
        "message": "Credits deducted successfully"
    }
    
    CREDIT KEYS:
    - "make-wish-generate": Make a Wish formula generation
    - More keys can be added as features are integrated
    """
    try:
        # Extract user ID from JWT token
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(
                status_code=400,
                detail="User ID not found in token"
            )
        
        # Validate taskKey
        task_key = request.taskKey
        
        # For now, implement basic credit deduction logic
        # TODO: Integrate with actual credits database/collection
        # This is a placeholder implementation
        
        # Check if taskKey is valid (exists in CreditKey enum)
        valid_keys = [key.value for key in CreditKey]
        if task_key not in valid_keys:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid taskKey: {task_key}. Valid keys: {', '.join(valid_keys)}"
            )
        
        # TODO: Implement actual credit deduction logic here
        # This should:
        # 1. Check user's current credits
        # 2. Determine credit cost for the taskKey
        # 3. Deduct credits if sufficient
        # 4. Update user's credit balance
        # 5. Log the transaction
        
        # Placeholder response - replace with actual implementation
        credits_deducted = 10  # Default credit cost
        credits_remaining = 100  # Placeholder - should come from database
        
        return DeductCreditsResponse(
            success=True,
            data={
                "deducted": True,
                "creditsDeducted": credits_deducted,
                "creditsRemaining": credits_remaining
            },
            message="Credits deducted successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ [CREDITS API] Error deducting credits: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

