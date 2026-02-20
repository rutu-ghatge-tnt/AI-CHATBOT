"""
WebSocket Notification Helper
==============================

Helper functions for sending real-time notifications via WebSocket.

This module provides backward-compatible functions and also integrates with
the new notification service for full-featured notifications.

Usage:
    # Simple notification (backward compatible)
    from app.ai_ingredient_intelligence.logic.websocket_notifications import notify_user
    
    await notify_user(
        user_id="user123",
        title="Task Complete",
        message="Your process finished successfully"
    )
    
    # Enhanced notification with full features (recommended)
    from app.ai_ingredient_intelligence.logic.websocket_notifications import notify_user_enhanced
    from app.ai_ingredient_intelligence.models.notification_schemas import NotificationAction
    
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
        )
    )
"""

import logging
from typing import Optional, Dict, Any
from app.ai_ingredient_intelligence.logic.websocket_manager import get_websocket_manager
from app.ai_ingredient_intelligence.logic.notification_service import (
    NotificationService,
    notify_user_enhanced as _notify_user_enhanced
)
from app.ai_ingredient_intelligence.models.notification_schemas import (
    NotificationModule,
    NotificationType,
    NotificationAction
)

logger = logging.getLogger(__name__)


async def notify_user(
    user_id: str,
    title: str,
    message: str,
    data: Optional[Dict[str, Any]] = None,
    module: NotificationModule = "general"
) -> bool:
    """
    Send a real-time notification to a user via WebSocket.
    
    This function is backward compatible with the old implementation.
    For new code, use notify_user_enhanced() instead.
    
    This function is safe to call even if the user is offline - it will
    simply do nothing without crashing.
    
    Args:
        user_id: Unique identifier for the user
        title: Notification title
        message: Notification message
        data: Optional additional data to include in the notification
        module: Notification module (defaults to "general" for backward compatibility)
        
    Returns:
        True if notification was sent, False if user is offline or error occurred
        
    Example:
        await notify_user(
            user_id="user123",
            title="Formula Generated",
            message="Your formula is ready!",
            data={"history_id": "abc123", "status": "completed"}
        )
    """
    try:
        # Determine notification type from data if available
        notification_type: NotificationType = "info"
        if data:
            if data.get("status") == "completed":
                notification_type = "success"
            elif data.get("status") == "error" or data.get("error"):
                notification_type = "error"
            elif data.get("status") == "processing":
                notification_type = "loading"
        
        # Create action if data contains route information
        action: Optional[NotificationAction] = None
        if data and data.get("history_id"):
            # Try to determine route based on module
            route_path = None
            if module == "make-wish":
                route_path = f"/make-wish/{data.get('history_id')}"
            elif module == "compare":
                route_path = f"/compare/{data.get('history_id')}"
            elif module == "market-research":
                route_path = f"/market-research/{data.get('history_id')}"
            elif module == "formulation":
                route_path = f"/formulation/{data.get('history_id')}"
            
            if route_path:
                action = NotificationAction(
                    label="View",
                    kind="route",
                    to=route_path
                )
        
        # Use enhanced notification service
        await _notify_user_enhanced(
            user_id=user_id,
            module=module,
            notification_type=notification_type,
            title=title,
            message=message,
            action=action,
            meta=data
        )
        
        return True
        
    except Exception as e:
        # Log error but don't crash - notifications are non-critical
        logger.error(f"❌ Error sending notification to user {user_id}: {e}")
        return False


# Re-export the enhanced notification function
notify_user_enhanced = _notify_user_enhanced
