"""
Ingredient Costs CRUD API
========================
Full CRUD and search for the ingredient_costs collection.
Search by brand name (branded_ingredient) and INCI name.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, Any
from datetime import datetime
from bson import ObjectId

from app.ai_ingredient_intelligence.auth import verify_jwt_token
from app.ai_ingredient_intelligence.db.collections import ingredient_costs_col

router = APIRouter(prefix="/ingredient-costs", tags=["Ingredient Costs"])


def _serialize_doc(doc: dict) -> dict:
    """Convert MongoDB doc to JSON-serializable dict; _id -> id."""
    if not doc:
        return doc
    out = dict(doc)
    out["id"] = str(out.pop("_id"))
    if "migrated_at" in out and hasattr(out["migrated_at"], "isoformat"):
        out["migrated_at"] = out["migrated_at"].isoformat()
    if "updated_at" in out and hasattr(out["updated_at"], "isoformat"):
        out["updated_at"] = out["updated_at"].isoformat()
    return out


# ----- List (with search and pagination) -----

@router.get("")
async def list_ingredient_costs(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    brand_name: Optional[str] = Query(None, description="Search by branded ingredient / brand name"),
    inci_name: Optional[str] = Query(None, description="Search by INCI name"),
    sort_by: str = Query("updated_at", description="Sort field: inci_name, branded_ingredient, avg_cost, updated_at"),
    sort_order: str = Query("desc", description="asc or desc"),
    current_user: dict = Depends(verify_jwt_token),
):
    """
    List ingredient costs with pagination and optional search by brand name and/or INCI name.
    """
    try:
        query = {}
        if brand_name and brand_name.strip():
            query["branded_ingredient"] = {"$regex": brand_name.strip(), "$options": "i"}
        if inci_name and inci_name.strip():
            query["$or"] = [
                {"inci_name": {"$regex": inci_name.strip(), "$options": "i"}},
                {"inci_name_normalized": {"$regex": inci_name.strip().lower(), "$options": "i"}},
            ]
            # If we already had brand_name, combine with $and
            if "branded_ingredient" in query:
                query = {"$and": [{"branded_ingredient": query["branded_ingredient"]}, {"$or": query["$or"]}]}

        total = await ingredient_costs_col.count_documents(query)
        sort_field = "updated_at"
        if sort_by in ("inci_name", "branded_ingredient", "avg_cost", "updated_at", "inci_name_normalized"):
            sort_field = sort_by
        order = -1 if sort_order == "desc" else 1
        cursor = ingredient_costs_col.find(query).sort(sort_field, order).skip(skip).limit(limit)
        items = await cursor.to_list(length=limit)

        return {
            "items": [_serialize_doc(d) for d in items],
            "total": total,
            "skip": skip,
            "limit": limit,
            "hasMore": (skip + limit) < total,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list ingredient costs: {str(e)}")


# ----- Search (must be before /{id}) -----

@router.get("/search/query")
async def search_ingredient_costs(
    q: Optional[str] = Query(None, description="Search in INCI name and brand name"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(verify_jwt_token),
):
    """
    Search ingredient costs by a single query string (matches both INCI name and branded ingredient).
    """
    if not q or not q.strip():
        total = await ingredient_costs_col.count_documents({})
        cursor = ingredient_costs_col.find({}).sort("updated_at", -1).skip(skip).limit(limit)
        items = await cursor.to_list(length=limit)
        return {
            "items": [_serialize_doc(d) for d in items],
            "total": total,
            "skip": skip,
            "limit": limit,
            "hasMore": (skip + limit) < total,
        }
    s = q.strip()
    s_lower = s.lower()
    query = {
        "$or": [
            {"inci_name": {"$regex": s, "$options": "i"}},
            {"inci_name_normalized": {"$regex": s_lower, "$options": "i"}},
            {"branded_ingredient": {"$regex": s, "$options": "i"}},
        ]
    }
    total = await ingredient_costs_col.count_documents(query)
    cursor = ingredient_costs_col.find(query).sort("updated_at", -1).skip(skip).limit(limit)
    items = await cursor.to_list(length=limit)
    return {
        "items": [_serialize_doc(d) for d in items],
        "total": total,
        "skip": skip,
        "limit": limit,
        "hasMore": (skip + limit) < total,
    }


# ----- Detail -----

@router.get("/{id}")
async def get_ingredient_cost(
    id: str,
    current_user: dict = Depends(verify_jwt_token),
):
    """Get a single ingredient cost by ID (view)."""
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ingredient cost ID")
    doc = await ingredient_costs_col.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Ingredient cost not found")
    return _serialize_doc(doc)


# ----- Create -----

@router.post("")
async def create_ingredient_cost(
    payload: dict,
    current_user: dict = Depends(verify_jwt_token),
):
    """
    Create a new ingredient cost.
    Body: inci_name (required), avg_cost (required), branded_ingredient (optional), primary_supplier (optional), source (optional).
    """
    try:
        inci_name = payload.get("inci_name")
        avg_cost = payload.get("avg_cost")
        if inci_name is None or str(inci_name).strip() == "":
            raise HTTPException(status_code=400, detail="inci_name is required")
        if avg_cost is None:
            raise HTTPException(status_code=400, detail="avg_cost is required")
        try:
            avg_cost = float(avg_cost)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="avg_cost must be a number")
        if avg_cost < 0:
            raise HTTPException(status_code=400, detail="avg_cost must be >= 0")

        inci_name = str(inci_name).strip()
        inci_name_normalized = inci_name.lower().strip()
        branded_ingredient = str(payload.get("branded_ingredient", "")).strip() if payload.get("branded_ingredient") is not None else ""
        primary_supplier = str(payload.get("primary_supplier", "")).strip() if payload.get("primary_supplier") is not None else ""
        source = str(payload.get("source", "api")).strip() or "api"
        now = datetime.utcnow()

        doc = {
            "inci_name": inci_name,
            "inci_name_normalized": inci_name_normalized,
            "avg_cost": avg_cost,
            "branded_ingredient": branded_ingredient,
            "primary_supplier": primary_supplier,
            "source": source,
            "updated_at": now,
        }
        result = await ingredient_costs_col.insert_one(doc)
        doc["_id"] = result.inserted_id
        return _serialize_doc(doc)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create ingredient cost: {str(e)}")


# ----- Update (edit) -----

@router.put("/{id}")
async def update_ingredient_cost(
    id: str,
    payload: dict,
    current_user: dict = Depends(verify_jwt_token),
):
    """
    Update an existing ingredient cost (edit).
    Body: inci_name, avg_cost, branded_ingredient, primary_supplier, source (all optional; only provided fields are updated).
    """
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ingredient cost ID")

    existing = await ingredient_costs_col.find_one({"_id": oid})
    if not existing:
        raise HTTPException(status_code=404, detail="Ingredient cost not found")

    update_fields = {}
    if "inci_name" in payload:
        inci_name = str(payload["inci_name"]).strip()
        if not inci_name:
            raise HTTPException(status_code=400, detail="inci_name cannot be empty")
        update_fields["inci_name"] = inci_name
        update_fields["inci_name_normalized"] = inci_name.lower().strip()
    if "avg_cost" in payload:
        try:
            avg_cost = float(payload["avg_cost"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="avg_cost must be a number")
        if avg_cost < 0:
            raise HTTPException(status_code=400, detail="avg_cost must be >= 0")
        update_fields["avg_cost"] = avg_cost
    if "branded_ingredient" in payload:
        update_fields["branded_ingredient"] = str(payload["branded_ingredient"]).strip() if payload["branded_ingredient"] is not None else ""
    if "primary_supplier" in payload:
        update_fields["primary_supplier"] = str(payload["primary_supplier"]).strip() if payload["primary_supplier"] is not None else ""
    if "source" in payload:
        update_fields["source"] = str(payload["source"]).strip() or "api"

    if not update_fields:
        return _serialize_doc(existing)

    update_fields["updated_at"] = datetime.utcnow()
    await ingredient_costs_col.update_one({"_id": oid}, {"$set": update_fields})
    updated = await ingredient_costs_col.find_one({"_id": oid})
    return _serialize_doc(updated)


# ----- Delete -----

@router.delete("/{id}")
async def delete_ingredient_cost(
    id: str,
    current_user: dict = Depends(verify_jwt_token),
):
    """Delete an ingredient cost by ID."""
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ingredient cost ID")
    result = await ingredient_costs_col.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Ingredient cost not found")
    return {"success": True, "message": "Ingredient cost deleted", "id": id}


