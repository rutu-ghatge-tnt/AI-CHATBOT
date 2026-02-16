"""
WebSocket Routes
================

Real-time notification endpoints using WebSocket.

Routes:
- GET /ws/{user_id} - WebSocket connection endpoint for real-time notifications
"""

import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.ai_ingredient_intelligence.logic.websocket_manager import get_websocket_manager
from app.ai_ingredient_intelligence.auth import verify_jwt_token

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket"])

# Security scheme for WebSocket (optional - can use query params or headers)
security = HTTPBearer(auto_error=False)


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: str
):
    """
    WebSocket endpoint for real-time notifications.
    
    Connects a user's WebSocket and keeps the connection alive.
    Sends periodic ping messages to keep the connection active.
    
    Args:
        websocket: WebSocket connection
        user_id: User identifier (should match authenticated user)
        
    Note:
        In production, you may want to verify the user_id matches
        the authenticated user from a token or session.
    """
    websocket_manager = get_websocket_manager()
    
    # Accept the WebSocket connection
    try:
        await websocket.accept()
        logger.info(f"🔌 WebSocket connection accepted for user: {user_id}")
    except Exception as e:
        logger.error(f"❌ Error accepting WebSocket connection: {e}")
        return
    
    # Register the connection
    connected = await websocket_manager.connect(user_id, websocket)
    if not connected:
        logger.error(f"❌ Failed to register WebSocket connection for user: {user_id}")
        try:
            await websocket.close()
        except:
            pass
        return
    
    # Keep-alive loop
    try:
        while True:
            # Wait for messages from client (ping/pong or other messages)
            try:
                # Set a timeout to periodically send keep-alive
                import asyncio
                
                # Wait for message with timeout
                try:
                    data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                    
                    # Handle incoming messages (e.g., ping/pong)
                    if data == "ping":
                        await websocket.send_text("pong")
                    elif data == "pong":
                        # Client responded to our ping
                        pass
                    else:
                        # Handle other messages if needed
                        logger.debug(f"Received message from user {user_id}: {data}")
                        
                except asyncio.TimeoutError:
                    # Send keep-alive ping
                    try:
                        await websocket.send_json({"type": "ping"})
                    except Exception as e:
                        logger.warning(f"Failed to send ping to user {user_id}: {e}")
                        break
                        
            except WebSocketDisconnect:
                logger.info(f"🔌 WebSocket disconnected by client for user: {user_id}")
                break
            except Exception as e:
                logger.error(f"❌ Error in WebSocket loop for user {user_id}: {e}")
                break
                
    except Exception as e:
        logger.error(f"❌ Unexpected error in WebSocket endpoint for user {user_id}: {e}")
    finally:
        # Clean up: disconnect the WebSocket
        try:
            await websocket_manager.disconnect(user_id, websocket)
        except Exception as e:
            logger.error(f"❌ Error disconnecting WebSocket for user {user_id}: {e}")
        
        try:
            await websocket.close()
        except:
            pass
        
        logger.info(f"🧹 WebSocket connection cleaned up for user: {user_id}")


