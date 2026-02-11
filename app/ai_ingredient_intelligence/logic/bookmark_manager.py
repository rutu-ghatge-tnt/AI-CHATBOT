"""
Bookmark management logic (MongoDB).

Documents use a `reference` object:
- INGREDIENT | PRODUCT | RECIPE: reference = { id, name }
- URL: reference = { title, url }
"""

from datetime import datetime, timezone, timedelta
from typing import List, Set, Tuple, Optional, Any, Dict

from app.ai_ingredient_intelligence.db.collections import bookmarks_col
from app.ai_ingredient_intelligence.models.bookmarks_schemas import (
    BookmarkType,
    CreateBookmarksData,
    BookmarkItemInput,
)


def _item_id_and_doc(
    user_id: str,
    item: BookmarkItemInput,
    bookmark_type: BookmarkType,
    now: str,
) -> Tuple[str, Dict[str, Any]]:
    """Build (dedupe_key, doc) for one item. Doc uses reference object."""
    base = {
        "user_id": user_id,
        "type": bookmark_type.value,
        "created_at": now,
    }
    if bookmark_type == BookmarkType.URL:
        url = (item.url or "").strip()
        title = (item.title or "").strip()
        doc = {**base, "reference": {"title": title, "url": url}}
        return url, doc
    else:
        # INGREDIENT, PRODUCT, RECIPE
        id_val = (item.id or "").strip()
        name_val = (item.name or "").strip() if item.name else ""
        doc = {**base, "reference": {"id": id_val, "name": name_val}}
        return id_val, doc


def _ref_field(bookmark_type: BookmarkType) -> str:
    """Field in reference used for dedupe: reference.id or reference.url."""
    return "reference.url" if bookmark_type == BookmarkType.URL else "reference.id"


async def find_existing_item_ids(
    user_id: str,
    item_ids: List[str],
    bookmark_type: BookmarkType,
) -> Set[str]:
    """Return set of ids/urls already bookmarked for this user and type (query by reference.id or reference.url)."""
    if not item_ids:
        return set()
    ref_field = _ref_field(bookmark_type)
    cursor = bookmarks_col.find(
        {
            "user_id": user_id,
            "type": bookmark_type.value,
            ref_field: {"$in": item_ids},
        },
        {ref_field: 1},
    )
    existing = set()
    async for doc in cursor:
        val = doc.get("reference", {}).get("url" if bookmark_type == BookmarkType.URL else "id")
        if val:
            existing.add(val)
    return existing


async def add_bookmarks(
    user_id: str,
    docs_to_insert: List[Dict[str, Any]],
    bookmark_type: BookmarkType,
) -> Tuple[List[str], List[str], List[str]]:
    """
    Add bookmarks. Idempotent: existing (user_id, type, reference.id/url) are skipped.
    Docs use reference object; dedupe key is reference.id or reference.url.
    """
    if not docs_to_insert:
        return [], [], []
    ref_field = _ref_field(bookmark_type)
    keys = []
    for d in docs_to_insert:
        ref = d.get("reference") or {}
        k = ref.get("url" if bookmark_type == BookmarkType.URL else "id") or ""
        keys.append(k)
    existing = await find_existing_item_ids(user_id, keys, bookmark_type)
    already_bookmarked = list(existing)
    added: List[str] = []
    failed: List[str] = []
    try:
        result = await bookmarks_col.insert_many(docs_to_insert, ordered=False)
        if result.acknowledged:
            added = [k for k in keys if k not in existing]
            print(f"[BOOKMARKS] Inserted {len(added)} into collection 'bookmarks' (db: {bookmarks_col.database.name})")
        else:
            failed = keys
    except Exception as e:
        import traceback
        print(f"[BOOKMARKS] insert_many error: {e}")
        traceback.print_exc()
        from pymongo.errors import BulkWriteError
        if isinstance(e, BulkWriteError) and e.details.get("writeErrors"):
            failed_indices = {err["index"] for err in e.details["writeErrors"] if err.get("index") is not None}
            failed = [keys[i] for i in failed_indices if 0 <= i < len(keys)]
            added = [k for k in keys if k not in failed and k not in existing]
        else:
            failed = keys
    return added, already_bookmarked, failed


async def get_bookmarks_for_user(
    user_id: str,
    bookmark_type: Optional[BookmarkType] = None,
    skip: int = 0,
    limit: int = 50,
):
    """
    List bookmarks for a user with optional type filter and pagination.
    Returns items (type, reference, created_at) and total count.
    """
    query = {"user_id": user_id}
    if bookmark_type is not None:
        query["type"] = bookmark_type.value
    total = await bookmarks_col.count_documents(query)
    cursor = bookmarks_col.find(
        query,
        {"_id": 0, "type": 1, "reference": 1, "created_at": 1},
    ).sort("created_at", -1).skip(skip).limit(limit)
    items = []
    async for doc in cursor:
        items.append(doc)
    return {"items": items, "total": total}


async def create_bookmarks(
    user_id: str,
    bookmark_type: BookmarkType,
    items: List[BookmarkItemInput],
) -> CreateBookmarksData:
    """
    Process bulk bookmark request: dedupe by reference.id / reference.url, ignore already bookmarked,
    return CreateBookmarksData (added, alreadyBookmarked, failed).
    """
    now = datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()
    seen: Set[str] = set()
    id_doc_list: List[Tuple[str, Dict[str, Any]]] = []
    for item in items:
        key, doc = _item_id_and_doc(user_id, item, bookmark_type, now)
        if not key:
            continue
        if key in seen:
            continue
        seen.add(key)
        id_doc_list.append((key, doc))

    if not id_doc_list:
        return CreateBookmarksData(
            type=bookmark_type,
            added=[],
            alreadyBookmarked=[],
            failed=[],
        )

    item_ids = [x[0] for x in id_doc_list]
    existing = await find_existing_item_ids(user_id, item_ids, bookmark_type)
    already_bookmarked = list(existing)
    to_insert = [(k, doc) for k, doc in id_doc_list if k not in existing]
    docs_only = [doc for _, doc in to_insert]

    added, _, failed = await add_bookmarks(
        user_id=user_id,
        docs_to_insert=docs_only,
        bookmark_type=bookmark_type,
    )

    return CreateBookmarksData(
        type=bookmark_type,
        added=added,
        alreadyBookmarked=already_bookmarked,
        failed=failed,
    )
