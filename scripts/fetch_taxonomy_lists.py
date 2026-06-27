"""Read-only fetch of product_attributes, attribute values, benefits, and tags from skin_bb MongoDB.

Usage:
    python scripts/fetch_taxonomy_lists.py
    python scripts/fetch_taxonomy_lists.py --mongo-uri "mongodb://user:pass@host:port/skin_bb"

Writes app/label_looker/data/skin_bb_taxonomy.json (read-only source snapshot).
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

from bson import ObjectId
from pymongo import MongoClient

DEFAULT_MONGO_URI = "mongodb://skinbb:IgR9RMn%40skNBbh84Gsz@localhost:27018/skin_bb"
DB_NAME = "skin_bb"
OUTPUT_PATH = (
    Path(__file__).resolve().parents[1] / "app" / "label_looker" / "data" / "skin_bb_taxonomy.json"
)

_OBJECT_ID_RE = re.compile(r"^[0-9a-f]{24}$", re.I)


def _is_garbage_benefit(value: str | None, name: str | None) -> bool:
    v = (value or "").strip()
    n = (name or "").strip()
    if not v or not n:
        return True
    if _OBJECT_ID_RE.fullmatch(v) or _OBJECT_ID_RE.fullmatch(n):
        return True
    if v == n and re.fullmatch(r"[0-9a-f]{20,}", v):
        return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch skin_bb taxonomy lists (read-only).")
    parser.add_argument("--mongo-uri", default=DEFAULT_MONGO_URI, help="MongoDB connection URI")
    args = parser.parse_args()

    client = MongoClient(args.mongo_uri, serverSelectionTimeoutMS=10000)
    db = client[DB_NAME]

    # --- product_attributes ---
    attributes = list(
        db.product_attributes.find({"isDeleted": {"$ne": True}}).sort("name", 1)
    )
    attr_by_id = {a["_id"]: a for a in attributes}

    attr_list = []
    for a in attributes:
        attr_list.append(
            {
                "id": str(a["_id"]),
                "name": a.get("name"),
                "slug": a.get("slug"),
                "dataType": a.get("dataType"),
                "fieldType": a.get("fieldType"),
                "isFilterable": a.get("isFilterable"),
                "isSearchable": a.get("isSearchable"),
                "isVariantField": a.get("isVariantField"),
                "isRequired": a.get("isRequired"),
            }
        )

    # --- product_attribute_values (grouped by attribute) ---
    values = list(
        db.product_attribute_values.find(
            {"isDeleted": {"$ne": True}, "isActive": {"$ne": False}}
        ).sort([("attributeId", 1), ("label", 1)])
    )

    values_by_attribute: dict[str, list[dict]] = defaultdict(list)
    flat_values = []
    for v in values:
        attr_id = v.get("attributeId")
        attr_doc = attr_by_id.get(attr_id, {})
        entry = {
            "id": str(v["_id"]),
            "attributeId": str(attr_id) if attr_id else None,
            "attributeSlug": attr_doc.get("slug"),
            "attributeName": attr_doc.get("name"),
            "value": v.get("value"),
            "label": v.get("label"),
        }
        flat_values.append(entry)
        slug = attr_doc.get("slug") or str(attr_id)
        values_by_attribute[slug].append(entry)

    # --- benefits ---
    benefits = list(db.benefits.find({}).sort("name", 1))
    benefit_list = []
    benefits_by_value: dict[str, str] = {}
    for b in benefits:
        value = str(b.get("value") or "").strip()
        name = str(b.get("name") or "").strip()
        if _is_garbage_benefit(value, name):
            continue
        benefit_list.append(
            {
                "id": str(b["_id"]),
                "value": value,
                "name": name,
                "applicableAreas": b.get("applicableAreas") or [],
            }
        )
        benefits_by_value[value] = name

    # --- product_tags (active only) ---
    product_tags = list(
        db.product_tags.find({"isDeleted": {"$ne": True}}).sort("name", 1)
    )
    product_tag_list = [
        {
            "id": str(t["_id"]),
            "name": t.get("name"),
            "slug": t.get("slug"),
            "description": t.get("description") or "",
            "seoKeywords": t.get("seoKeywords") or [],
        }
        for t in product_tags
    ]

    # --- tags collection (blog/general tags, active only) ---
    tags = list(db.tags.find({"isDeleted": {"$ne": True}}).sort("name", 1))
    tag_list = [
        {
            "id": str(t["_id"]),
            "name": t.get("name"),
            "slug": t.get("slug"),
            "description": t.get("description") or "",
            "seoKeywords": t.get("seoKeywords") or [],
        }
        for t in tags
    ]

    # Lookup maps: slug/value -> display label
    attribute_slugs = {a["slug"]: a["name"] for a in attr_list if a.get("slug")}
    attribute_values_by_slug: dict[str, dict[str, str]] = {}
    for slug, rows in values_by_attribute.items():
        attribute_values_by_slug[slug] = {r["value"]: r["label"] for r in rows if r.get("value")}

    product_tags_by_slug = {t["slug"]: t["name"] for t in product_tag_list if t.get("slug")}
    tags_by_slug = {t["slug"]: t["name"] for t in tag_list if t.get("slug")}

    payload = {
        "product_attributes": attr_list,
        "product_attribute_values": flat_values,
        "product_attribute_values_by_attribute": dict(values_by_attribute),
        "attribute_slugs": attribute_slugs,
        "attribute_values_by_slug": attribute_values_by_slug,
        "benefits": benefit_list,
        "benefits_by_value": benefits_by_value,
        "product_tags": product_tag_list,
        "product_tags_by_slug": product_tags_by_slug,
        "tags": tag_list,
        "tags_by_slug": tags_by_slug,
        "counts": {
            "product_attributes": len(attr_list),
            "product_attribute_values": len(flat_values),
            "benefits": len(benefit_list),
            "product_tags": len(product_tag_list),
            "tags": len(tag_list),
        },
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)

    print(json.dumps(payload["counts"], indent=2))
    print(f"Written to {OUTPUT_PATH}")

    # Print attribute summary
    print("\n--- product_attributes ---")
    for a in attr_list:
        slug = a["slug"]
        n_vals = len(values_by_attribute.get(slug, []))
        print(f"  {a['name']} ({slug}): {n_vals} values")

    client.close()


if __name__ == "__main__":
    main()
