"""
Query Management System (QMS) - API Routes
===========================================
API endpoints for managing queries, partners, notes, and admin operations
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, List
from datetime import datetime, date, timezone, timedelta
from bson import ObjectId
from bson.errors import InvalidId

from app.ai_ingredient_intelligence.models.qms_schemas import (
    QueryListResponse,
    QueryDetailResponse,
    QueryStatusUpdateRequest,
    QueryListPaginatedResponse,
    QueryStatsResponse,
    NoteCreate,
    NoteResponse,
    PartnerCreate,
    PartnerResponse,
    PartnerListResponse,
    QueryStatus,
    PartnerStatus,
    NoteRole,
    PaymentStatus,
    RefundRequest,
    UserInfo,
)
from app.ai_ingredient_intelligence.db.collections import (
    users_col,
    qms_partners_col,
    qms_queries_col,
    qms_query_notes_col,
    qms_payments_col,
    qms_audit_log_col,
)
from app.ai_ingredient_intelligence.auth import verify_jwt_token
import math

router = APIRouter(prefix="/qms", tags=["QMS - Query Management System"])

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def generate_display_id(prefix: str, year: int = None) -> str:
    """Generate human-readable display ID (e.g., QRY-2025-001, P001)"""
    if year is None:
        year = datetime.now().year
    
    if prefix == "QRY":
        # Get the last query number for this year
        last_query = await qms_queries_col.find_one(
            {"display_id": {"$regex": f"^{prefix}-{year}-"}},
            sort=[("display_id", -1)]
        )
        if last_query:
            last_num = int(last_query["display_id"].split("-")[-1])
            new_num = last_num + 1
        else:
            new_num = 1
        return f"{prefix}-{year}-{str(new_num).zfill(3)}"
    elif prefix.startswith("P"):
        # Get the last partner number
        last_partner = await qms_partners_col.find_one(
            {"display_id": {"$regex": f"^{prefix}"}},
            sort=[("display_id", -1)]
        )
        if last_partner:
            last_num = int(last_partner["display_id"][1:])
            new_num = last_num + 1
        else:
            new_num = 1
        return f"{prefix}{str(new_num).zfill(3)}"
    return f"{prefix}-{new_num}"


async def log_audit(
    actor_id: str,
    actor_role: str,
    action: str,
    resource_type: str,
    resource_id: str,
    details: dict = None,
    ip_address: str = None
):
    """Log an action to audit log"""
    audit_entry = {
        "actor_id": actor_id,
        "actor_role": actor_role,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "details": details or {},
        "ip_address": ip_address,
        "created_at": datetime.now(timezone(timedelta(hours=5, minutes=30)))
    }
    await qms_audit_log_col.insert_one(audit_entry)


def validate_object_id(id_str: str) -> ObjectId:
    """Validate and convert string to ObjectId"""
    try:
        return ObjectId(id_str)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail=f"Invalid ID format: {id_str}")


# ============================================================================
# QUERY LIST & DETAIL ENDPOINTS
# ============================================================================

@router.get("/queries", response_model=QueryListPaginatedResponse)
async def list_queries(
    status: Optional[QueryStatus] = Query(None),
    user_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(verify_jwt_token)
):
    """
    List all queries with filters and pagination.
    
    Simplified for current requirements: get it made, list, status.
    """
    try:
        user_role = current_user.get("role", "user")
        user_id_from_token = current_user.get("user_id") or current_user.get("_id")
        
        # Build filter
        filter_dict = {}
        
        # Role-based filtering
        if user_role == "user":
            # Users can only see their own queries
            filter_dict["user_id"] = user_id_from_token
        
        # Apply filters
        if status:
            filter_dict["status"] = status.value
        if user_id and user_role == "admin":
            filter_dict["user_id"] = user_id
        if date_from:
            date_from_dt = datetime.combine(date_from, datetime.min.time().replace(tzinfo=timezone(timedelta(hours=5, minutes=30))))
            if "created_at" in filter_dict:
                filter_dict["created_at"]["$gte"] = date_from_dt
            else:
                filter_dict["created_at"] = {"$gte": date_from_dt}
        if date_to:
            date_to_dt = datetime.combine(date_to, datetime.max.time().replace(tzinfo=timezone(timedelta(hours=5, minutes=30))))
            if "created_at" in filter_dict:
                filter_dict["created_at"]["$lte"] = date_to_dt
            else:
                filter_dict["created_at"] = {"$lte": date_to_dt}
        
        # Get total count (search will be done after fetching wish_history)
        total = await qms_queries_col.count_documents(filter_dict)
        
        # Get paginated results
        skip = (page - 1) * limit
        queries_cursor = qms_queries_col.find(filter_dict).sort("created_at", -1).skip(skip).limit(limit)
        queries = await queries_cursor.to_list(length=limit)
        
        # Enrich with user names and fetch formula details
        from app.ai_ingredient_intelligence.db.collections import wish_history_col
        query_responses = []
        for query in queries:
            # Get user name from main users collection
            user_name = None
            user_city = None
            if query.get("user_id"):
                user = await users_col.find_one({"_id": ObjectId(query["user_id"])})
                if user:
                    user_name = user.get("fullname") or user.get("name")
                    user_city = user.get("city")
            
            # Get formula name from query (stored directly) or fallback to wish_history
            formula_name = query.get("formula_name") or "Custom Formula"
            product_type = "Product"
            category = "skincare"
            wish_id = query.get("wish_id") or query.get("history_id")
            if wish_id and not query.get("formula_name"):
                wish_history = await wish_history_col.find_one({"_id": ObjectId(wish_id)})
                if wish_history:
                    formula_name = (
                        wish_history.get("name") 
                        or wish_history.get("formula_name")
                        or "Custom Formula"
                    )
                    product_type = (
                        wish_history.get("parsed_data", {}).get("product_type", {}).get("name")
                        or wish_history.get("wish_data", {}).get("productType")
                        or wish_history.get("product_type")
                        or "Product"
                    )
                    category = (
                        wish_history.get("parsed_data", {}).get("category")
                        or wish_history.get("wish_data", {}).get("category")
                        or wish_history.get("category")
                        or "skincare"
                    )
            
            # Apply search filter if provided (after fetching formula_name)
            if search:
                search_lower = search.lower()
                if search_lower not in formula_name.lower() and search_lower not in (user_name or "").lower():
                    continue  # Skip this query if it doesn't match search
            
            query_responses.append(QueryListResponse(
                id=str(query["_id"]),
                display_id=query.get("display_id", ""),
                formula_name=formula_name,
                user_name=user_name,
                user_city=user_city,
                product_type=product_type,
                category=category,
                status=QueryStatus(query.get("status", "new")),
                created_at=query.get("created_at", datetime.now())
            ))
        
        # Recalculate total if search was applied (since we filtered in memory)
        if search:
            total = len(query_responses)
        
        total_pages = math.ceil(total / limit) if total > 0 else 0
        
        return QueryListPaginatedResponse(
            queries=query_responses,
            page=page,
            limit=limit,
            total=total,
            total_pages=total_pages
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error listing queries: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to list queries: {str(e)}")


@router.get("/queries/{query_id}", response_model=QueryDetailResponse)
async def get_query_detail(
    query_id: str,
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Get detailed query information including user, partner, payment, and notes.
    
    Admin sees all data. Partners see formulation-relevant data only (no user background).
    """
    try:
        user_role = current_user.get("role", "user")
        user_id_from_token = current_user.get("user_id") or current_user.get("_id")
        
        query_obj_id = validate_object_id(query_id)
        query = await qms_queries_col.find_one({"_id": query_obj_id})
        
        if not query:
            raise HTTPException(status_code=404, detail="Query not found")
        
        # Role-based access control
        if user_role == "partner":
            partner = await qms_partners_col.find_one({"email": current_user.get("email")})
            if not partner or str(partner["_id"]) != query.get("partner_id"):
                raise HTTPException(status_code=403, detail="Access denied")
        elif user_role == "user":
            if str(query.get("user_id")) != user_id_from_token:
                raise HTTPException(status_code=403, detail="Access denied")
        
        # Get user from main users collection (only if admin or owner)
        user = None
        if user_role == "admin" or (user_role == "user" and str(query.get("user_id")) == user_id_from_token):
            user_doc = await users_col.find_one({"_id": ObjectId(query["user_id"])})
            if user_doc:
                user = UserInfo(
                    fullname=user_doc.get("fullname") or user_doc.get("name", ""),
                    phone=user_doc.get("phone", ""),
                    city=user_doc.get("city"),
                    pincode=user_doc.get("pincode")
                )
        
        # Get partner
        partner = None
        if query.get("partner_id"):
            partner_doc = await qms_partners_col.find_one({"_id": ObjectId(query["partner_id"])})
            if partner_doc:
                partner = PartnerResponse(
                    id=str(partner_doc["_id"]),
                    display_id=partner_doc.get("display_id", ""),
                    name=partner_doc.get("name", ""),
                    email=partner_doc.get("email", ""),
                    phone=partner_doc.get("phone", ""),
                    type=partner_doc.get("type"),
                    city=partner_doc.get("city"),
                    experience=partner_doc.get("experience"),
                    specializations=partner_doc.get("specializations", []),
                    bio=partner_doc.get("bio"),
                    notes=partner_doc.get("notes") if user_role == "admin" else None,  # Hide internal notes
                    rating=partner_doc.get("rating", 0.0),
                    status=partner_doc.get("status", "active"),
                    created_at=partner_doc.get("created_at", datetime.now()),
                    updated_at=partner_doc.get("updated_at", datetime.now())
                )
        
        # Get payment
        payment = None
        if query.get("payment_id") and user_role == "admin":
            payment_doc = await qms_payments_col.find_one({"_id": ObjectId(query["payment_id"])})
            if payment_doc:
                from app.ai_ingredient_intelligence.models.qms_schemas import PaymentResponse, PaymentStatus
                payment = PaymentResponse(
                    id=str(payment_doc["_id"]),
                    user_id=str(payment_doc.get("user_id", "")),
                    razorpay_order_id=payment_doc.get("razorpay_order_id"),
                    razorpay_payment_id=payment_doc.get("razorpay_payment_id"),
                    razorpay_signature=payment_doc.get("razorpay_signature"),
                    amount=payment_doc.get("amount", 0),
                    currency=payment_doc.get("currency", "INR"),
                    status=PaymentStatus(payment_doc.get("status", "created")),
                    method=payment_doc.get("method"),
                    refund_id=payment_doc.get("refund_id"),
                    refund_reason=payment_doc.get("refund_reason"),
                    created_at=payment_doc.get("created_at", datetime.now())
                )
        
        # Get notes (filtered by role)
        notes_filter = {"query_id": query_id, "deleted_at": None}
        if user_role != "admin":
            notes_filter["is_internal"] = False
        
        notes_cursor = qms_query_notes_col.find(notes_filter).sort("created_at", -1)
        notes_list = await notes_cursor.to_list(length=100)
        
        notes = []
        for note_doc in notes_list:
            notes.append(NoteResponse(
                id=str(note_doc["_id"]),
                query_id=note_doc.get("query_id", ""),
                author_id=str(note_doc.get("author_id", "")),
                author_role=NoteRole(note_doc.get("author_role", "user")),
                author_name=note_doc.get("author_name", ""),
                content=note_doc.get("content", ""),
                attachments=note_doc.get("attachments", []),
                is_internal=note_doc.get("is_internal", False),
                created_at=note_doc.get("created_at", datetime.now()),
                deleted_at=note_doc.get("deleted_at")
            ))
        
        # Fetch wish_brief from wish_history if needed
        wish_brief = None
        wish_id = query.get("wish_id") or query.get("history_id")
        if wish_id:
            from app.ai_ingredient_intelligence.db.collections import wish_history_col
            wish_history = await wish_history_col.find_one({"_id": ObjectId(wish_id)})
            if wish_history:
                # Return the full wish_history as wish_brief
                wish_brief = {
                    "formula_id": query.get("formula_id"),
                    "history_id": wish_id,
                    "formula_name": query.get("formula_name") or wish_history.get("name") or wish_history.get("formula_name"),
                    "product_type": wish_history.get("parsed_data", {}).get("product_type", {}).get("name") or wish_history.get("product_type"),
                    "category": wish_history.get("parsed_data", {}).get("category") or wish_history.get("wish_data", {}).get("category"),
                    "wish_data": wish_history.get("wish_data", {}),
                    "formula_data": wish_history.get("formula_data", {}),
                    "optimized_formula": wish_history.get("formula_data", {}) or wish_history.get("basic_mode_result", {})
                }
        
        return QueryDetailResponse(
            id=str(query["_id"]),
            display_id=query.get("display_id", ""),
            user_id=str(query.get("user_id", "")),
            formula_id=query.get("formula_id", ""),
            wish_id=query.get("wish_id") or query.get("history_id", ""),
            formula_name=query.get("formula_name", "Custom Formula"),
            experience_level=query.get("experience_level", ""),
            timeline=query.get("timeline", ""),
            quantity_interest=query.get("quantity_interest"),
            additional_notes=query.get("additional_notes"),
            status=QueryStatus(query.get("status", "new")),
            wish_brief=wish_brief,
            created_at=query.get("created_at", datetime.now()),
            updated_at=query.get("updated_at", datetime.now()),
            user=user,
            partner=partner,
            payment=payment,
            notes=notes
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error getting query detail: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to get query detail: {str(e)}")


# ============================================================================
# QUERY OPERATIONS (Role-based access control)
# ============================================================================

# TODO: Partner assignment - to be implemented later
# @router.post("/queries/{query_id}/assign")
# async def assign_partner(...):
#     """Assign a partner to a query. Admin only. - Not needed for current requirements"""


@router.patch("/queries/{query_id}/status")
async def update_query_status(
    query_id: str,
    request: QueryStatusUpdateRequest,
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Update query status. Admin can override any transition.
    """
    try:
        user_role = current_user.get("role", "user")
        if user_role != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        
        query_obj_id = validate_object_id(query_id)
        query = await qms_queries_col.find_one({"_id": query_obj_id})
        
        if not query:
            raise HTTPException(status_code=404, detail="Query not found")
        
        old_status = query.get("status")
        
        # Update status (simplified - no milestones or dates for now)
        update_data = {
            "status": request.status.value,
            "updated_at": datetime.now(timezone(timedelta(hours=5, minutes=30)))
        }
        
        await qms_queries_col.update_one(
            {"_id": query_obj_id},
            {"$set": update_data}
        )
        
        # Log audit
        await log_audit(
            actor_id=str(current_user.get("user_id") or current_user.get("_id")),
            actor_role="admin",
            action="query.status_changed",
            resource_type="query",
            resource_id=query_id,
            details={"old_status": old_status, "new_status": request.status.value}
        )
        
        return {
            "success": True,
            "message": "Status updated successfully",
            "query_id": query_id,
            "old_status": old_status,
            "new_status": request.status.value
        }
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error updating status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update status: {str(e)}")


# TODO: Priority update - to be implemented later
# @router.patch("/queries/{query_id}/priority")
# async def update_query_priority(...):
#     """Update query priority. Admin only. - Not needed for current requirements"""


# ============================================================================
# REFUND ENDPOINT
# ============================================================================

@router.post("/queries/{query_id}/refund")
async def process_refund(
    query_id: str,
    request: RefundRequest,
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Process refund for consultation fee after call completion.
    Admin only. Updates payment status to REFUNDED.
    """
    try:
        user_role = current_user.get("role", "user")
        if user_role != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        
        query_obj_id = validate_object_id(query_id)
        query = await qms_queries_col.find_one({"_id": query_obj_id})
        
        if not query:
            raise HTTPException(status_code=404, detail="Query not found")
        
        payment_id = query.get("payment_id")
        if not payment_id:
            raise HTTPException(status_code=400, detail="No payment found for this query")
        
        payment_obj_id = validate_object_id(payment_id)
        payment = await qms_payments_col.find_one({"_id": payment_obj_id})
        
        if not payment:
            raise HTTPException(status_code=404, detail="Payment not found")
        
        # Check if already refunded
        if payment.get("status") == PaymentStatus.REFUNDED.value:
            raise HTTPException(status_code=400, detail="Payment already refunded")
        
        # Check if payment was captured
        if payment.get("status") != PaymentStatus.CAPTURED.value:
            raise HTTPException(status_code=400, detail=f"Cannot refund payment with status: {payment.get('status')}")
        
        razorpay_payment_id = payment.get("razorpay_payment_id")
        refund_reason = request.refund_reason or "Consultation call completed"
        
        # Process refund through Razorpay (if payment_id exists)
        refund_id = None
        if razorpay_payment_id:
            try:
                # TODO: Integrate with Razorpay SDK when available
                # import razorpay
                # razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
                # refund = razorpay_client.payment.refund(razorpay_payment_id, {"amount": payment.get("amount")})
                # refund_id = refund["id"]
                
                # For now, generate a mock refund ID (replace with actual Razorpay integration)
                refund_id = f"rfnd_{razorpay_payment_id[:10]}_{int(datetime.now().timestamp())}"
                print(f"⚠️ Mock refund ID generated: {refund_id}. Replace with actual Razorpay integration.")
            except Exception as e:
                print(f"❌ Error processing Razorpay refund: {e}")
                # Continue with database update even if Razorpay fails (for manual processing)
        
        # Update payment record
        update_data = {
            "status": PaymentStatus.REFUNDED.value,
            "refund_id": refund_id,
            "refund_reason": refund_reason,
            "updated_at": datetime.now(timezone(timedelta(hours=5, minutes=30)))
        }
        
        await qms_payments_col.update_one(
            {"_id": payment_obj_id},
            {"$set": update_data}
        )
        
        # Log audit
        await log_audit(
            actor_id=str(current_user.get("user_id") or current_user.get("_id")),
            actor_role="admin",
            action="payment.refunded",
            resource_type="payment",
            resource_id=payment_id,
            details={
                "query_id": query_id,
                "refund_id": refund_id,
                "refund_reason": refund_reason,
                "amount": payment.get("amount")
            }
        )
        
        return {
            "success": True,
            "message": "Refund processed successfully",
            "query_id": query_id,
            "payment_id": payment_id,
            "refund_id": refund_id,
            "refund_reason": refund_reason,
            "amount": payment.get("amount"),
            "amount_in_rupees": payment.get("amount", 0) / 100
        }
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error processing refund: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to process refund: {str(e)}")


# ============================================================================
# NOTES ENDPOINTS
# ============================================================================

@router.post("/queries/{query_id}/notes", response_model=NoteResponse)
async def create_note(
    query_id: str,
    request: NoteCreate,
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Create a note for a query. Role is auto-detected from JWT.
    """
    try:
        user_role = current_user.get("role", "user")
        user_id = str(current_user.get("user_id") or current_user.get("_id"))
        
        query_obj_id = validate_object_id(query_id)
        query = await qms_queries_col.find_one({"_id": query_obj_id})
        
        if not query:
            raise HTTPException(status_code=404, detail="Query not found")
        
        # Get author name based on role
        author_name = current_user.get("name", "Unknown")
        if user_role == "partner":
            partner = await qms_partners_col.find_one({"_id": ObjectId(user_id)})
            if partner:
                author_name = partner.get("name", "Unknown")
        elif user_role == "user":
            user = await users_col.find_one({"_id": ObjectId(user_id)})
            if user:
                author_name = user.get("fullname") or user.get("name", "Unknown")
        
        # Create note
        note_doc = {
            "query_id": query_id,
            "author_id": user_id,
            "author_role": user_role,
            "author_name": author_name,
            "content": request.content,
            "attachments": request.attachments or [],
            "is_internal": request.is_internal if user_role == "admin" else False,
            "created_at": datetime.now(timezone(timedelta(hours=5, minutes=30))),
            "deleted_at": None
        }
        
        result = await qms_query_notes_col.insert_one(note_doc)
        note_doc["_id"] = result.inserted_id
        
        # Log audit
        await log_audit(
            actor_id=user_id,
            actor_role=user_role,
            action="note.created",
            resource_type="note",
            resource_id=str(result.inserted_id),
            details={"query_id": query_id}
        )
        
        return NoteResponse(
            id=str(note_doc["_id"]),
            query_id=note_doc["query_id"],
            author_id=note_doc["author_id"],
            author_role=NoteRole(note_doc["author_role"]),
            author_name=note_doc["author_name"],
            content=note_doc["content"],
            attachments=note_doc["attachments"],
            is_internal=note_doc["is_internal"],
            created_at=note_doc["created_at"],
            deleted_at=None
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error creating note: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create note: {str(e)}")


@router.delete("/queries/{query_id}/notes/{note_id}")
async def delete_note(
    query_id: str,
    note_id: str,
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Soft-delete a note. Admin only.
    """
    try:
        user_role = current_user.get("role", "user")
        if user_role != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        
        note_obj_id = validate_object_id(note_id)
        note = await qms_query_notes_col.find_one({"_id": note_obj_id})
        
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")
        
        # Soft delete
        await qms_query_notes_col.update_one(
            {"_id": note_obj_id},
            {"$set": {"deleted_at": datetime.now(timezone(timedelta(hours=5, minutes=30)))}}
        )
        
        return {
            "success": True,
            "message": "Note deleted successfully"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error deleting note: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete note: {str(e)}")


# ============================================================================
# QUERY CREATION FROM COMMERCIALIZATION REQUEST
# ============================================================================

# REMOVED: This endpoint is no longer needed since we use qms_queries directly
# Commercialization requests are now created as QMS queries immediately in make_wish_api_revised.py


# ============================================================================
# DASHBOARD STATS
# ============================================================================

@router.get("/stats", response_model=QueryStatsResponse)
async def get_dashboard_stats(
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Get dashboard statistics for admin. Shows counts by status, priority, revenue.
    """
    try:
        user_role = current_user.get("role", "user")
        if user_role != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        
        # Total queries
        total_queries = await qms_queries_col.count_documents({})
        
        # Count by status
        status_pipeline = [
            {"$group": {"_id": "$status", "count": {"$sum": 1}}}
        ]
        status_counts = {}
        async for doc in qms_queries_col.aggregate(status_pipeline):
            status_counts[doc["_id"]] = doc["count"]
        
        # Revenue (sum of all captured payments)
        revenue_pipeline = [
            {"$match": {"status": "captured"}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ]
        revenue_result = await qms_payments_col.aggregate(revenue_pipeline).to_list(length=1)
        revenue = (revenue_result[0]["total"] / 100) if revenue_result else 0.0  # Convert paise to ₹
        
        return QueryStatsResponse(
            total_queries=total_queries,
            by_status=status_counts,
            revenue=revenue
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")

