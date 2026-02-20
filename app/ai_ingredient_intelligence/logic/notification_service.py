"""
Notification Service
====================

Service for managing notifications across all features.
Handles creation, storage, retrieval, and WebSocket delivery of notifications.
"""

import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone
from bson import ObjectId
import uuid

from app.ai_ingredient_intelligence.db.collections import notifications_col
from app.ai_ingredient_intelligence.models.notification_schemas import (
    NotificationItem,
    NotificationModule,
    NotificationType,
    NotificationAction,
    CreateNotificationRequest
)
from app.ai_ingredient_intelligence.logic.websocket_manager import get_websocket_manager

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for managing notifications"""
    
    @staticmethod
    async def create_notification(
        user_id: str,
        request: CreateNotificationRequest,
        send_websocket: bool = True
    ) -> NotificationItem:
        """
        Create a new notification and optionally send it via WebSocket.
        
        Args:
            user_id: User ID for the notification
            request: Notification creation request
            send_websocket: Whether to send the notification via WebSocket immediately
            
        Returns:
            Created notification item
        """
        # Generate unique ID
        notification_id = str(uuid.uuid4())
        
        # Get current timestamp in milliseconds
        created_at = int(datetime.now(timezone.utc).timestamp() * 1000)
        
        # Create notification item
        notification = NotificationItem(
            id=notification_id,
            module=request.module,
            type=request.type,
            title=request.title,
            message=request.message,
            createdAt=created_at,
            dismissible=request.dismissible,
            read=False,
            action=request.action,
            meta=request.meta,
            userId=user_id
        )
        
        # Store in database
        notification_dict = notification.model_dump()
        notification_dict["_id"] = notification_id
        notification_dict["user_id"] = user_id  # Store user_id for querying
        
        try:
            await notifications_col.insert_one(notification_dict)
            logger.info(f"✅ Notification created: {notification_id} for user {user_id}")
        except Exception as e:
            logger.error(f"❌ Error storing notification: {e}")
            raise
        
        # Send via WebSocket if requested
        if send_websocket:
            try:
                websocket_manager = get_websocket_manager()
                await websocket_manager.send_to_user(user_id, {
                    "type": "notification",
                    "notification": notification.model_dump()
                })
                logger.info(f"✅ Notification sent via WebSocket: {notification_id}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to send notification via WebSocket: {e}")
                # Don't fail if WebSocket fails - notification is still stored
        
        return notification
    
    @staticmethod
    async def get_user_notifications(
        user_id: str,
        module: Optional[NotificationModule] = None,
        unread_only: bool = False,
        limit: int = 50,
        skip: int = 0
    ) -> Tuple[List[NotificationItem], int, int]:
        """
        Get notifications for a user.
        
        Args:
            user_id: User ID
            module: Optional module filter
            unread_only: Whether to return only unread notifications
            limit: Maximum number of notifications to return
            skip: Number of notifications to skip (for pagination)
            
        Returns:
            Tuple of (notifications list, total count, unread count)
        """
        # Build query
        query: Dict[str, Any] = {"user_id": user_id}
        
        if module:
            query["module"] = module
        
        if unread_only:
            query["read"] = False
        
        try:
            # Get total count
            total_count = await notifications_col.count_documents(query)
            
            # Get unread count
            unread_query = query.copy()
            unread_query["read"] = False
            unread_count = await notifications_col.count_documents(unread_query)
            
            # Get notifications
            cursor = notifications_col.find(query).sort("createdAt", -1).skip(skip).limit(limit)
            notifications = []
            
            async for doc in cursor:
                # Remove MongoDB _id and convert to NotificationItem
                doc.pop("_id", None)
                doc.pop("user_id", None)  # Remove internal user_id field
                notification = NotificationItem(**doc)
                notifications.append(notification)
            
            return notifications, total_count, unread_count
            
        except Exception as e:
            logger.error(f"❌ Error fetching notifications: {e}")
            raise
    
    @staticmethod
    async def get_notification(notification_id: str, user_id: str) -> Optional[NotificationItem]:
        """
        Get a specific notification by ID.
        
        Args:
            notification_id: Notification ID
            user_id: User ID (for security)
            
        Returns:
            Notification item or None if not found
        """
        try:
            doc = await notifications_col.find_one({
                "id": notification_id,
                "user_id": user_id
            })
            
            if not doc:
                return None
            
            doc.pop("_id", None)
            doc.pop("user_id", None)
            return NotificationItem(**doc)
            
        except Exception as e:
            logger.error(f"❌ Error fetching notification: {e}")
            raise
    
    @staticmethod
    async def mark_as_read(notification_ids: List[str], user_id: str) -> int:
        """
        Mark notifications as read.
        
        Args:
            notification_ids: List of notification IDs to mark as read
            user_id: User ID (for security)
            
        Returns:
            Number of notifications marked as read
        """
        try:
            result = await notifications_col.update_many(
                {
                    "id": {"$in": notification_ids},
                    "user_id": user_id,
                    "read": False
                },
                {
                    "$set": {
                        "read": True,
                        "readAt": int(datetime.now(timezone.utc).timestamp() * 1000)
                    }
                }
            )
            
            logger.info(f"✅ Marked {result.modified_count} notifications as read for user {user_id}")
            return result.modified_count
            
        except Exception as e:
            logger.error(f"❌ Error marking notifications as read: {e}")
            raise
    
    @staticmethod
    async def mark_all_as_read(user_id: str, module: Optional[NotificationModule] = None) -> int:
        """
        Mark all notifications as read for a user.
        
        Args:
            user_id: User ID
            module: Optional module filter
            
        Returns:
            Number of notifications marked as read
        """
        query: Dict[str, Any] = {
            "user_id": user_id,
            "read": False
        }
        
        if module:
            query["module"] = module
        
        try:
            result = await notifications_col.update_many(
                query,
                {
                    "$set": {
                        "read": True,
                        "readAt": int(datetime.now(timezone.utc).timestamp() * 1000)
                    }
                }
            )
            
            logger.info(f"✅ Marked {result.modified_count} notifications as read for user {user_id}")
            return result.modified_count
            
        except Exception as e:
            logger.error(f"❌ Error marking all notifications as read: {e}")
            raise
    
    @staticmethod
    async def dismiss_notification(notification_id: str, user_id: str) -> bool:
        """
        Dismiss (delete) a notification.
        
        Args:
            notification_id: Notification ID
            user_id: User ID (for security)
            
        Returns:
            True if notification was dismissed, False if not found
        """
        try:
            result = await notifications_col.delete_one({
                "id": notification_id,
                "user_id": user_id
            })
            
            if result.deleted_count > 0:
                logger.info(f"✅ Notification dismissed: {notification_id}")
                return True
            else:
                logger.warning(f"⚠️ Notification not found or already dismissed: {notification_id}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error dismissing notification: {e}")
            raise
    
    @staticmethod
    async def send_notification(
        user_id: str,
        module: NotificationModule,
        notification_type: NotificationType,
        title: str,
        message: Optional[str] = None,
        dismissible: bool = True,
        action: Optional[NotificationAction] = None,
        meta: Optional[Dict[str, Any]] = None,
        send_websocket: bool = True
    ) -> NotificationItem:
        """
        Convenience method to create and send a notification.
        
        Args:
            user_id: User ID
            module: Notification module
            notification_type: Notification type
            title: Notification title
            message: Optional message
            dismissible: Whether notification can be dismissed
            action: Optional action
            meta: Optional metadata
            send_websocket: Whether to send via WebSocket
            
        Returns:
            Created notification item
        """
        request = CreateNotificationRequest(
            module=module,
            type=notification_type,
            title=title,
            message=message,
            dismissible=dismissible,
            action=action,
            meta=meta
        )
        
        return await NotificationService.create_notification(
            user_id=user_id,
            request=request,
            send_websocket=send_websocket
        )


# Convenience function for backward compatibility
async def notify_user_enhanced(
    user_id: str,
    module: NotificationModule,
    notification_type: NotificationType,
    title: str,
    message: Optional[str] = None,
    dismissible: bool = True,
    action: Optional[NotificationAction] = None,
    meta: Optional[Dict[str, Any]] = None
) -> NotificationItem:
    """
    Enhanced notification function that creates and stores notifications.
    This is the recommended way to send notifications.
    
    Args:
        user_id: User ID
        module: Notification module (e.g., "make-wish", "compare", "formulation")
        notification_type: Type of notification ("loading", "success", "error", "info")
        title: Notification title
        message: Optional message
        dismissible: Whether notification can be dismissed
        action: Optional action button
        meta: Optional metadata
        
    Returns:
        Created notification item
        
    Example:
        await notify_user_enhanced(
            user_id="user123",
            module="make-wish",
            notification_type="success",
            title="Formula Generated",
            message="Your formula is ready!",
            action=NotificationAction(
                label="View Formula",
                kind="route",
                to="/formulas/abc123"
            ),
            meta={"history_id": "abc123"}
        )
    """
    return await NotificationService.send_notification(
        user_id=user_id,
        module=module,
        notification_type=notification_type,
        title=title,
        message=message,
        dismissible=dismissible,
        action=action,
        meta=meta,
        send_websocket=True
    )

