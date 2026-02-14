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
            # Get user name from main users collection, with fallback to stored form data
            user_name = None
            user_city = None
            if query.get("user_id"):
                user = await users_col.find_one({"_id": ObjectId(query["user_id"])})
                if user:
                    user_name = user.get("fullname") or user.get("name")
                    user_city = user.get("city")
            
            # Fallback: Use stored form data if user collection doesn't have name
            if not user_name:
                user_name = query.get("user_name")  # From get-this-made form
            if not user_city:
                user_city = query.get("user_city")  # From get-this-made form
            
            # Get formula name from query (stored directly) or fallback to wish_history
            formula_name = query.get("formula_name") or "Custom Formula"
            product_type = "Product"
            category = "skincare"
            wish_id = query.get("wish_id") or query.get("history_id")
            # Always fetch wish_history to get product_type and category, even if formula_name exists
            if wish_id:
                wish_history = await wish_history_col.find_one({"_id": ObjectId(wish_id)})
                if wish_history:
                    # Update formula_name if not already set in query
                    if not query.get("formula_name"):
                        formula_name = (
                            wish_history.get("name") 
                            or wish_history.get("formula_name")
                            or "Custom Formula"
                        )
                    # Always fetch product_type and category from wish_history
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
                queue_number=query.get("queue_number"),
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


@router.get("/queries/{query_id}", response_model=QueryDetailResponse, response_model_exclude={"user_id"})
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
            print(f"❌ Query not found: {query_id}")
            print(f"   User ID from token: {user_id_from_token}")
            raise HTTPException(status_code=404, detail=f"Query not found: {query_id}")
        
        print(f"✅ Query found: {query_id}")
        print(f"   Query user_id: {query.get('user_id')}")
        print(f"   Token user_id: {user_id_from_token}")
        print(f"   User role: {user_role}")
        print(f"   Query document keys: {list(query.keys())}")
        print(f"   payment_id in query: {query.get('payment_id')} (type: {type(query.get('payment_id'))})")
        print(f"   Payment ID in query: {query.get('payment_id')} (type: {type(query.get('payment_id'))})")
        
        # Role-based access control
        if user_role == "partner":
            partner = await qms_partners_col.find_one({"email": current_user.get("email")})
            if not partner or str(partner["_id"]) != query.get("partner_id"):
                raise HTTPException(status_code=403, detail="Access denied")
        elif user_role == "user":
            query_user_id = str(query.get("user_id", ""))
            if query_user_id != user_id_from_token:
                print(f"⚠️ Access denied: Query user_id ({query_user_id}) != Token user_id ({user_id_from_token})")
                raise HTTPException(status_code=403, detail="Access denied - Query belongs to different user")
        
        # Get user from main users collection (only if admin or owner)
        user = None
        query_user_id_str = str(query.get("user_id", ""))
        print(f"🔍 Fetching user info...")
        print(f"   Query user_id: {query_user_id_str}")
        print(f"   Token user_id: {user_id_from_token}")
        print(f"   User role: {user_role}")
        print(f"   Stored form data - name: {query.get('user_name')}, phone: {query.get('user_phone')}")
        
        if user_role == "admin" or (user_role == "user" and query_user_id_str == user_id_from_token):
            try:
                if query_user_id_str and len(query_user_id_str) == 24:
                    user_doc = await users_col.find_one({"_id": ObjectId(query["user_id"])})
                    if user_doc:
                        print(f"✅ Found user in users collection")
                        # Use stored form data as fallback if user collection doesn't have the field
                        fullname = user_doc.get("fullname") or user_doc.get("name") or query.get("user_name", "")
                        phone = user_doc.get("phone") or query.get("user_phone", "")
                        city = user_doc.get("city") or query.get("user_city")
                        email = user_doc.get("email") or query.get("user_email")
                        pincode = user_doc.get("pincode") or query.get("user_pincode")
                        user = UserInfo(
                            fullname=fullname,
                            phone=phone,
                            city=city,
                            pincode=pincode
                        )
                    else:
                        print(f"⚠️ User not found in users collection, using stored form data")
                        # If user not found in users collection, use stored form data
                        if query.get("user_name") or query.get("user_phone"):
                            user = UserInfo(
                                fullname=query.get("user_name", ""),
                                phone=query.get("user_phone", ""),
                                city=query.get("user_city"),
                                pincode=query.get("user_pincode")
                            )
                else:
                    print(f"⚠️ Invalid user_id format, using stored form data")
                    # Invalid user_id format, use stored form data
                    if query.get("user_name") or query.get("user_phone"):
                        user = UserInfo(
                            fullname=query.get("user_name", ""),
                            phone=query.get("user_phone", ""),
                            city=query.get("user_city"),
                            pincode=query.get("user_pincode")
                        )
            except Exception as e:
                print(f"⚠️ Error fetching user from users collection: {e}")
                # Fallback to stored form data on error
                if query.get("user_name") or query.get("user_phone"):
                    user = UserInfo(
                        fullname=query.get("user_name", ""),
                        phone=query.get("user_phone", ""),
                        city=query.get("user_city"),
                        pincode=query.get("user_pincode")
                    )
        
        # Always use stored form data if available, even if user_doc lookup failed
        if not user and (query.get("user_name") or query.get("user_phone")):
            print(f"✅ Using stored form data for user info")
            user = UserInfo(
                fullname=query.get("user_name", ""),
                phone=query.get("user_phone", ""),
                city=query.get("user_city"),
                pincode=query.get("user_pincode")
            )
        
        print(f"   Final user object: {user}")
        
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
        
        # Get payment: fetch payment_id from qms_queries, then get payment data from qms_payments
        payment = None
        payment_id_from_query = query.get("payment_id")
        query_id_str = str(query["_id"])
        
        print(f"🔍 Fetching payment for query {query_id_str}")
        print(f"   Step 1: payment_id from qms_queries: {payment_id_from_query} (type: {type(payment_id_from_query)})")
        
        if payment_id_from_query:
            try:
                # Convert payment_id to ObjectId (handles both string and ObjectId)
                if isinstance(payment_id_from_query, ObjectId):
                    payment_obj_id = payment_id_from_query
                else:
                    payment_obj_id = ObjectId(str(payment_id_from_query))
                
                print(f"   Step 2: Looking up payment in qms_payments_col with _id: {payment_obj_id}")
                
                # Fetch payment document from qms_payments collection
                payment_doc = await qms_payments_col.find_one({"_id": payment_obj_id})
                
                if payment_doc:
                    print(f"✅ Found payment document in qms_payments_col")
                else:
                    print(f"❌ Payment document NOT FOUND in qms_payments_col for _id: {payment_obj_id}")
                    print(f"   payment_id exists in qms_queries but payment document doesn't exist in qms_payments_col!")
                    payment_doc = None
            except (InvalidId, ValueError) as e:
                print(f"⚠️ payment_id '{payment_id_from_query}' is not a valid MongoDB ObjectId: {e}")
                payment_doc = None
            except Exception as e:
                print(f"⚠️ Error fetching payment from qms_payments_col: {e}")
                import traceback
                traceback.print_exc()
                payment_doc = None
        else:
            print(f"ℹ️ No payment_id found in qms_queries document - query has no payment associated")
            payment_doc = None
            
            # Fallback: Try to find payment by queryId or displayId
            print(f"   🔍 Trying fallback: searching for payment by queryId or displayId...")
            try:
                # Try to find payment where queryId matches this query's _id
                query_id_str = str(query["_id"])
                payment_by_query_id = await qms_payments_col.find_one({
                    "queryId": query_id_str
                })
                
                if payment_by_query_id:
                    print(f"   ✅ Found payment by queryId: {payment_by_query_id.get('_id')}")
                    payment_doc = payment_by_query_id
                else:
                    # Try to find payment by displayId (e.g., QRY-2025-001)
                    display_id = query.get("display_id")
                    if display_id:
                        payment_by_display_id = await qms_payments_col.find_one({
                            "paymentDetails.displayId": display_id
                        })
                        if payment_by_display_id:
                            print(f"   ✅ Found payment by displayId: {payment_by_display_id.get('_id')}")
                            payment_doc = payment_by_display_id
                        else:
                            print(f"   ❌ No payment found by queryId or displayId")
            except Exception as e:
                print(f"   ⚠️ Error in fallback payment search: {e}")
        
        # If payment document found, map it to PaymentResponse
        if payment_doc:
            try:
                from app.ai_ingredient_intelligence.models.qms_schemas import PaymentResponse, PaymentStatus
                
                # Map actual payment document fields to PaymentResponse schema
                # Payment doc has: userId, transactionId, providerOrderId, status, etc.
                # PaymentResponse expects: user_id, razorpay_payment_id, razorpay_order_id, etc.
                
                # Map status - "paid" from doc is returned as "paid" (PaymentStatus.CAPTURED)
                payment_status = payment_doc.get("status", "created").lower()
                if payment_status == "paid":
                    status_enum = PaymentStatus.CAPTURED  # serializes as "paid"
                elif payment_status == "refunded":
                    status_enum = PaymentStatus.REFUNDED
                elif payment_status == "failed":
                    status_enum = PaymentStatus.FAILED
                else:
                    status_enum = PaymentStatus.CREATED
                
                # Get amount - prefer razorpayPayment amount (in paise), otherwise use root amount
                # If root amount looks like rupees (small number), convert to paise
                razorpay_payment = payment_doc.get("paymentDetails", {}).get("razorpayPayment", {})
                amount_in_paise = razorpay_payment.get("amount")  # This is definitely in paise
                if not amount_in_paise:
                    root_amount = payment_doc.get("amount", 0)
                    # If amount is less than 10000, assume it's in rupees and convert to paise
                    if root_amount < 10000:
                        amount_in_paise = root_amount * 100
                    else:
                        amount_in_paise = root_amount
                
                payment = PaymentResponse(
                    id=str(payment_doc["_id"]),
                    user_id=str(payment_doc.get("userId") or payment_doc.get("user_id", "")),
                    razorpay_order_id=payment_doc.get("providerOrderId") or payment_doc.get("razorpay_order_id") or payment_doc.get("paymentDetails", {}).get("razorpayOrderId"),
                    razorpay_payment_id=payment_doc.get("transactionId") or payment_doc.get("providerPaymentId") or payment_doc.get("razorpay_payment_id") or razorpay_payment.get("id"),
                    razorpay_signature=payment_doc.get("razorpay_signature") or payment_doc.get("paymentDetails", {}).get("razorpaySignature"),
                    amount=amount_in_paise,  # Amount in paise
                    currency=payment_doc.get("currency", "INR"),
                    status=status_enum,
                    method=payment_doc.get("paymentMethod") or payment_doc.get("method") or razorpay_payment.get("method"),
                    refund_id=payment_doc.get("refund_id") or payment_doc.get("refundId"),
                    refund_reason=payment_doc.get("refund_reason") or payment_doc.get("refundReason"),
                    created_at=payment_doc.get("createdAt") or payment_doc.get("created_at", datetime.now())
                )
                print(f"✅ Successfully mapped payment document to PaymentResponse")
            except Exception as e:
                print(f"⚠️ Error mapping payment document to PaymentResponse: {e}")
                import traceback
                traceback.print_exc()
                payment = None
        else:
            print(f"⚠️ No payment document found for query {query_id_str}")
            print(f"ℹ️ No payment_id found in query document")
        
        # Get notes (filtered by role)
        # notes_filter = {"query_id": query_id, "deleted_at": None}
        # if user_role != "admin":
        #     notes_filter["is_internal"] = False
        
        # notes_cursor = qms_query_notes_col.find(notes_filter).sort("created_at", -1)
        # notes_list = await notes_cursor.to_list(length=100)
        
        # notes = []
        # for note_doc in notes_list:
        #     notes.append(NoteResponse(
        #         id=str(note_doc["_id"]),
        #         query_id=note_doc.get("query_id", ""),
        #         author_id=str(note_doc.get("author_id", "")),
        #         author_role=NoteRole(note_doc.get("author_role", "user")),
        #         author_name=note_doc.get("author_name", ""),
        #         content=note_doc.get("content", ""),
        #         attachments=note_doc.get("attachments", []),
        #         is_internal=note_doc.get("is_internal", False),
        #         created_at=note_doc.get("created_at", datetime.now()),
        #         deleted_at=note_doc.get("deleted_at")
        #     ))
        
        return QueryDetailResponse(
            id=str(query["_id"]),
            display_id=query.get("display_id", ""),
            queue_number=query.get("queue_number"),
            formula_id=query.get("formula_id", ""),
            wish_id=query.get("wish_id") or query.get("history_id", ""),
            formula_name=query.get("formula_name", "Custom Formula"),
            experience_level=query.get("experience_level", ""),
            timeline=query.get("timeline", ""),
            quantity_interest=query.get("quantity_interest"),
            additional_notes=query.get("additional_notes") if isinstance(query.get("additional_notes"), str) else (", ".join(query.get("additional_notes")) if isinstance(query.get("additional_notes"), list) else str(query.get("additional_notes")) if query.get("additional_notes") else None),
            status=QueryStatus(query.get("status", "new")),
            created_at=query.get("created_at", datetime.now()),
            updated_at=query.get("updated_at", datetime.now()),
            user=user,
            partner=partner,
            payment=payment,
            # notes=notes
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
    Update query status. Users can update their own queries, admins can update any query.
    """
    try:
        user_role = current_user.get("role", "user")
        user_id_from_token = current_user.get("user_id") or current_user.get("_id")
        
        query_obj_id = validate_object_id(query_id)
        query = await qms_queries_col.find_one({"_id": query_obj_id})
        
        if not query:
            raise HTTPException(status_code=404, detail="Query not found")
        
        # Access control: Users can only update their own queries, admins can update any
        if user_role != "admin":
            if str(query.get("user_id")) != user_id_from_token:
                raise HTTPException(
                    status_code=403, 
                    detail="You can only update your own queries"
                )
        
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
            actor_id=str(user_id_from_token),
            actor_role=user_role,
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


@router.patch("/queries/{query_id}")
async def update_query(
    query_id: str,
    request: dict,
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Update any query fields.
    Users can update their own queries, admins can update any query.
    
    You can update any field except protected ones:
    - Protected fields (cannot be updated): _id, user_id, created_at, display_id
    
    Common fields you can update:
    - status: Query status (e.g., "new", "under_review", "completed")
    - payment_id: Payment ID (e.g., after payment is processed)
    - additional_notes: Additional notes
    - quantity_interest: Quantity interest
    - experience_level: Experience level
    - timeline: Timeline
    - formula_name: Formula name
    - partner_id: Partner assignment
    - queue_number: Queue number
    - And any other custom fields
    """
    try:
        user_role = current_user.get("role", "user")
        user_id_from_token = current_user.get("user_id") or current_user.get("_id")
        
        query_obj_id = validate_object_id(query_id)
        query = await qms_queries_col.find_one({"_id": query_obj_id})
        
        if not query:
            raise HTTPException(status_code=404, detail="Query not found")
        
        # Access control: Users can only update their own queries, admins can update any
        if user_role != "admin":
            if str(query.get("user_id")) != user_id_from_token:
                raise HTTPException(
                    status_code=403, 
                    detail="You can only update your own queries"
                )
        
        # Protected fields that cannot be updated
        protected_fields = {
            "_id",
            "user_id",
            "created_at",
            "display_id"
        }
        
        # Validate status if provided
        if "status" in request:
            status_value = request["status"]
            # Check if it's a valid QueryStatus enum value
            try:
                if isinstance(status_value, str):
                    QueryStatus(status_value)  # Validate it's a valid status
                else:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid status format. Expected string, got {type(status_value)}"
                    )
            except ValueError:
                valid_statuses = [s.value for s in QueryStatus]
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status value: {status_value}. Valid values: {', '.join(valid_statuses)}"
                )
        
        # Filter out protected fields and build update data
        update_data = {}
        for key, value in request.items():
            if key in protected_fields:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot update protected field: {key}"
                )
            update_data[key] = value
        
        if not update_data:
            raise HTTPException(
                status_code=400,
                detail="No fields to update. Provide at least one field to update."
            )
        
        # Add updated_at timestamp
        update_data["updated_at"] = datetime.now(timezone(timedelta(hours=5, minutes=30)))
        
        # Track old status if status is being updated
        old_status = None
        if "status" in update_data:
            old_status = query.get("status")
        
        # Update query
        await qms_queries_col.update_one(
            {"_id": query_obj_id},
            {"$set": update_data}
        )
        
        # Prepare audit details
        audit_details = {"updated_fields": list(update_data.keys())}
        if old_status and "status" in update_data:
            audit_details["old_status"] = old_status
            audit_details["new_status"] = update_data["status"]
            action = "query.status_changed"
        else:
            action = "query.updated"
        
        # Log audit
        await log_audit(
            actor_id=str(user_id_from_token),
            actor_role=user_role,
            action=action,
            resource_type="query",
            resource_id=query_id,
            details=audit_details
        )
        
        response = {
            "success": True,
            "message": "Query updated successfully",
            "query_id": query_id,
            "updated_fields": list(update_data.keys())
        }
        
        # Include status change info if status was updated
        if old_status and "status" in update_data:
            response["old_status"] = old_status
            response["new_status"] = update_data["status"]
        
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error updating query: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to update query: {str(e)}")


# ============================================================================
# PAYMENT ENDPOINTS
# ============================================================================

# Payment details are now included in the query detail endpoint (GET /api/qms/queries/{query_id}).
# This separate endpoint is kept for backward compatibility but is not recommended.
# Use GET /api/qms/queries/{query_id} instead to get payment details along with query info.


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
        
        # Revenue (sum of all paid payments; include legacy "captured" in DB)
        revenue_pipeline = [
            {"$match": {"status": {"$in": [PaymentStatus.CAPTURED.value, "captured"]}}},
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

