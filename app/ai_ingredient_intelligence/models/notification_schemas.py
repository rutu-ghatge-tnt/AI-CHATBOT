"""
Notification Module Schemas
===========================

Pydantic models for the notification system that can be used across all features.
Matches the TypeScript interface definitions.
"""

from typing import Optional, Literal, Dict, Any, List
from pydantic import BaseModel, Field
from datetime import datetime


# Notification Module Types
NotificationModule = Literal["compare", "formulation", "market-research", "general", "boards", "make-wish"]

# Notification Types
NotificationType = Literal["loading", "success", "error", "info"]


class NotificationAction(BaseModel):
    """Action that can be performed on a notification"""
    label: str = Field(..., description="Action button label")
    kind: Literal["route", "callback"] = Field(..., description="Action type: route or callback")
    to: Optional[str] = Field(None, description="Route path (required if kind is 'route')")
    onClick: Optional[str] = Field(None, description="Callback function name (required if kind is 'callback')")


class NotificationItem(BaseModel):
    """Notification item matching the TypeScript interface"""
    id: str = Field(..., description="Unique notification ID")
    module: NotificationModule = Field(..., description="Module that generated the notification")
    type: NotificationType = Field(..., description="Notification type: loading, success, error, or info")
    title: str = Field(..., description="Notification title")
    message: Optional[str] = Field(None, description="Optional notification message")
    createdAt: int = Field(..., description="Unix timestamp in milliseconds")
    dismissible: bool = Field(True, description="Whether the notification can be dismissed")
    read: bool = Field(False, description="Whether the notification has been read")
    action: Optional[NotificationAction] = Field(None, description="Optional action button")
    meta: Optional[Dict[str, Any]] = Field(None, description="Optional metadata")
    userId: Optional[str] = Field(None, description="User ID (for backward compatibility)")


class CreateNotificationRequest(BaseModel):
    """Request model for creating a notification"""
    module: NotificationModule
    type: NotificationType
    title: str
    message: Optional[str] = None
    dismissible: bool = True
    action: Optional[NotificationAction] = None
    meta: Optional[Dict[str, Any]] = None


class NotificationResponse(BaseModel):
    """Response model for notification operations"""
    success: bool
    notification: Optional[NotificationItem] = None
    message: Optional[str] = None


class NotificationListResponse(BaseModel):
    """Response model for listing notifications"""
    notifications: List[NotificationItem]
    total: int
    unread_count: int


class MarkReadRequest(BaseModel):
    """Request model for marking notifications as read"""
    notification_ids: List[str] = Field(..., description="List of notification IDs to mark as read")


class DismissNotificationRequest(BaseModel):
    """Request model for dismissing a notification"""
    notification_id: str = Field(..., description="Notification ID to dismiss")

