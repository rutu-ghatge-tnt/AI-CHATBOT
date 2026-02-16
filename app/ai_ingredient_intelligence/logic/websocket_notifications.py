"""
WebSocket Notification Helper
==============================

Helper function for sending real-time notifications via WebSocket.

Usage:
    from app.ai_ingredient_intelligence.logic.websocket_notifications import notify_user
    
    # In a background task or endpoint
    await notify_user(
        user_id="user123",
        title="Task Complete",
        message="Your process finished successfully"
    )
"""

import logging
from typing import Optional, Dict, Any
from app.ai_ingredient_intelligence.logic.websocket_manager import get_websocket_manager

logger = logging.getLogger(__name__)


async def notify_user(
    user_id: str,
    title: str,
    message: str,
    data: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Send a real-time notification to a user via WebSocket.
    
    This function is safe to call even if the user is offline - it will
    simply do nothing without crashing.
    
    Args:
        user_id: Unique identifier for the user
        title: Notification title
        message: Notification message
        data: Optional additional data to include in the notification
        
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
        websocket_manager = get_websocket_manager()
        
        # Prepare notification payload
        notification = {
            "type": "notification",
            "title": title,
            "message": message,
            "timestamp": None  # Will be set by frontend or can add here
        }
        
        # Add optional data
        if data:
            notification["data"] = data
        
        # Send via WebSocket
        success = await websocket_manager.send_to_user(user_id, notification)
        
        if success:
            logger.info(f"✅ Notification sent to user {user_id}: {title}")
        else:
            logger.debug(f"⚠️ User {user_id} is offline, notification not sent")
        
        return success
        
    except Exception as e:
        # Log error but don't crash - notifications are non-critical
        logger.error(f"❌ Error sending notification to user {user_id}: {e}")
        return False


