"""
WebSocket Connection Manager
============================

Global service for managing WebSocket connections and real-time notifications.

Features:
- Stores active connections per user_id
- Supports multiple connections per user (multiple tabs/devices)
- Thread-safe connection management
- Graceful disconnect handling
- Broadcast functionality

Usage:
    from app.ai_ingredient_intelligence.logic.websocket_manager import websocket_manager
    
    # Connect a user
    await websocket_manager.connect(user_id, websocket)
    
    # Send notification to user
    await websocket_manager.send_to_user(user_id, {"title": "Hello", "message": "World"})
    
    # Disconnect
    await websocket_manager.disconnect(user_id, websocket)
"""

import json
import logging
from typing import Dict, Set, List
from fastapi import WebSocket, WebSocketDisconnect
import asyncio

logger = logging.getLogger(__name__)


class WebSocketManager:
    """
    Manages WebSocket connections for real-time notifications.
    
    Supports multiple connections per user (e.g., multiple browser tabs).
    Thread-safe and production-ready.
    """
    
    def __init__(self):
        # Map user_id -> Set of WebSocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()
    
    async def connect(self, user_id: str, websocket: WebSocket) -> bool:
        """
        Register a new WebSocket connection for a user.
        
        Args:
            user_id: Unique identifier for the user
            websocket: WebSocket connection instance
            
        Returns:
            True if connection was added, False otherwise
        """
        try:
            async with self._lock:
                if user_id not in self.active_connections:
                    self.active_connections[user_id] = set()
                
                self.active_connections[user_id].add(websocket)
                connection_count = len(self.active_connections[user_id])
                
            logger.info(f"✅ WebSocket connected: user_id={user_id}, total_connections={connection_count}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error connecting WebSocket for user {user_id}: {e}")
            return False
    
    async def disconnect(self, user_id: str, websocket: WebSocket) -> bool:
        """
        Remove a WebSocket connection for a user.
        
        Args:
            user_id: Unique identifier for the user
            websocket: WebSocket connection instance to remove
            
        Returns:
            True if connection was removed, False otherwise
        """
        try:
            async with self._lock:
                if user_id in self.active_connections:
                    self.active_connections[user_id].discard(websocket)
                    
                    # Clean up empty user entries
                    if not self.active_connections[user_id]:
                        del self.active_connections[user_id]
                        logger.info(f"🧹 Removed all connections for user {user_id}")
                    else:
                        remaining = len(self.active_connections[user_id])
                        logger.info(f"🔌 WebSocket disconnected: user_id={user_id}, remaining_connections={remaining}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error disconnecting WebSocket for user {user_id}: {e}")
            return False
    
    async def send_to_user(self, user_id: str, data: dict) -> bool:
        """
        Send data to all active connections for a specific user.
        
        Args:
            user_id: Unique identifier for the user
            data: Dictionary to send as JSON
            
        Returns:
            True if sent to at least one connection, False if user is offline
        """
        if user_id not in self.active_connections:
            logger.debug(f"⚠️ User {user_id} has no active WebSocket connections")
            return False
        
        connections = self.active_connections[user_id].copy()  # Copy to avoid modification during iteration
        if not connections:
            return False
        
        # Prepare JSON message
        try:
            message = json.dumps(data)
        except Exception as e:
            logger.error(f"❌ Error serializing message for user {user_id}: {e}")
            return False
        
        # Send to all connections for this user
        success_count = 0
        failed_connections = []
        
        for websocket in connections:
            try:
                await websocket.send_text(message)
                success_count += 1
            except Exception as e:
                logger.warning(f"⚠️ Failed to send to connection for user {user_id}: {e}")
                failed_connections.append(websocket)
        
        # Clean up failed connections
        if failed_connections:
            async with self._lock:
                for failed_ws in failed_connections:
                    if user_id in self.active_connections:
                        self.active_connections[user_id].discard(failed_ws)
        
        if success_count > 0:
            logger.info(f"✅ Sent notification to user {user_id} ({success_count} connection(s))")
            return True
        else:
            logger.warning(f"⚠️ Failed to send to any connection for user {user_id}")
            return False
    
    async def broadcast(self, data: dict) -> int:
        """
        Broadcast data to all connected users.
        
        Args:
            data: Dictionary to send as JSON
            
        Returns:
            Number of users who received the message
        """
        if not self.active_connections:
            return 0
        
        # Prepare JSON message
        try:
            message = json.dumps(data)
        except Exception as e:
            logger.error(f"❌ Error serializing broadcast message: {e}")
            return 0
        
        # Send to all users
        success_count = 0
        all_user_ids = list(self.active_connections.keys())
        
        for user_id in all_user_ids:
            if await self.send_to_user(user_id, data):
                success_count += 1
        
        logger.info(f"📢 Broadcast sent to {success_count} user(s)")
        return success_count
    
    def is_connected(self, user_id: str) -> bool:
        """
        Check if a user has any active connections.
        
        Args:
            user_id: Unique identifier for the user
            
        Returns:
            True if user has at least one active connection
        """
        return user_id in self.active_connections and len(self.active_connections[user_id]) > 0
    
    def get_connection_count(self, user_id: str) -> int:
        """
        Get the number of active connections for a user.
        
        Args:
            user_id: Unique identifier for the user
            
        Returns:
            Number of active connections
        """
        if user_id not in self.active_connections:
            return 0
        return len(self.active_connections[user_id])
    
    def get_total_users(self) -> int:
        """
        Get the total number of users with active connections.
        
        Returns:
            Number of unique users connected
        """
        return len(self.active_connections)
    
    def get_total_connections(self) -> int:
        """
        Get the total number of active connections across all users.
        
        Returns:
            Total number of connections
        """
        return sum(len(connections) for connections in self.active_connections.values())


# Global singleton instance
_websocket_manager: WebSocketManager = None


def get_websocket_manager() -> WebSocketManager:
    """
    Get the global WebSocket manager instance (singleton pattern).
    
    Returns:
        WebSocketManager instance
    """
    global _websocket_manager
    if _websocket_manager is None:
        _websocket_manager = WebSocketManager()
    return _websocket_manager


# Convenience alias for direct import
websocket_manager = get_websocket_manager()

