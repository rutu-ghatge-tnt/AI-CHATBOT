"""
WebSocket Routes
================

Real-time notification endpoints using WebSocket.

Routes:
- GET /ws/{user_id} - WebSocket connection endpoint for real-time notifications
"""

import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query
from app.ai_ingredient_intelligence.logic.websocket_manager import get_websocket_manager
from app.ai_ingredient_intelligence.auth.jwt_auth import verify_access_token

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: str,
    token: str = Query(None, description="JWT token for authentication (query parameter)")
):
    """
    WebSocket endpoint for real-time notifications.
    
    Connects a user's WebSocket and keeps the connection alive.
    Sends periodic ping messages to keep the connection active.
    
    Authentication:
    - Token can be provided as query parameter: ?token=<jwt_token>
    - Or in Authorization header: Authorization: Bearer <jwt_token>
    - Token is verified before accepting the connection
    - user_id in path must match the authenticated user from token
    
    Args:
        websocket: WebSocket connection
        user_id: User identifier (must match authenticated user from token)
        token: JWT token for authentication (optional query parameter, can also be in header)
    """
    websocket_manager = get_websocket_manager()
    
    # Extract token from query parameter or headers
    auth_token = token
    if not auth_token:
        # Try to get token from Authorization header
        auth_header = websocket.headers.get("Authorization") or websocket.headers.get("authorization")
        if auth_header:
            if auth_header.startswith("Bearer ") or auth_header.startswith("bearer "):
                auth_token = auth_header[7:].strip()
    
    # Verify token before accepting connection
    if not auth_token:
        logger.warning(f"❌ WebSocket connection rejected: No token provided for user {user_id}")
        await websocket.close(code=1008, reason="Authentication required")
        return
    
    try:
        # Verify the JWT token
        payload = verify_access_token(auth_token)
        authenticated_user_id = payload.get("user_id") or payload.get("_id")
        
        # Normalize user_id format (handle ObjectId strings)
        if authenticated_user_id:
            authenticated_user_id = str(authenticated_user_id)
        user_id_normalized = str(user_id)
        
        # Verify user_id matches authenticated user
        if authenticated_user_id != user_id_normalized:
            logger.warning(f"❌ WebSocket auth failed: user_id mismatch. Path: {user_id}, Token: {authenticated_user_id}")
            await websocket.close(code=1008, reason="User ID mismatch")
            return
        
        logger.info(f"✅ WebSocket authentication successful for user: {user_id}")
        
    except Exception as auth_error:
        logger.error(f"❌ WebSocket authentication failed for user {user_id}: {auth_error}")
        await websocket.close(code=1008, reason="Authentication failed")
        return
    
    # Accept the WebSocket connection after authentication
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


