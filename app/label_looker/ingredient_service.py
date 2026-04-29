from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional

from anthropic import AsyncAnthropic
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection

from app.label_looker.aggregations import ingredient_detail_pipeline
from app.label_looker.constants import DEFAULT_LANGUAGE, SOURCE_CLUADE_AI
from app.label_looker.errors import ScannerApiError
from app.label_looker.escape_regex import escape_regex
from app.label_looker.prompts_controller import prompt_ai_to_get_ingredient_details
from app.label_looker.settings import get_label_looker_settings
from app.label_looker.text_extract import extract_first_json_object


try:
    import bleach
except ImportError:  # pragma: no cover
    bleach = None  # type: ignore

_ALLOWED_BLEACH_TAGS = [
    "p",
    "br",
    "strong",
    "em",
    "ul",
    "ol",
    "li",
    "h1",
    "h2",
    "h3",
    "h4",
    "blockquote",
    "a",
    "span",
    "div",
]


def _sanitize_html(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    if bleach is None:
        return value
    attrs = {"a": ["href", "title", "rel"]}
    return bleach.clean(value, tags=_ALLOWED_BLEACH_TAGS, attributes=attrs, strip=True)


def normalize_scanner_ingredient_name(raw: str | None) -> str:
    if not raw:
        return ""
    s = raw.strip()
    s = re.sub(r"^[^a-zA-Z0-9]+|[^a-zA-Z0-9]+$", "", s)
    return s


async def _find_ingredient_by_name(
    coll: AsyncIOMotorCollection, name: str
) -> Optional[dict[str, Any]]:
    if not name:
        return None
    if "/" in name:
        parts = [p.strip() for p in name.split("/") if p.strip()]
        or_clause = []
        for p in parts:
            or_clause.append({"name": {"$regex": f"^{escape_regex(p)}$", "$options": "i"}})
        if or_clause:
            return await coll.find_one({"$or": or_clause, "isDeleted": {"$ne": True}})
        return None
    return await coll.find_one(
        {"name": {"$regex": f"^{escape_regex(name)}$", "$options": "i"}, "isDeleted": {"$ne": True}}
    )


async def _create_placeholder_ingredient(coll: AsyncIOMotorCollection, name: str) -> dict[str, Any]:
    now = datetime.now()
    doc = {
        "name": name,
        "approved": True,
        "isLocked": True,
        "source": SOURCE_CLUADE_AI,
        "isDeleted": False,
        "parentIngredientId": None,
        "createdAt": now,
        "updatedAt": now,
        "__v": 0,
    }
    ins = await coll.insert_one(doc)
    doc["_id"] = ins.inserted_id
    return doc


async def _find_ai_author(user_coll: AsyncIOMotorCollection) -> dict[str, Any]:
    u = await user_coll.find_one({"role": "ai-assistant"})
    if u:
        return u
    u = await user_coll.find_one({"email": {"$regex": "ai.?assistant", "$options": "i"}})
    if u:
        return u
    raise ScannerApiError(500, "No User with role ai-assistant found for article authoring")


async def _create_article_from_ai(
    *,
    article_coll: AsyncIOMotorCollection,
    user_coll: AsyncIOMotorCollection,
    ingredient_id: ObjectId,
    payload: dict[str, Any],
) -> None:
    author = await _find_ai_author(user_coll)
    aid = author.get("_id")
    now = datetime.now()
    doc: dict[str, Any] = {
        "ingredientId": ingredient_id,
        "status": "approved",
        "authorId": aid,
        "reviewerId": aid,
        "createdAt": now,
        "updatedAt": now,
        "__v": 0,
    }
    for k, v in payload.items():
        if k in ("_id",):
            continue
        doc[k] = _sanitize_html(v) if isinstance(v, str) else v
    await article_coll.insert_one(doc)


async def _list_dimension_names(coll: AsyncIOMotorCollection) -> list[str]:
    rows = await coll.find({}, {"name": 1, "title": 1}).to_list(length=1000)
    out: list[str] = []
    for row in rows:
        v = row.get("name") or row.get("title")
        if isinstance(v, str) and v.strip():
            out.append(v.strip())
    # preserve first-seen order while de-duping
    return list(dict.fromkeys(out))


async def get_ingredient_detail_for_scanner(*, name: str | None) -> list[dict[str, Any]]:
    s = get_label_looker_settings()
    from app.label_looker.db import get_scanner_db

    db = get_scanner_db()
    ing_coll: AsyncIOMotorCollection = db[s.coll_ingredient]
    art_coll: AsyncIOMotorCollection = db[s.coll_article]
    cat_coll: AsyncIOMotorCollection = db[s.coll_category]
    benefit_coll: AsyncIOMotorCollection = db[s.coll_skin_benefit]
    naturality_coll: AsyncIOMotorCollection = db[s.coll_naturality]
    user_coll = db[s.coll_user]

    norm = normalize_scanner_ingredient_name(name)
    if not norm:
        raise ScannerApiError(400, "Query parameter name is required")

    ing = await _find_ingredient_by_name(ing_coll, norm)
    if not ing:
        ing = await _create_placeholder_ingredient(ing_coll, norm)

    ing_id: ObjectId = ing["_id"]
    parent_id = ing.get("parentIngredientId") or ing_id
    if isinstance(parent_id, str) and ObjectId.is_valid(parent_id):
        parent_id = ObjectId(parent_id)

    existing = await art_coll.find_one(
        {
            "status": "approved",
            "$or": [{"ingredientId": ing_id}, {"ingredientId": parent_id}],
        }
    )

    if not existing:
        client = AsyncAnthropic(api_key=s.anthropic_api_key)
        msg = await client.messages.create(
            model=s.anthropic_model,
            max_tokens=8192,
            messages=[
                {
                    "role": "user",
                    "content": prompt_ai_to_get_ingredient_details(
                        ingredient_name=ing.get("name", norm),
                        skin_benefits=await _list_dimension_names(benefit_coll),
                        categories=await _list_dimension_names(cat_coll),
                        naturalities=await _list_dimension_names(naturality_coll),
                    ),
                }
            ],
        )
        raw = "".join(getattr(b, "text", "") for b in msg.content)
        try:
            parsed = extract_first_json_object(raw)
        except Exception as e:
            raise ScannerApiError(500, str(e)) from e
        await _create_article_from_ai(
            article_coll=art_coll,
            user_coll=user_coll,
            ingredient_id=parent_id if isinstance(parent_id, ObjectId) else ing_id,
            payload=parsed,
        )

    pipe = ingredient_detail_pipeline(ing_id, s)
    out = await ing_coll.aggregate(pipe).to_list(length=50)
    if not out:
        return []
    return out


async def get_ingredient_detail_response(*, name: str | None) -> dict[str, Any]:
    rows = await get_ingredient_detail_for_scanner(name=name)
    if not rows:
        raise ScannerApiError(404, "Ingredient not found")
    return {"ingredientDetail": rows}
