"""
Pydantic schemas for Bookmark API.

Bulk bookmark: one type per request.
- INGREDIENT / PRODUCT / RECIPE: items have id, name (optional).
- URL: items have title, url.
"""

import enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ============================================================================
# ENUM
# ============================================================================

class BookmarkType(str, enum.Enum):
    INGREDIENT = "INGREDIENT"
    PRODUCT = "PRODUCT"
    RECIPE = "RECIPE"
    URL = "URL"


# ============================================================================
# REQUEST / RESPONSE SCHEMAS
# ============================================================================

class BookmarkItemInput(BaseModel):
    """
    Single item in bulk bookmark request.
    - For INGREDIENT / PRODUCT / RECIPE: provide id (required), name (optional).
    - For URL: provide title and url (required).
    - tags: optional list of strings for all types.
    """
    id: Optional[str] = Field(None, description="Item ID (for INGREDIENT, PRODUCT, RECIPE)")
    name: Optional[str] = Field(None, description="Display name (for INGREDIENT, PRODUCT, RECIPE)")
    title: Optional[str] = Field(None, description="Title (for URL type)")
    url: Optional[str] = Field(None, description="URL (for URL type)")
    tags: Optional[List[str]] = Field(default_factory=list, description="Tags for this bookmark (all types)")

    @field_validator("id", "name", "title", "url")
    @classmethod
    def strip_strings(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = v.strip() if isinstance(v, str) else str(v).strip()
        return s if s else None

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, v: Optional[List[str]]) -> List[str]:
        if v is None:
            return []
        return [str(x).strip() for x in v if x and str(x).strip()]


class CreateBookmarksRequest(BaseModel):
    """Request to create bookmarks in bulk (one type per request)."""
    type: BookmarkType = Field(..., description="Bookmark type: INGREDIENT, PRODUCT, RECIPE, or URL")
    items: List[BookmarkItemInput] = Field(..., min_length=1, description="Non-empty list of items")

    @model_validator(mode="after")
    def items_match_type(self):
        t = self.type
        for i, item in enumerate(self.items):
            if t in (BookmarkType.INGREDIENT, BookmarkType.PRODUCT, BookmarkType.RECIPE):
                if not item.id or not str(item.id).strip():
                    raise ValueError(f"items[{i}]: 'id' is required for type {t.value}")
            elif t == BookmarkType.URL:
                if not item.title or not str(item.title).strip():
                    raise ValueError(f"items[{i}]: 'title' is required for type URL")
                if not item.url or not str(item.url).strip():
                    raise ValueError(f"items[{i}]: 'url' is required for type URL")
        return self

    @field_validator("items")
    @classmethod
    def items_non_empty(cls, v: List[BookmarkItemInput]) -> List[BookmarkItemInput]:
        if not v or len(v) == 0:
            raise ValueError("items must be a non-empty array")
        return v


class CreateBookmarksData(BaseModel):
    """Result data for bulk create: added, alreadyBookmarked, failed."""
    type: BookmarkType
    added: List[str] = Field(default_factory=list, description="Item IDs/URLs that were added")
    alreadyBookmarked: List[str] = Field(default_factory=list, description="Item IDs/URLs already bookmarked")
    failed: List[str] = Field(default_factory=list, description="Item IDs/URLs that failed to add")


class CreateBookmarksResponse(BaseModel):
    """Success response for POST /bookmarks."""
    success: bool = True
    message: str = "Bookmarks processed successfully"
    data: CreateBookmarksData


# ============================================================================
# BULK DELETE REQUEST / RESPONSE
# ============================================================================

class DeleteBookmarkItemInput(BaseModel):
    """Single item for bulk delete: id for INGREDIENT/PRODUCT/RECIPE, url for URL."""
    id: Optional[str] = Field(None, description="Item ID (for INGREDIENT, PRODUCT, RECIPE)")
    url: Optional[str] = Field(None, description="URL (for URL type)")

    @field_validator("id", "url")
    @classmethod
    def strip_strings(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = v.strip() if isinstance(v, str) else str(v).strip()
        return s if s else None


class DeleteBookmarksRequest(BaseModel):
    """Request to delete bookmarks in bulk (one type per request)."""
    type: BookmarkType = Field(..., description="Bookmark type: INGREDIENT, PRODUCT, RECIPE, or URL")
    items: List[DeleteBookmarkItemInput] = Field(..., min_length=1, description="Non-empty list of items to delete")

    @model_validator(mode="after")
    def items_match_type(self):
        t = self.type
        for i, item in enumerate(self.items):
            if t in (BookmarkType.INGREDIENT, BookmarkType.PRODUCT, BookmarkType.RECIPE):
                if not item.id or not str(item.id).strip():
                    raise ValueError(f"items[{i}]: 'id' is required for type {t.value}")
            elif t == BookmarkType.URL:
                if not item.url or not str(item.url).strip():
                    raise ValueError(f"items[{i}]: 'url' is required for type URL")
        return self

    @field_validator("items")
    @classmethod
    def items_non_empty(cls, v: List[DeleteBookmarkItemInput]) -> List[DeleteBookmarkItemInput]:
        if not v or len(v) == 0:
            raise ValueError("items must be a non-empty array")
        return v


class DeleteBookmarksData(BaseModel):
    """Result data for bulk delete: deleted, notFound, failed."""
    type: BookmarkType
    deleted: List[str] = Field(default_factory=list, description="IDs/URLs that were deleted")
    notFound: List[str] = Field(default_factory=list, description="IDs/URLs that were not bookmarked")
    failed: List[str] = Field(default_factory=list, description="IDs/URLs that failed to delete")


class DeleteBookmarksResponse(BaseModel):
    """Success response for DELETE /bookmarks."""
    success: bool = True
    message: str = "Bookmarks delete processed successfully"
    data: DeleteBookmarksData


# ============================================================================
# LIST (PAGINATED) RESPONSE
# ============================================================================

class BookmarkReference(BaseModel):
    """Reference payload: id+name for INGREDIENT/PRODUCT/RECIPE, title+url for URL, tags for all. Nulls excluded in response."""
    model_config = ConfigDict(serialization_exclude_none=True)
    id: Optional[str] = Field(None, description="Item ID (INGREDIENT, PRODUCT, RECIPE)")
    name: Optional[str] = Field(None, description="Display name (INGREDIENT, PRODUCT, RECIPE)")
    title: Optional[str] = Field(None, description="Title (URL type)")
    url: Optional[str] = Field(None, description="URL (URL type)")
    tags: Optional[List[str]] = Field(default_factory=list, description="Tags (all types)")


class BookmarkListItem(BaseModel):
    """Single bookmark in list response."""
    type: str = Field(..., description="Bookmark type: INGREDIENT, PRODUCT, RECIPE, URL")
    reference: BookmarkReference = Field(..., description="Reference (id/name or title/url)")
    created_at: Optional[str] = Field(None, description="Created at ISO datetime")


class ListBookmarksResponse(BaseModel):
    """Paginated list of bookmarks (GET /bookmarks)."""
    items: List[BookmarkListItem] = Field(default_factory=list, description="Bookmarks for current page")
    total: int = Field(..., description="Total number of bookmarks matching the filter")
