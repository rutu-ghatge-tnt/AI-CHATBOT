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
    wish_brief: Dict[str, Any],
    payment_id: Optional[str] = None
) -> str:
    """
    Create a QMS query from a commercialization request (payment optional).
    
    This function:
    1. Creates or updates user record
    2. Creates query record (with optional payment link)
    3. Sets initial status to 'new' and milestone to 0
    
    Args:
        user_id: User ID from JWT token
        wish_history_id: Make A Wish history ID
        formula_id: Formula ID
        user_info: User information (name, email, phone, city, background, etc.)
        wish_brief: Complete Make A Wish output (formula data)
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
        
        # Extract formula name and details from wish_brief or wish_history
        formula_name = (
            wish_brief.get("formula_name") 
            or wish_brief.get("optimized_formula", {}).get("name") 
            or wish_history.get("formula_name")
            or "Custom Formula"
        )
        product_type = (
            wish_brief.get("product_type") 
            or wish_brief.get("wish_data", {}).get("productType") 
            or wish_history.get("product_type")
            or "Product"
        )
        category = (
            wish_brief.get("category") 
            or wish_brief.get("wish_data", {}).get("category") 
            or wish_history.get("category")
            or "skincare"
        )
        
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
        
        # Get payment date (from payment if exists, otherwise today)
        # MongoDB requires datetime, not date - convert to datetime at start of day in IST
        ist_tz = timezone(timedelta(hours=5, minutes=30))
        payment_date = datetime.now(ist_tz).replace(hour=0, minute=0, second=0, microsecond=0)
        if payment_id:
            payment = await qms_payments_col.find_one({"_id": ObjectId(payment_id)})
            if payment and payment.get("created_at"):
                if isinstance(payment["created_at"], datetime):
                    # Convert to IST and set to start of day
                    if payment["created_at"].tzinfo is None:
                        payment_dt = payment["created_at"].replace(tzinfo=ist_tz)
                    else:
                        payment_dt = payment["created_at"].astimezone(ist_tz)
                    payment_date = payment_dt.replace(hour=0, minute=0, second=0, microsecond=0)
                elif isinstance(payment["created_at"], str):
                    payment_dt = datetime.fromisoformat(payment["created_at"].replace("Z", "+00:00"))
                    payment_dt = payment_dt.astimezone(ist_tz)
                    payment_date = payment_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Generate display ID (import locally to avoid circular dependency)
        from app.ai_ingredient_intelligence.api.qms_routes import generate_display_id
        display_id = await generate_display_id("QRY")
        
        # Create query
        now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
        query_doc = {
            "display_id": display_id,
            "user_id": user_id,
            "partner_id": None,
            "formula_name": formula_name,
            "product_type": product_type,
            "category": category,
            "target_mrp": wish_brief.get("target_mrp"),
            "batch_size": wish_brief.get("batch_size") or user_info.get("preferred_batch"),
            "queue_number": wish_brief.get("queue_number"),  # Store queue number for easy access
            "status": QueryStatus.NEW.value,
            "priority": QueryPriority.NORMAL.value,
            "current_milestone": 0,  # Payment Received (or Request Submitted if no payment)
            "wish_brief": wish_brief,
            "payment_id": payment_id,  # Can be None
            "payment_date": payment_date,
            "assigned_date": None,
            "completed_date": None,
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
    user_info: Dict[str, Any],
    wish_brief: Dict[str, Any]
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
        wish_brief: Complete Make A Wish output (formula data)
    
    Returns:
        Query ID (MongoDB ObjectId as string)
    """
    return await create_query_from_commercialization(
        user_id=user_id,
        wish_history_id=wish_history_id,
        formula_id=formula_id,
        user_info=user_info,
        wish_brief=wish_brief,
        payment_id=payment_id
    )


# REMOVED: create_query_from_commercialization_request function
# No longer needed since commercialization_requests collection was removed
# All commercialization requests are now created directly as QMS queries
