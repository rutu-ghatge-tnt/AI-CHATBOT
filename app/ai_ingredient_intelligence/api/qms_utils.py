"""
QMS Utility Functions
=====================
Helper functions for creating queries, users, and payments
"""

from datetime import datetime, date, timezone, timedelta
from bson import ObjectId
from typing import Dict, Any, Optional

from app.ai_ingredient_intelligence.db.collections import (
    qms_users_col,
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
    user_info: Dict[str, Any],
    payment_id: Optional[str] = None
) -> str:
    """
    Create a QMS query from a commercialization request (payment optional).
    
    This function:
    1. Creates or updates user record
    2. Creates query record (with optional payment link)
    3. Sets initial status to 'new'
    
    Args:
        user_id: User ID from JWT token
        wish_history_id: Make A Wish history ID (to fetch all data from)
        formula_id: Formula ID
        user_info: User information (name, email, phone, city, background, etc.)
        payment_id: Optional payment record ID (for future payment integration)
    
    Returns:
        Query ID (MongoDB ObjectId as string)
    """
    try:
        # Get wish history to extract formula details
        wish_history = await wish_history_col.find_one({
            "_id": ObjectId(wish_history_id),
            "user_id": user_id
        })
        
        if not wish_history:
            raise ValueError(f"Wish history not found: {wish_history_id}")
        
        # Get or create user
        user_obj_id = ObjectId(user_id)
        existing_user = await qms_users_col.find_one({"_id": user_obj_id})
        
        if existing_user:
            # Update user if info provided
            update_data = {}
            if user_info.get("name"):
                update_data["name"] = user_info["name"]
            if user_info.get("email"):
                update_data["email"] = user_info["email"]
            if user_info.get("phone"):
                update_data["phone"] = user_info["phone"]
            if user_info.get("city"):
                update_data["city"] = user_info["city"]
            if user_info.get("background"):
                update_data["background"] = user_info["background"]
            if user_info.get("preferred_batch"):
                update_data["preferred_batch"] = user_info["preferred_batch"]
            
            if update_data:
                update_data["updated_at"] = datetime.now(timezone(timedelta(hours=5, minutes=30)))
                await qms_users_col.update_one(
                    {"_id": user_obj_id},
                    {"$set": update_data}
                )
        else:
            # Create new user
            user_doc = {
                "_id": user_obj_id,
                "name": user_info.get("name", "User"),
                "email": user_info.get("email", ""),
                "phone": user_info.get("phone", ""),
                "city": user_info.get("city"),
                "background": user_info.get("background"),
                "preferred_batch": user_info.get("preferred_batch"),
                "source": "make_a_wish",
                "created_at": datetime.now(timezone(timedelta(hours=5, minutes=30))),
                "updated_at": datetime.now(timezone(timedelta(hours=5, minutes=30)))
            }
            await qms_users_col.insert_one(user_doc)
        
        # Generate display ID (import locally to avoid circular dependency)
        from app.ai_ingredient_intelligence.api.qms_routes import generate_display_id
        display_id = await generate_display_id("QRY")
        
        # Create query - only essential fields (formula_id and history_id, fetch everything else from wish_history)
        now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
        query_doc = {
            "display_id": display_id,
            "user_id": user_id,
            "formula_id": formula_id,
            "history_id": wish_history_id,
            "status": QueryStatus.NEW.value,
            "created_at": now,
            "updated_at": now
        }
        
        result = await qms_queries_col.insert_one(query_doc)
        query_id = str(result.inserted_id)
        
        print(f"✅ Created QMS query: {display_id} (ID: {query_id})")
        print(f"   User: {user_info.get('name', 'Unknown')}")
        print(f"   Formula: {formula_name}")
        print(f"   Status: {QueryStatus.NEW.value}")
        if payment_id:
            print(f"   Payment ID: {payment_id}")
        else:
            print(f"   Payment: Skipped (payment not implemented yet)")
        
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
    user_info: Dict[str, Any]
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
        user_info: User information (name, email, phone, city, background, etc.)
    
    Returns:
        Query ID (MongoDB ObjectId as string)
    """
    return await create_query_from_commercialization(
        user_id=user_id,
        wish_history_id=wish_history_id,
        formula_id=formula_id,
        user_info=user_info,
        payment_id=payment_id
    )


# REMOVED: create_query_from_commercialization_request function
# No longer needed since commercialization_requests collection was removed
# All commercialization requests are now created directly as QMS queries
