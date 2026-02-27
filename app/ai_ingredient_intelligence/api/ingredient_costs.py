"""
Ingredient Costs CRUD API
========================
Full CRUD and search for the ingredient_costs collection.
Filters: INCI name, branded ingredient, primary supplier, cost range (min/max).
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, Any, List
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
    out["hide"] = out.get("hide", False)  # default False for legacy docs
    if "migrated_at" in out and hasattr(out["migrated_at"], "isoformat"):
        out["migrated_at"] = out["migrated_at"].isoformat()
    if "updated_at" in out and hasattr(out["updated_at"], "isoformat"):
        out["updated_at"] = out["updated_at"].isoformat()
    return out


def _build_filter_query(
    inci_name: Optional[str] = None,
    brand_name: Optional[str] = None,
    supplier: Optional[str] = None,
    min_cost: Optional[float] = None,
    max_cost: Optional[float] = None,
    q: Optional[str] = None,
) -> dict:
    """Build MongoDB query from INCI, branded name, supplier, cost range, and optional text q. List shows all (hidden + visible)."""
    conditions: List[dict] = []

    if inci_name and inci_name.strip():
        s = inci_name.strip()
        s_lower = s.lower()
        conditions.append({
            "$or": [
                {"inci_name": {"$regex": s, "$options": "i"}},
                {"inci_name_normalized": {"$regex": s_lower, "$options": "i"}},
            ]
        })

    if brand_name and brand_name.strip():
        conditions.append({
            "branded_ingredient": {"$regex": brand_name.strip(), "$options": "i"}
        })

    if supplier and supplier.strip():
        conditions.append({
            "primary_supplier": {"$regex": supplier.strip(), "$options": "i"}
        })

    min_val = None
    max_val = None
    if min_cost is not None:
        try:
            v = float(min_cost)
            if v >= 0:
                min_val = v
        except (TypeError, ValueError):
            pass
    if max_cost is not None:
        try:
            v = float(max_cost)
            if v >= 0:
                max_val = v
        except (TypeError, ValueError):
            pass
    if min_val is not None and max_val is not None:
        conditions.append({"avg_cost": {"$gte": min_val, "$lte": max_val}})
    elif min_val is not None:
        conditions.append({"avg_cost": {"$gte": min_val}})
    elif max_val is not None:
        conditions.append({"avg_cost": {"$lte": max_val}})

    if q and q.strip():
        s = q.strip()
        s_lower = s.lower()
        conditions.append({
            "$or": [
                {"inci_name": {"$regex": s, "$options": "i"}},
                {"inci_name_normalized": {"$regex": s_lower, "$options": "i"}},
                {"branded_ingredient": {"$regex": s, "$options": "i"}},
                {"primary_supplier": {"$regex": s, "$options": "i"}},
            ]
        })

    # List/search always show ALL (admin). Hidden is only excluded in feature queries (make a wish, cost lookup).
    # So we do NOT add NOT_HIDDEN_QUERY here.

    if not conditions:
        return {}
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


# ----- List (with search and pagination) -----

@router.get("")
async def list_ingredient_costs(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    inci_name: Optional[str] = Query(None, description="Filter by INCI name (partial match)"),
    brand_name: Optional[str] = Query(None, description="Filter by branded ingredient / brand name (partial match)"),
    supplier: Optional[str] = Query(None, description="Filter by primary supplier (partial match)"),
    min_cost: Optional[float] = Query(None, ge=0, description="Minimum avg_cost (₹/kg)"),
    max_cost: Optional[float] = Query(None, ge=0, description="Maximum avg_cost (₹/kg)"),
    sort_by: str = Query("updated_at", description="Sort field: inci_name, branded_ingredient, avg_cost, updated_at"),
    sort_order: str = Query("desc", description="asc or desc"),
    current_user: dict = Depends(verify_jwt_token),
):
    """
    List ingredient costs with pagination. Returns ALL ingredients (hidden + visible). Filters: INCI, brand, supplier, cost range. All filters are AND.
    """
    try:
        query = _build_filter_query(
            inci_name=inci_name,
            brand_name=brand_name,
            supplier=supplier,
            min_cost=min_cost,
            max_cost=max_cost,
        )
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
    q: Optional[str] = Query(None, description="Search text in INCI, branded ingredient, and supplier"),
    inci_name: Optional[str] = Query(None, description="Filter by INCI name (partial match)"),
    brand_name: Optional[str] = Query(None, description="Filter by branded ingredient (partial match)"),
    supplier: Optional[str] = Query(None, description="Filter by primary supplier (partial match)"),
    min_cost: Optional[float] = Query(None, ge=0, description="Minimum avg_cost (₹/kg)"),
    max_cost: Optional[float] = Query(None, ge=0, description="Maximum avg_cost (₹/kg)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    sort_by: str = Query("updated_at", description="Sort field: inci_name, branded_ingredient, avg_cost, updated_at"),
    sort_order: str = Query("desc", description="asc or desc"),
    current_user: dict = Depends(verify_jwt_token),
):
    """
    Search ingredient costs. Returns ALL (hidden + visible). Use q for free-text search or specific filters.
    """
    query = _build_filter_query(
        inci_name=inci_name,
        brand_name=brand_name,
        supplier=supplier,
        min_cost=min_cost,
        max_cost=max_cost,
        q=q,
    )
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


# ----- Detail -----

@router.get("/{id}")
async def get_ingredient_cost(
    id: str,
    current_user: dict = Depends(verify_jwt_token),
):
    """
    Get a single ingredient cost by ID. Returns the ingredient regardless of hide status
    (admin can always fetch by ID whether hidden or not). No filter by hide is applied.
    """
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ingredient cost ID")
    # No hide filter: admin must be able to fetch any ingredient by ID
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
    Body: inci_name (required), avg_cost (required), branded_ingredient (optional), primary_supplier (optional), source (optional), hide (optional, default false).
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

        hide = bool(payload.get("hide", False))
        doc = {
            "inci_name": inci_name,
            "inci_name_normalized": inci_name_normalized,
            "avg_cost": avg_cost,
            "branded_ingredient": branded_ingredient,
            "primary_supplier": primary_supplier,
            "source": source,
            "hide": hide,
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
    Body: inci_name, avg_cost, branded_ingredient, primary_supplier, source, hide (all optional; only provided fields are updated).
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
    if "hide" in payload:
        update_fields["hide"] = bool(payload["hide"])

    if not update_fields:
        return _serialize_doc(existing)

    update_fields["updated_at"] = datetime.utcnow()
    await ingredient_costs_col.update_one({"_id": oid}, {"$set": update_fields})
    updated = await ingredient_costs_col.find_one({"_id": oid})
    return _serialize_doc(updated)


# ----- Hide / Unhide (admin) -----

@router.patch("/{id}/hide")
async def set_ingredient_cost_hidden(
    id: str,
    payload: dict,
    current_user: dict = Depends(verify_jwt_token),
):
    """
    Set hide flag for an ingredient cost (admin). Body: {"hide": true} or {"hide": false}.
    Hidden ingredients are excluded from all cost lookups (formulas, cost reference, etc.).
    """
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ingredient cost ID")
    if "hide" not in payload:
        raise HTTPException(status_code=400, detail="Body must include 'hide': true or false")
    hide = bool(payload["hide"])
    existing = await ingredient_costs_col.find_one({"_id": oid})
    if not existing:
        raise HTTPException(status_code=404, detail="Ingredient cost not found")
    await ingredient_costs_col.update_one(
        {"_id": oid},
        {"$set": {"hide": hide, "updated_at": datetime.utcnow()}},
    )
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


