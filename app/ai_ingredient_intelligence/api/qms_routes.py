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
    QueryAssignRequest,
    QueryStatusUpdateRequest,
    QueryPriorityUpdateRequest,
    QueryReassignRequest,
    QueryFilters,
    QueryListPaginatedResponse,
    QueryStatsResponse,
    NoteCreate,
    NoteResponse,
    PartnerCreate,
    PartnerResponse,
    PartnerListResponse,
    QueryStatus,
    QueryPriority,
    PartnerStatus,
    NoteRole,
)
from app.ai_ingredient_intelligence.db.collections import (
    qms_users_col,
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
    priority: Optional[QueryPriority] = Query(None),
    partner_id: Optional[str] = Query(None),
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
    
    Admin can see all queries. Partners can only see assigned queries.
    """
    try:
        user_role = current_user.get("role", "user")
        user_id_from_token = current_user.get("user_id") or current_user.get("_id")
        
        # Build filter
        filter_dict = {}
        
        # Role-based filtering
        if user_role == "partner":
            # Partners can only see their assigned queries
            partner = await qms_partners_col.find_one({"email": current_user.get("email")})
            if not partner:
                raise HTTPException(status_code=403, detail="Partner not found")
            filter_dict["partner_id"] = str(partner["_id"])
        elif user_role == "user":
            # Users can only see their own queries
            filter_dict["user_id"] = user_id_from_token
        
        # Apply filters
        if status:
            filter_dict["status"] = status.value
        if priority:
            filter_dict["priority"] = priority.value
        if partner_id:
            filter_dict["partner_id"] = partner_id
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
        
        # Search filter
        if search:
            filter_dict["$or"] = [
                {"formula_name": {"$regex": search, "$options": "i"}},
                {"user_name": {"$regex": search, "$options": "i"}},
            ]
        
        # Get total count
        total = await qms_queries_col.count_documents(filter_dict)
        
        # Get paginated results
        skip = (page - 1) * limit
        queries_cursor = qms_queries_col.find(filter_dict).sort("created_at", -1).skip(skip).limit(limit)
        queries = await queries_cursor.to_list(length=limit)
        
        # Enrich with user and partner names
        query_responses = []
        for query in queries:
            # Get user name
            user_name = None
            user_city = None
            if query.get("user_id"):
                user = await qms_users_col.find_one({"_id": ObjectId(query["user_id"])})
                if user:
                    user_name = user.get("name")
                    user_city = user.get("city")
            
            # Get partner name
            partner_name = None
            if query.get("partner_id"):
                partner = await qms_partners_col.find_one({"_id": ObjectId(query["partner_id"])})
                if partner:
                    partner_name = partner.get("name")
            
            # Get note count
            note_count = await qms_query_notes_col.count_documents({
                "query_id": str(query["_id"]),
                "deleted_at": None
            })
            
            # Get last activity (from notes)
            last_note = await qms_query_notes_col.find_one(
                {"query_id": str(query["_id"]), "deleted_at": None},
                sort=[("created_at", -1)]
            )
            last_activity = last_note.get("created_at") if last_note else query.get("updated_at")
            
            query_responses.append(QueryListResponse(
                id=str(query["_id"]),
                display_id=query.get("display_id", ""),
                formula_name=query.get("formula_name", ""),
                user_name=user_name,
                user_city=user_city,
                product_type=query.get("product_type", ""),
                category=query.get("category", ""),
                status=QueryStatus(query.get("status", "new")),
                priority=QueryPriority(query.get("priority", "normal")),
                partner_id=str(query["partner_id"]) if query.get("partner_id") else None,
                partner_name=partner_name,
                current_milestone=query.get("current_milestone", 0),
                payment_date=query.get("payment_date"),
                note_count=note_count,
                last_activity=last_activity,
                created_at=query.get("created_at", datetime.now())
            ))
        
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
        
        # Get user (only if admin or owner)
        user = None
        if user_role == "admin" or (user_role == "user" and str(query.get("user_id")) == user_id_from_token):
            user_doc = await qms_users_col.find_one({"_id": ObjectId(query["user_id"])})
            if user_doc:
                from app.ai_ingredient_intelligence.models.qms_schemas import UserResponse
                user = UserResponse(
                    id=str(user_doc["_id"]),
                    name=user_doc.get("name", ""),
                    email=user_doc.get("email", ""),
                    phone=user_doc.get("phone", ""),
                    city=user_doc.get("city"),
                    background=user_doc.get("background"),
                    preferred_batch=user_doc.get("preferred_batch"),
                    source=user_doc.get("source", "make_a_wish"),
                    created_at=user_doc.get("created_at", datetime.now()),
                    updated_at=user_doc.get("updated_at", datetime.now())
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
        
        return QueryDetailResponse(
            id=str(query["_id"]),
            display_id=query.get("display_id", ""),
            user_id=str(query.get("user_id", "")),
            partner_id=str(query["partner_id"]) if query.get("partner_id") else None,
            formula_name=query.get("formula_name", ""),
            product_type=query.get("product_type", ""),
            category=query.get("category", ""),
            target_mrp=query.get("target_mrp"),
            batch_size=query.get("batch_size"),
            status=QueryStatus(query.get("status", "new")),
            priority=QueryPriority(query.get("priority", "normal")),
            current_milestone=query.get("current_milestone", 0),
            wish_brief=query.get("wish_brief", {}),
            payment_id=str(query["payment_id"]) if query.get("payment_id") else None,
            payment_date=query.get("payment_date"),
            assigned_date=query.get("assigned_date"),
            completed_date=query.get("completed_date"),
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
# ADMIN QUERY OPERATIONS
# ============================================================================

@router.post("/admin/queries/{query_id}/assign")
async def assign_partner(
    query_id: str,
    request: QueryAssignRequest,
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Assign a partner to a query. Admin only.
    """
    try:
        user_role = current_user.get("role", "user")
        if user_role != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        
        query_obj_id = validate_object_id(query_id)
        partner_obj_id = validate_object_id(request.partner_id)
        
        # Check query exists
        query = await qms_queries_col.find_one({"_id": query_obj_id})
        if not query:
            raise HTTPException(status_code=404, detail="Query not found")
        
        # Check partner exists and is active
        partner = await qms_partners_col.find_one({"_id": partner_obj_id})
        if not partner:
            raise HTTPException(status_code=404, detail="Partner not found")
        
        if partner.get("status") != "active":
            raise HTTPException(status_code=400, detail="Cannot assign: partner is not active")
        
        # Update query
        update_data = {
            "partner_id": request.partner_id,
            "status": QueryStatus.ASSIGNED.value,
            "assigned_date": date.today(),
            "current_milestone": 2,  # Partner Assigned milestone
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
            action="query.assigned",
            resource_type="query",
            resource_id=query_id,
            details={"partner_id": request.partner_id, "old_status": query.get("status")}
        )
        
        return {
            "success": True,
            "message": "Partner assigned successfully",
            "query_id": query_id,
            "partner_id": request.partner_id,
            "status": QueryStatus.ASSIGNED.value
        }
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error assigning partner: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to assign partner: {str(e)}")


@router.patch("/admin/queries/{query_id}/status")
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
        
        # Update status
        update_data = {
            "status": request.status.value,
            "updated_at": datetime.now(timezone(timedelta(hours=5, minutes=30)))
        }
        
        # Update milestone based on status
        status_milestone_map = {
            QueryStatus.UNDER_REVIEW.value: 1,
            QueryStatus.ASSIGNED.value: 2,
            QueryStatus.CONSULTATION_DONE.value: 3,
            QueryStatus.BRIEF_SHARED.value: 4,
            QueryStatus.IN_PROGRESS.value: 5,
            QueryStatus.SAMPLE_READY.value: 6,
            QueryStatus.COMPLETED.value: 7,
        }
        
        if request.status.value in status_milestone_map:
            update_data["current_milestone"] = status_milestone_map[request.status.value]
        
        if request.status == QueryStatus.COMPLETED:
            update_data["completed_date"] = date.today()
        
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


@router.patch("/admin/queries/{query_id}/priority")
async def update_query_priority(
    query_id: str,
    request: QueryPriorityUpdateRequest,
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Update query priority. Admin only.
    """
    try:
        user_role = current_user.get("role", "user")
        if user_role != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        
        query_obj_id = validate_object_id(query_id)
        query = await qms_queries_col.find_one({"_id": query_obj_id})
        
        if not query:
            raise HTTPException(status_code=404, detail="Query not found")
        
        await qms_queries_col.update_one(
            {"_id": query_obj_id},
            {"$set": {
                "priority": request.priority.value,
                "updated_at": datetime.now(timezone(timedelta(hours=5, minutes=30)))
            }}
        )
        
        return {
            "success": True,
            "message": "Priority updated successfully",
            "query_id": query_id,
            "priority": request.priority.value
        }
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error updating priority: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update priority: {str(e)}")


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
            user = await qms_users_col.find_one({"_id": ObjectId(user_id)})
            if user:
                author_name = user.get("name", "Unknown")
        
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


@router.delete("/admin/queries/{query_id}/notes/{note_id}")
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
# DASHBOARD STATS
# ============================================================================

@router.get("/admin/stats", response_model=QueryStatsResponse)
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
        
        # Count by priority
        priority_pipeline = [
            {"$group": {"_id": "$priority", "count": {"$sum": 1}}}
        ]
        priority_counts = {}
        async for doc in qms_queries_col.aggregate(priority_pipeline):
            priority_counts[doc["_id"]] = doc["count"]
        
        # Unassigned count
        unassigned_count = await qms_queries_col.count_documents({"partner_id": None})
        
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
            by_priority=priority_counts,
            unassigned_count=unassigned_count,
            revenue=revenue
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")

