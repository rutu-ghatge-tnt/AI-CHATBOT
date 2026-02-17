"""
Notification API Endpoints
==========================

API endpoints for managing notifications across all features.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, List
from app.ai_ingredient_intelligence.auth import verify_jwt_token
from app.ai_ingredient_intelligence.models.notification_schemas import (
    NotificationItem,
    NotificationListResponse,
    NotificationResponse,
    CreateNotificationRequest,
    MarkReadRequest,
    DismissNotificationRequest,
    NotificationModule,
    NotificationType
)
from app.ai_ingredient_intelligence.logic.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.post("", response_model=NotificationResponse)
async def create_notification(
    request: CreateNotificationRequest,
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Create a new notification for the current user.
    
    This endpoint allows creating notifications programmatically.
    Most features should use the notification service directly.
    """
    try:
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="User ID not found")
        
        notification = await NotificationService.create_notification(
            user_id=str(user_id),
            request=request,
            send_websocket=True
        )
        
        return NotificationResponse(
            success=True,
            notification=notification,
            message="Notification created successfully"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create notification: {str(e)}"
        )


@router.get("", response_model=NotificationListResponse)
async def get_notifications(
    module: Optional[NotificationModule] = Query(None, description="Filter by module"),
    unread_only: bool = Query(False, description="Return only unread notifications"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of notifications"),
    skip: int = Query(0, ge=0, description="Number of notifications to skip"),
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Get notifications for the current user.
    
    Supports filtering by module and unread status, with pagination.
    """
    try:
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="User ID not found")
        
        notifications, total, unread_count = await NotificationService.get_user_notifications(
            user_id=str(user_id),
            module=module,
            unread_only=unread_only,
            limit=limit,
            skip=skip
        )
        
        return NotificationListResponse(
            notifications=notifications,
            total=total,
            unread_count=unread_count
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch notifications: {str(e)}"
        )


@router.get("/{notification_id}", response_model=NotificationResponse)
async def get_notification(
    notification_id: str,
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Get a specific notification by ID.
    """
    try:
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="User ID not found")
        
        notification = await NotificationService.get_notification(
            notification_id=notification_id,
            user_id=str(user_id)
        )
        
        if not notification:
            raise HTTPException(status_code=404, detail="Notification not found")
        
        return NotificationResponse(
            success=True,
            notification=notification
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch notification: {str(e)}"
        )


@router.post("/mark-read", response_model=NotificationResponse)
async def mark_notifications_as_read(
    request: MarkReadRequest,
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Mark one or more notifications as read.
    """
    try:
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="User ID not found")
        
        count = await NotificationService.mark_as_read(
            notification_ids=request.notification_ids,
            user_id=str(user_id)
        )
        
        return NotificationResponse(
            success=True,
            message=f"Marked {count} notification(s) as read"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to mark notifications as read: {str(e)}"
        )


@router.post("/mark-all-read", response_model=NotificationResponse)
async def mark_all_notifications_as_read(
    module: Optional[NotificationModule] = Query(None, description="Filter by module"),
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Mark all notifications as read for the current user.
    Optionally filter by module.
    """
    try:
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="User ID not found")
        
        count = await NotificationService.mark_all_as_read(
            user_id=str(user_id),
            module=module
        )
        
        return NotificationResponse(
            success=True,
            message=f"Marked {count} notification(s) as read"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to mark all notifications as read: {str(e)}"
        )


@router.delete("/{notification_id}", response_model=NotificationResponse)
async def dismiss_notification(
    notification_id: str,
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Dismiss (delete) a notification.
    """
    try:
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="User ID not found")
        
        success = await NotificationService.dismiss_notification(
            notification_id=notification_id,
            user_id=str(user_id)
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Notification not found")
        
        return NotificationResponse(
            success=True,
            message="Notification dismissed successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to dismiss notification: {str(e)}"
        )

