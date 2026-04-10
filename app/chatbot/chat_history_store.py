"""
Mongo-backed chat threads for authenticated users (ChatGPT-style persistence).
Anonymous callers keep using request.history only.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.config import (
    CHAT_HISTORY_CONTEXT_TURNS,
    CHAT_HISTORY_MAX_MESSAGES,
    MONGO_CHAT_CONVERSATIONS_COLLECTION,
)


def _collection():
    # Import here so `motor`/Mongo client are not required to import `app.chatbot.api`
    # (avoids skipping the whole chatbot router in main.py if Motor fails at startup).
    from app.ai_ingredient_intelligence.db.mongodb import db

    return db[MONGO_CHAT_CONVERSATIONS_COLLECTION]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def user_id_from_payload(payload: Optional[Dict[str, Any]]) -> Optional[str]:
    if not payload:
        return None
    for key in ("user_id", "sub", "id"):
        v = payload.get(key)
        if v is not None and str(v).strip():
            return str(v).strip()
    return None


def messages_to_context(msgs: List[Dict[str, Any]], max_pairs: int) -> str:
    """Build RAG history string from stored messages (user/assistant pairs)."""
    if not msgs or max_pairs <= 0:
        return ""
    cap = max_pairs * 2
    tail = msgs[-cap:] if len(msgs) > cap else msgs
    parts: List[str] = []
    i = 0
    while i + 1 < len(tail):
        u, a = tail[i], tail[i + 1]
        if u.get("role") == "user" and a.get("role") == "assistant":
            uq = (u.get("content") or "").strip()
            ar = (a.get("content") or "").strip()
            if uq and ar:
                parts.append(f"User: {uq}\nAssistant: {ar}")
            i += 2
        else:
            i += 1
    return "\n".join(parts)


async def load_messages(user_id: str, conversation_id: str) -> List[Dict[str, Any]]:
    doc = await _collection().find_one(
        {"user_id": user_id, "conversation_id": conversation_id},
        projection={"messages": 1},
    )
    if not doc:
        return []
    return list(doc.get("messages") or [])


async def append_turn(
    user_id: str,
    conversation_id: str,
    user_text: str,
    assistant_text: str,
) -> None:
    """Append one user + one assistant message; trim to max length."""
    now = _utcnow()
    user_text = (user_text or "").strip()
    assistant_text = (assistant_text or "").strip()
    user_msg = {"role": "user", "content": user_text, "ts": now}
    asst_msg = {"role": "assistant", "content": assistant_text, "ts": now}

    col = _collection()
    existing = await col.find_one(
        {"user_id": user_id, "conversation_id": conversation_id},
        projection={"messages": 1, "title": 1},
    )
    title = None
    if existing is None or not (existing.get("title") or "").strip():
        title = (user_text[:120] + "…") if len(user_text) > 120 else user_text or "New chat"

    if existing is None:
        await col.insert_one(
            {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "title": title or "New chat",
                "messages": [user_msg, asst_msg][-CHAT_HISTORY_MAX_MESSAGES:],
                "createdAt": now,
                "updatedAt": now,
            }
        )
        return

    msgs: List[Dict[str, Any]] = list(existing.get("messages") or [])
    msgs.extend([user_msg, asst_msg])
    if len(msgs) > CHAT_HISTORY_MAX_MESSAGES:
        msgs = msgs[-CHAT_HISTORY_MAX_MESSAGES:]

    update: Dict[str, Any] = {"$set": {"messages": msgs, "updatedAt": now}}
    if title:
        update["$set"]["title"] = title

    await col.update_one(
        {"user_id": user_id, "conversation_id": conversation_id},
        update,
    )


def _iso(ts: Any) -> Optional[str]:
    if ts is None:
        return None
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.isoformat()
    return str(ts)


async def list_conversations(user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    col = _collection()
    cursor = (
        col.find(
            {"user_id": user_id},
            projection={"conversation_id": 1, "title": 1, "updatedAt": 1},
        )
        .sort("updatedAt", -1)
        .limit(limit)
    )
    out: List[Dict[str, Any]] = []
    async for doc in cursor:
        out.append(
            {
                "conversation_id": doc.get("conversation_id"),
                "title": doc.get("title") or "New chat",
                "updatedAt": _iso(doc.get("updatedAt")),
            }
        )
    return out


async def get_conversation(user_id: str, conversation_id: str) -> Optional[Dict[str, Any]]:
    doc = await _collection().find_one(
        {"user_id": user_id, "conversation_id": conversation_id},
    )
    if not doc:
        return None
    raw_msgs = list(doc.get("messages") or [])
    messages = [
        {
            "role": m.get("role"),
            "content": m.get("content") or "",
            "ts": _iso(m.get("ts")),
        }
        for m in raw_msgs
    ]
    return {
        "conversation_id": doc.get("conversation_id"),
        "title": doc.get("title") or "New chat",
        "createdAt": _iso(doc.get("createdAt")),
        "updatedAt": _iso(doc.get("updatedAt")),
        "messages": messages,
    }


async def delete_conversation(user_id: str, conversation_id: str) -> int:
    res = await _collection().delete_one(
        {"user_id": user_id, "conversation_id": conversation_id}
    )
    return res.deleted_count


async def delete_conversations_bulk(user_id: str, conversation_ids: List[str]) -> int:
    """Delete multiple conversations for a user in one call."""
    clean_ids = [cid.strip() for cid in conversation_ids if cid and cid.strip()]
    if not clean_ids:
        return 0
    res = await _collection().delete_many(
        {"user_id": user_id, "conversation_id": {"$in": clean_ids}}
    )
    return res.deleted_count


def context_turns_limit() -> int:
    return CHAT_HISTORY_CONTEXT_TURNS
