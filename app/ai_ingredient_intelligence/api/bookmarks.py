"""
Bookmark API Endpoints
======================

API endpoints for bulk bookmark functionality:
- Create bookmarks (one type per request: INGREDIENT, PRODUCT, RECIPE)

Uses JWT authentication (userId from token only). MongoDB backend via
app.ai_ingredient_intelligence.db.collections.bookmarks_col.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.ai_ingredient_intelligence.auth import verify_jwt_token
from app.ai_ingredient_intelligence.logic.bookmark_manager import (
    create_bookmarks as create_bookmarks_logic,
    delete_bookmarks as delete_bookmarks_logic,
    get_bookmarks_for_user,
)
from app.ai_ingredient_intelligence.models.bookmarks_schemas import (
    BookmarkListItem,
    BookmarkReference,
    BookmarkType,
    CreateBookmarksRequest,
    CreateBookmarksResponse,
    DeleteBookmarksRequest,
    DeleteBookmarksResponse,
    ListBookmarksResponse,
)


# ============================================================================
# BOOKMARK ENDPOINTS
# ============================================================================

router = APIRouter(prefix="/bookmarks", tags=["Bookmarks"])


def _get_user_id(current_user: dict) -> str:
    """Extract user_id from JWT payload; raise 400 if missing."""
    user_id = current_user.get("user_id") or current_user.get("_id")
    if not user_id:
        raise HTTPException(
            status_code=400,
            detail="User ID not found in JWT token",
        )
    return str(user_id)


@router.get("")
async def list_bookmarks(
    type: Optional[str] = Query(None, description="Filter by type: INGREDIENT, PRODUCT, RECIPE, URL"),
    limit: int = Query(50, ge=1, le=100, description="Number of results per page"),
    skip: int = Query(0, ge=0, description="Number of results to skip"),
    current_user: dict = Depends(verify_jwt_token),
):
    """
    List your bookmarks with pagination and optional type filter.

    Query parameters:
    - type: Filter by bookmark type (INGREDIENT, PRODUCT, RECIPE, URL). Case-insensitive.
    - limit: Number of results (default: 50, max: 100).
    - skip: Number of results to skip (default: 0).

    Example: GET /api/bookmarks?type=INGREDIENT&limit=20&skip=0
    """
    try:
        user_id = _get_user_id(current_user)
        bookmark_type = None
        if type:
            type_upper = (type or "").strip().upper()
            try:
                bookmark_type = BookmarkType(type_upper)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid type. Use one of: INGREDIENT, PRODUCT, RECIPE, URL",
                )
        data = await get_bookmarks_for_user(
            user_id, bookmark_type=bookmark_type, skip=skip, limit=limit
        )
        items = []
        for doc in data["items"]:
            ref = doc.get("reference") or {}
            t = doc.get("type") or ""
            tags = ref.get("tags") if isinstance(ref.get("tags"), list) else []
            if (t or "").upper() == "URL":
                reference = BookmarkReference(title=ref.get("title"), url=ref.get("url"), tags=tags)
            else:
                reference = BookmarkReference(id=ref.get("id"), name=ref.get("name"), tags=tags)
            items.append(
                BookmarkListItem(type=t, reference=reference, created_at=doc.get("created_at"))
            )
        result = ListBookmarksResponse(items=items, total=data["total"])
        return result.model_dump(exclude_none=True)
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error listing bookmarks: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=CreateBookmarksResponse)
async def create_bookmarks(
    request: CreateBookmarksRequest,
    current_user: dict = Depends(verify_jwt_token),  # JWT token validation
):
    """
    Create bookmarks in bulk (one type per request).

    Request body:
    - INGREDIENT / PRODUCT / RECIPE: items with id (required), name (optional).
    - URL: items with title and url (required).

    Example (INGREDIENT):
    { "type": "INGREDIENT", "items": [ { "id": "ing_001", "name": "Niacinamide" } ] }

    Example (URL):
    { "type": "URL", "items": [ { "title": "Article", "url": "https://example.com/page" } ] }

    Rules:
    - type is required: INGREDIENT, PRODUCT, RECIPE, or URL.
    - For INGREDIENT/PRODUCT/RECIPE each item must have id; name is optional.
    - For URL each item must have title and url.
    - Duplicate IDs in the request are removed.
    - Already existing bookmarks are ignored (no error).
    - Response includes added, alreadyBookmarked, and failed lists.

    Returns:
    {
        "success": true,
        "message": "Bookmarks processed successfully",
        "data": {
            "type": "INGREDIENT",
            "added": ["ing_001", "ing_002"],
            "alreadyBookmarked": ["ing_003"],
            "failed": []
        }
    }

    Authentication:
    - Requires JWT token in Authorization header.
    - User ID is extracted from the token only (do not send userId in body).
    """
    try:
        user_id = _get_user_id(current_user)
        data = await create_bookmarks_logic(
            user_id=user_id,
            bookmark_type=request.type,
            items=request.items,
        )
        return CreateBookmarksResponse(
            success=True,
            message="Bookmarks processed successfully",
            data=data,
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating bookmarks: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create bookmarks: {str(e)}",
        )


@router.delete("", response_model=DeleteBookmarksResponse)
async def delete_bookmarks(
    request: DeleteBookmarksRequest,
    current_user: dict = Depends(verify_jwt_token),
):
    """
    Delete bookmarks in bulk (one type per request).

    Request body:
    - type: INGREDIENT, PRODUCT, RECIPE, or URL.
    - items: For INGREDIENT/PRODUCT/RECIPE each item must have "id". For URL each item must have "url".

    Example (INGREDIENT):
    { "type": "INGREDIENT", "items": [ { "id": "ing_001" }, { "id": "ing_002" } ] }

    Example (URL):
    { "type": "URL", "items": [ { "url": "https://example.com/page" } ] }

    Response:
    - deleted: IDs/URLs that were removed.
    - notFound: IDs/URLs that were not bookmarked (no error).
    - failed: IDs/URLs that could not be deleted (e.g. DB error).

    Authentication: JWT required; user_id from token only.
    """
    try:
        user_id = _get_user_id(current_user)
        data = await delete_bookmarks_logic(
            user_id=user_id,
            bookmark_type=request.type,
            items=request.items,
        )
        return DeleteBookmarksResponse(
            success=True,
            message="Bookmarks delete processed successfully",
            data=data,
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting bookmarks: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete bookmarks: {str(e)}",
        )
