"""
QMS Utility Functions
=====================
Helper functions for creating queries, users, and payments
"""

from datetime import datetime, date, timezone, timedelta
from bson import ObjectId
from typing import Dict, Any, Optional

from app.ai_ingredient_intelligence.db.collections import (
    users_col,
    qms_queries_col,
    qms_payments_col,
    wish_history_col,
)
from app.ai_ingredient_intelligence.models.qms_schemas import (
    QueryStatus,
    QueryPriority,
    PaymentStatus,
)


async def create_query_from_commercialization(
    user_id: str,
    wish_history_id: str,
    formula_id: str,
    formula_name: str,
    experience_level: str,
    timeline: str,
    quantity_interest: Optional[str] = None,
    additional_notes: Optional[str] = None,
    payment_id: Optional[str] = None,
    queue_number: Optional[str] = None,
    user_name: Optional[str] = None,  # Store user name from form as fallback
    user_phone: Optional[str] = None,  # Store user phone from form
    user_city: Optional[str] = None,  # Store user city from form
    user_email: Optional[str] = None,  # Store user email from form
    user_pincode: Optional[str] = None  # Store user pincode from form
) -> str:
    """
    Create a QMS query from a commercialization request (payment optional).
    
    This function:
    1. Creates query record with all form fields
    2. Sets initial status to 'new'
    
    Args:
        user_id: User ID from JWT token
        wish_history_id: Make A Wish history ID (wish_id)
        formula_id: Formula ID
        formula_name: Formula name
        experience_level: Experience level
        timeline: Timeline
        quantity_interest: Optional quantity interest
        notes: Optional notes
        payment_id: Optional payment record ID (for future payment integration)
        queue_number: Optional queue number
    
    Returns:
        Query ID (MongoDB ObjectId as string)
    """
    try:
        # Get wish history to validate it exists
        wish_history = await wish_history_col.find_one({
            "_id": ObjectId(wish_history_id),
            "user_id": user_id
        })
        
        if not wish_history:
            raise ValueError(f"Wish history not found: {wish_history_id}")
        
        # Generate display ID (import locally to avoid circular dependency)
        from app.ai_ingredient_intelligence.api.qms_routes import generate_display_id
        display_id = await generate_display_id("QRY")
        
        # Create query with all form fields
        now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
        query_doc = {
            "display_id": display_id,
            "user_id": user_id,
            "formula_id": formula_id,
            "wish_id": wish_history_id,  # Store as wish_id (alias for history_id)
            "formula_name": formula_name,
            "experience_level": experience_level,
            "timeline": timeline,
            "quantity_interest": quantity_interest,
            "additional_notes": additional_notes if isinstance(additional_notes, str) else (", ".join(additional_notes) if isinstance(additional_notes, list) else str(additional_notes) if additional_notes else None),
            "status": QueryStatus.NEW.value,
            "queue_number": int(queue_number) if queue_number else None,  # Store as integer for easy sorting
            # Store payment_id only if provided (MongoDB doesn't store None fields)
            **({"payment_id": payment_id} if payment_id else {}),
            # Store user info from form as fallback (in case users collection doesn't have it)
            "user_name": user_name,  # From get-this-made form
            "user_phone": user_phone,  # From get-this-made form
            "user_city": user_city,  # From get-this-made form
            "user_email": user_email,  # From get-this-made form
            "user_pincode": user_pincode,  # From get-this-made form
            "created_at": now,
            "updated_at": now
        }
        
        result = await qms_queries_col.insert_one(query_doc)
        query_id = str(result.inserted_id)
        
        print(f"✅ Created QMS query: {display_id} (ID: {query_id})")
        print(f"   Formula: {formula_name}")
        print(f"   Experience Level: {experience_level}")
        print(f"   Timeline: {timeline}")
        if queue_number:
            print(f"   Queue Number: {queue_number}")
        print(f"   Status: {QueryStatus.NEW.value}")
        print(f"   Payment ID: {payment_id} (stored: {query_doc.get('payment_id')})")
        
        return query_id
    
    except Exception as e:
        print(f"❌ Error creating query from commercialization: {e}")
        import traceback
        traceback.print_exc()
        raise


async def create_query_from_payment(
    user_id: str,
    payment_id: str,
    wish_history_id: str,
    formula_id: str,
    formula_name: str,
    experience_level: str,
    timeline: str,
    quantity_interest: Optional[str] = None,
    additional_notes: Optional[str] = None
) -> str:
    """
    Create a QMS query from a successful payment.
    
    This is a wrapper around create_query_from_commercialization that requires payment_id.
    Use this when payment is verified.
    
    Args:
        user_id: User ID from JWT token
        payment_id: Payment record ID (required)
        wish_history_id: Make A Wish history ID
        formula_id: Formula ID
        formula_name: Formula name
        experience_level: Experience level
        timeline: Timeline
        quantity_interest: Optional quantity interest
        notes: Optional notes
    
    Returns:
        Query ID (MongoDB ObjectId as string)
    """
    return await create_query_from_commercialization(
        user_id=user_id,
        wish_history_id=wish_history_id,
        formula_id=formula_id,
        formula_name=formula_name,
        experience_level=experience_level,
        timeline=timeline,
        quantity_interest=quantity_interest,
        additional_notes=additional_notes,
        payment_id=payment_id
    )


# REMOVED: create_query_from_commercialization_request function
# No longer needed since commercialization_requests collection was removed
# All commercialization requests are now created directly as QMS queries
