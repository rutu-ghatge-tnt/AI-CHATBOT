from __future__ import annotations

from typing import Any

from bson import ObjectId

from app.label_looker.settings import LabelLookerSettings


def ingredient_detail_pipeline(ingredient_oid: ObjectId, s: LabelLookerSettings) -> list[dict[str, Any]]:
    """
    Port of getIngredientDetails-style pipeline (structure only; refine against Node controller when available).
    Starts from ingredients, joins optional article / taxonomies by common foreign keys.
    """
    return [
        {"$match": {"_id": ingredient_oid, "isDeleted": {"$ne": True}}},
        {
            "$lookup": {
                "from": s.coll_article,
                "let": {"ingId": "$_id", "parentId": "$parentIngredientId"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$and": [
                                    {"$eq": ["$status", "approved"]},
                                    {
                                        "$or": [
                                            {"$eq": ["$ingredientId", "$$ingId"]},
                                            {
                                                "$and": [
                                                    {"$ne": ["$$parentId", None]},
                                                    {"$eq": ["$ingredientId", "$$parentId"]},
                                                ]
                                            },
                                        ]
                                    },
                                ]
                            }
                        }
                    },
                    {"$limit": 1},
                ],
                "as": "articleDoc",
            }
        },
        {
            "$lookup": {
                "from": s.coll_category,
                "localField": "categoryId",
                "foreignField": "_id",
                "as": "categories",
            }
        },
        {
            "$lookup": {
                "from": s.coll_skin_benefit,
                "localField": "skinBenefitIds",
                "foreignField": "_id",
                "as": "skinBenefits",
            }
        },
        {
            "$lookup": {
                "from": s.coll_naturality,
                "localField": "naturalityId",
                "foreignField": "_id",
                "as": "naturalityDoc",
            }
        },
        {
            "$addFields": {
                "article": {"$arrayElemAt": ["$articleDoc", 0]},
                "naturality": {"$arrayElemAt": ["$naturalityDoc", 0]},
            }
        },
        {"$project": {"articleDoc": 0, "naturalityDoc": 0}},
    ]


def admin_scan_list_pipeline(*, skip: int, limit: int, s: LabelLookerSettings) -> list[dict[str, Any]]:
    return [
        {"$sort": {"createdAt": -1}},
        {"$skip": skip},
        {"$limit": limit},
        {
            "$lookup": {
                "from": s.coll_user,
                "localField": "userId",
                "foreignField": "_id",
                "as": "userDoc",
            }
        },
        {"$addFields": {"user": {"$arrayElemAt": ["$userDoc", 0]}}},
        {"$project": {"userDoc": 0}},
    ]


def rating_count_pipeline(s: LabelLookerSettings) -> list[dict[str, Any]]:
    return [
        {"$match": {"rating": {"$in": ["good", "okay", "bad"]}}},
        {"$group": {"_id": "$rating", "count": {"$sum": 1}}},
    ]
