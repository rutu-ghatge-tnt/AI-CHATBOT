"""
Query Management System (QMS) - Pydantic Schemas
================================================
Schemas for queries, users, partners, payments, and notes
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from enum import Enum
import re


# ============================================================================
# ENUMS
# ============================================================================

class QueryStatus(str, Enum):
    """Query status enum"""
    NEW = "new"
    UNDER_REVIEW = "under_review"
    ASSIGNED = "assigned"
    CONSULTATION_DONE = "consultation_done"
    BRIEF_SHARED = "brief_shared"
    IN_PROGRESS = "in_progress"
    SAMPLE_READY = "sample_ready"
    REVISION = "revision"
    COMPLETED = "completed"
    ON_HOLD = "on_hold"
    CANCELLED = "cancelled"


class QueryPriority(str, Enum):
    """Query priority enum"""
    URGENT = "urgent"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class PartnerType(str, Enum):
    """Partner type enum"""
    INDEPENDENT_CONSULTANT = "independent_consultant"
    MANUFACTURER = "manufacturer"
    CONTRACT_LAB = "contract_lab"


class PartnerStatus(str, Enum):
    """Partner status enum"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class NoteRole(str, Enum):
    """Note author role enum"""
    ADMIN = "admin"
    PARTNER = "partner"
    USER = "user"


class PaymentStatus(str, Enum):
    """Payment status enum"""
    CREATED = "created"
    CAPTURED = "paid"  # Label "paid" for API response (successful payment)
    FAILED = "failed"
    REFUNDED = "refunded"


# ============================================================================
# USER SCHEMAS
# ============================================================================

class UserBase(BaseModel):
    """Base user schema"""
    name: str = Field(..., description="Full name of the user")
    email: Optional[str] = Field(None, description="Email address (optional)")
    phone: str = Field(..., description="Phone with country code (+91...)")
    city: Optional[str] = Field(None, description="User city")
    background: Optional[str] = Field(None, description="User background / entrepreneurial context")
    preferred_batch: Optional[str] = Field(None, description="Preferred batch size range")
    source: str = Field("make_a_wish", description="Acquisition source")
    
    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        """Validate email format if provided"""
        if v is None or v == "":
            return None
        # Simple email regex validation (doesn't require email-validator package)
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, v):
            raise ValueError(f"Invalid email format: {v}")
        return v


class UserCreate(UserBase):
    """Schema for creating a user"""
    pass


class UserResponse(UserBase):
    """Schema for user response"""
    id: str = Field(..., alias="_id")
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True


# ============================================================================
# PARTNER SCHEMAS
# ============================================================================

class PartnerBase(BaseModel):
    """Base partner schema"""
    name: str = Field(..., description="Full name or firm name")
    email: str = Field(..., description="Login email")
    phone: str = Field(..., description="Contact phone")
    type: PartnerType = Field(..., description="Partner type")
    city: Optional[str] = Field(None, description="City of operation")
    experience: Optional[str] = Field(None, description="Years of experience")
    specializations: List[str] = Field(default_factory=list, description="Specialization tags")
    bio: Optional[str] = Field(None, description="Professional bio")
    notes: Optional[str] = Field(None, description="Internal admin notes")
    rating: float = Field(0.0, ge=0.0, le=5.0, description="Rating (0.0-5.0)")
    status: PartnerStatus = Field(PartnerStatus.ACTIVE, description="Partner status")
    
    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        """Validate email format"""
        if not v:
            raise ValueError("Email is required")
        # Simple email regex validation (doesn't require email-validator package)
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, v):
            raise ValueError(f"Invalid email format: {v}")
        return v


class PartnerCreate(PartnerBase):
    """Schema for creating a partner"""
    pass


class PartnerResponse(PartnerBase):
    """Schema for partner response"""
    id: str = Field(..., alias="_id")
    display_id: str = Field(..., description="Human-readable ID (P001, P002...)")
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True


class PartnerListResponse(BaseModel):
    """Schema for partner list response"""
    id: str = Field(..., alias="_id")
    display_id: str
    name: str
    email: str
    type: PartnerType
    city: Optional[str]
    status: PartnerStatus
    rating: float
    active_queries_count: int = 0
    completed_queries_count: int = 0

    class Config:
        populate_by_name = True


# ============================================================================
# PAYMENT SCHEMAS
# ============================================================================

class PaymentBase(BaseModel):
    """Base payment schema"""
    user_id: str = Field(..., description="The paying user")
    razorpay_order_id: Optional[str] = Field(None, description="Razorpay order ID")
    razorpay_payment_id: Optional[str] = Field(None, description="Razorpay payment ID")
    razorpay_signature: Optional[str] = Field(None, description="Payment signature")
    amount: int = Field(..., description="Amount in paise (500000 = ₹5,000)")
    currency: str = Field("INR", description="Currency")
    status: PaymentStatus = Field(..., description="Payment status")
    method: Optional[str] = Field(None, description="Payment method")
    refund_id: Optional[str] = Field(None, description="Razorpay refund ID")
    refund_reason: Optional[str] = Field(None, description="Reason for refund")


class PaymentCreate(PaymentBase):
    """Schema for creating a payment"""
    pass


class PaymentResponse(PaymentBase):
    """Schema for payment response"""
    id: str = Field(..., alias="_id")
    created_at: datetime

    class Config:
        populate_by_name = True


# ============================================================================
# QUERY SCHEMAS
# ============================================================================

class QueryBase(BaseModel):
    """Base query schema with form fields from get this made form"""
    user_id: str = Field(..., description="The customer who requested the formula")
    formula_id: str = Field(..., description="Formula ID")
    wish_id: str = Field(..., description="Wish history ID (alias for history_id)")
    formula_name: str = Field(..., description="Formula name")
    experience_level: str = Field(..., description="Experience level: 'dreaming', 'researching', 'ready', or 'existing'")
    timeline: str = Field(..., description="Timeline: 'asap', '3months', '6months', or 'exploring'")
    quantity_interest: Optional[str] = Field(None, description="Quantity interest")
    additional_notes: Optional[str] = Field(None, description="Additional notes from form")
    status: QueryStatus = Field(QueryStatus.NEW, description="Query status")


class QueryCreate(QueryBase):
    """Schema for creating a query"""
    pass


class QueryResponse(QueryBase):
    """Schema for query response"""
    id: str = Field(..., alias="_id")
    display_id: str = Field(..., description="Human-readable ID (QRY-2025-001)")
    queue_number: Optional[int] = Field(None, description="Queue number assigned to the query")
    user_id: Optional[str] = Field(None, description="Customer user ID (optional in response)")
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True


class UserInfo(BaseModel):
    """User information embedded in query response"""
    fullname: str = Field(..., description="User full name")
    phone: str = Field(..., description="User phone number")
    city: Optional[str] = Field(None, description="User city")
    pincode: Optional[str] = Field(None, description="User pincode")


class QueryListResponse(BaseModel):
    """Schema for query list item (simplified for current requirements)"""
    id: str = Field(..., alias="_id")
    display_id: str
    queue_number: Optional[int] = Field(None, description="Queue number assigned to the query")
    formula_name: str
    user_name: Optional[str] = None
    user_city: Optional[str] = None
    product_type: str
    category: str
    status: QueryStatus
    created_at: datetime

    class Config:
        populate_by_name = True


class QueryDetailResponse(QueryResponse):
    """Schema for detailed query response"""
    user: Optional[UserInfo] = Field(None, description="User information from main user table")
    partner: Optional[PartnerResponse] = None
    payment: Optional[PaymentResponse] = None
    # notes: List["NoteResponse"] = Field(default_factory=list)


class QueryStatusUpdateRequest(BaseModel):
    """Schema for updating query status"""
    status: QueryStatus = Field(..., description="New status")

# TODO: These schemas are for future features (partner assignment, priority) - not needed for current requirements
# class QueryAssignRequest(BaseModel):
#     """Schema for assigning a partner to a query"""
#     partner_id: str = Field(..., description="Partner ID to assign")
#
# class QueryPriorityUpdateRequest(BaseModel):
#     """Schema for updating query priority"""
#     priority: QueryPriority = Field(..., description="New priority")
#
# class QueryReassignRequest(BaseModel):
#     """Schema for reassigning a query"""
#     partner_id: str = Field(..., description="New partner ID")
#     reason: Optional[str] = Field(None, description="Reason for reassignment")


class RefundRequest(BaseModel):
    """Schema for processing refund after consultation call"""
    refund_reason: Optional[str] = Field(None, description="Reason for refund (default: Consultation call completed)")


# ============================================================================
# NOTE SCHEMAS
# ============================================================================

class NoteBase(BaseModel):
    """Base note schema"""
    query_id: str = Field(..., description="Parent query")
    content: str = Field(..., max_length=5000, description="Note content")
    attachments: List[Dict[str, Any]] = Field(default_factory=list, description="File attachments")
    is_internal: bool = Field(False, description="If true, only visible to admin")


class NoteCreate(NoteBase):
    """Schema for creating a note"""
    pass


class NoteResponse(NoteBase):
    """Schema for note response"""
    id: str = Field(..., alias="_id")
    author_id: str = Field(..., description="User, Partner, or Admin UUID")
    author_role: NoteRole = Field(..., description="Author role")
    author_name: str = Field(..., description="Denormalized display name")
    created_at: datetime
    deleted_at: Optional[datetime] = None

    class Config:
        populate_by_name = True


# ============================================================================
# FILTER & PAGINATION SCHEMAS
# ============================================================================

class QueryFilters(BaseModel):
    """Schema for query list filters (simplified - priority and partner_id removed)"""
    status: Optional[QueryStatus] = None
    user_id: Optional[str] = None
    search: Optional[str] = Field(None, description="Search in formula name, user name")
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    page: int = Field(1, ge=1)
    limit: int = Field(20, ge=1, le=100)


class PaginatedResponse(BaseModel):
    """Generic paginated response"""
    page: int
    limit: int
    total: int
    total_pages: int


class QueryListPaginatedResponse(PaginatedResponse):
    """Paginated query list response"""
    queries: List[QueryListResponse]


# ============================================================================
# DASHBOARD STATS SCHEMAS
# ============================================================================

class QueryStatsResponse(BaseModel):
    """Schema for query statistics (simplified)"""
    total_queries: int
    by_status: Dict[str, int]
    revenue: float = Field(..., description="Total revenue in ₹")


# ============================================================================
# UPDATE FORWARD REFERENCES
# ============================================================================

QueryDetailResponse.model_rebuild()

