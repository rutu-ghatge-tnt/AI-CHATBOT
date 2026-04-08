# app/chatbot/mongo_ingest.py
"""Load MongoDB documents into LangChain Documents for chatbot RAG (inventory, ingredients, external products)."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Any, Dict, List, Set, Tuple

from bson import ObjectId
from langchain_core.documents import Document
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from app.config import (
    DB_NAME,
    MONGO_RAG_BRANDED_INGREDIENTS_COLLECTION,
    MONGO_RAG_EXTERNAL_PRODUCTS_COLLECTION,
    MONGO_RAG_INCI_COLLECTION,
    MONGO_RAG_INGEST_ENABLED,
    MONGO_RAG_MAX_DOCS_PER_COLLECTION,
    MONGO_RAG_PRODUCTS_COLLECTION,
    MONGO_RAG_VARIANTS_COLLECTION,
    MONGO_URI,
)

MANIFEST_PREFIX = "mongo@"


def _chunk_metadata_for_chroma(meta: dict) -> dict:
    out: Dict[str, Any] = {}
    for k, v in (meta or {}).items():
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            out[k] = v
        else:
            out[k] = str(v)
    return out


def _oid_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, ObjectId):
        return str(value)
    return str(value)


def _snapshot_hash(coll) -> str:
    """Cheap change detector: count + latest timestamp or max _id."""
    try:
        count = coll.count_documents({})
    except Exception:
        count = 0
    last_marker = ""
    for field in ("updatedAt", "updated_at", "modifiedAt", "createdAt", "created_at"):
        try:
            doc = coll.find_one({field: {"$exists": True}}, sort=[(field, -1)])
            if doc and doc.get(field) is not None:
                last_marker = f"{field}:{doc.get(field)!s}"
                break
        except Exception:
            continue
    if not last_marker:
        try:
            doc = coll.find_one(sort=[("_id", -1)])
            if doc and doc.get("_id") is not None:
                last_marker = f"_id:{doc['_id']!s}"
        except Exception:
            last_marker = "none"
    raw = f"{count}|{last_marker}"
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:28]


def _strip_manifest_keys_for(embedded: Set[str], logical: str) -> Set[str]:
    prefix = f"{MANIFEST_PREFIX}{logical}@"
    return {k for k in embedded if not (isinstance(k, str) and k.startswith(prefix))}


def _manifest_key(logical: str, snapshot: str) -> str:
    return f"{MANIFEST_PREFIX}{logical}@{snapshot}"


def _truncate(s: Any, max_len: int = 8000) -> str:
    t = "" if s is None else str(s)
    if len(t) <= max_len:
        return t
    return t[: max_len - 3] + "..."


def _strip_html(html: Any) -> str:
    if html is None or not isinstance(html, str):
        return ""
    text = re.sub(r"<script[^>]*>[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<style[^>]*>[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _string_list(items: Any, max_items: int = 40) -> str:
    if not items:
        return ""
    if not isinstance(items, list):
        return str(items)
    parts: List[str] = []
    for x in items[:max_items]:
        if isinstance(x, dict):
            n = x.get("name") or x.get("label") or x.get("value")
            if n is not None:
                parts.append(str(n))
        else:
            parts.append(str(x))
    return ", ".join(parts)


def _skin_type_labels(skin_type: Any) -> str:
    if not skin_type or not isinstance(skin_type, list):
        return ""
    labels: List[str] = []
    for x in skin_type:
        if isinstance(x, dict) and x.get("label"):
            labels.append(str(x["label"]))
        elif isinstance(x, str):
            labels.append(x)
    return ", ".join(labels)


def _format_meta_data_entries(meta_data: Any) -> str:
    if not meta_data or not isinstance(meta_data, list):
        return ""
    lines: List[str] = []
    for entry in meta_data[:25]:
        if not isinstance(entry, dict):
            continue
        k = entry.get("key") or entry.get("name")
        v = entry.get("value")
        if k is None:
            continue
        if isinstance(v, list):
            v = ", ".join(str(i) for i in v[:20])
        lines.append(f"{k}: {v}")
    return "; ".join(lines)


def _format_inventory_product(
    product: Dict[str, Any],
    variants: List[Dict[str, Any]],
) -> str:
    """Format SkinBB `products` collection document (see schema: productName, slug, ingredients[], etc.)."""
    name = product.get("productName") or product.get("name") or product.get("title") or ""
    slug = product.get("slug") or ""
    sku = product.get("sku") or product.get("easyEcomSku") or ""
    status = product.get("status") or ""
    product_type = product.get("productType") or ""

    brand_ref = product.get("brand")
    if isinstance(brand_ref, ObjectId):
        brand_line = f"(brand reference id: {_oid_str(brand_ref)})"
    elif isinstance(brand_ref, dict) and brand_ref.get("name"):
        brand_line = str(brand_ref["name"])
    else:
        brand_line = str(brand_ref) if brand_ref else ""

    marketed_by = product.get("marketedBy") or ""
    about_brand = _strip_html(product.get("aboutTheBrand") or "")

    short_plain = _strip_html(product.get("description") or "")
    long_plain = _strip_html(product.get("longDescription") or "")
    if short_plain and long_plain:
        combined_desc = "\n\n".join((short_plain, long_plain))
    else:
        combined_desc = long_plain or short_plain

    ingredients = _string_list(product.get("ingredients"))
    key_ingredients = _string_list(product.get("keyIngredients"))
    skin_types = _string_list(product.get("skinTypes")) or _skin_type_labels(product.get("skinType"))
    skin_concerns = _string_list(product.get("skinConcerns"))
    hair_types = _string_list(product.get("hairTypes"))
    hair_concerns = _string_list(product.get("hairConcerns"))
    benefits = _string_list(product.get("benefit"))
    claims = _string_list(product.get("claims"))
    conscious = _string_list(product.get("conscious"))
    meta_keywords = _string_list(product.get("metaKeywords"))
    meta_data_line = _format_meta_data_entries(product.get("metaData"))

    price = product.get("price")
    sale_price = product.get("salePrice")
    qty = product.get("quantity")
    avail = product.get("availableQuantity")
    in_stock = product.get("isInStock")

    flags = []
    if product.get("isFeatured"):
        flags.append("featured")
    if product.get("isBestSeller"):
        flags.append("best seller")
    if product.get("isNewArrival"):
        flags.append("new arrival")
    if product.get("isTrendingNow"):
        flags.append("trending")
    if product.get("isExternalProduct"):
        flags.append("external product")

    lines = [
        "SkinBB shop catalog product (from MongoDB products collection).",
        f"Product name: {_truncate(name, 500)}",
        f"URL slug: {_truncate(slug, 320)}",
        f"SKU: {_truncate(sku, 120)}",
        f"Status: {_truncate(status, 80)}",
        f"Product type: {_truncate(product_type, 200)}",
    ]
    if marketed_by:
        lines.append(f"Marketed by: {_truncate(marketed_by, 300)}")
    if brand_line:
        lines.append(f"Brand: {_truncate(brand_line, 300)}")
    if about_brand:
        lines.append(f"About the brand: {_truncate(about_brand, 1500)}")
    if skin_types:
        lines.append(f"Skin types: {_truncate(skin_types, 400)}")
    if skin_concerns:
        lines.append(f"Skin concerns: {_truncate(skin_concerns, 400)}")
    if hair_types:
        lines.append(f"Hair types: {_truncate(hair_types, 300)}")
    if hair_concerns:
        lines.append(f"Hair concerns: {_truncate(hair_concerns, 300)}")
    if ingredients:
        lines.append(f"Ingredients (INCI-style list): {_truncate(ingredients, 8000)}")
    if key_ingredients:
        lines.append(f"Key ingredients: {_truncate(key_ingredients, 2000)}")
    if benefits:
        lines.append(f"Benefits: {_truncate(benefits, 1000)}")
    if claims:
        lines.append(f"Claims: {_truncate(claims, 500)}")
    if conscious:
        lines.append(f"Conscious / values: {_truncate(conscious, 500)}")
    if meta_keywords:
        lines.append(f"Search keywords: {_truncate(meta_keywords, 800)}")
    if meta_data_line:
        lines.append(f"Attributes: {_truncate(meta_data_line, 2000)}")
    lines.append(
        f"Pricing & stock: price {price}, sale price {sale_price}, quantity {qty}, "
        f"available {avail}, in stock {in_stock}"
    )
    if flags:
        lines.append("Highlights: " + ", ".join(flags))
    lines.append(f"Description: {_truncate(combined_desc, 7000)}")

    if variants:
        lines.append("Additional product variants (linked documents):")
        for v in variants[:80]:
            vsku = v.get("sku") or v.get("SKU") or ""
            vprice = v.get("price") or v.get("salePrice") or v.get("mrp") or v.get("MRP")
            vstock = v.get("stock") or v.get("quantity") or v.get("availableQuantity")
            opt = v.get("title") or v.get("name") or v.get("optionTitle") or ""
            lines.append(
                f"  - {_truncate(opt, 200)} | SKU {_truncate(vsku, 120)} | price {vprice} | stock {vstock}"
            )

    return "\n".join(lines)


PRODUCTS_ACTIVE_QUERY = {"$or": [{"isDeleted": {"$exists": False}}, {"isDeleted": False}]}


def _variant_product_keys(variant: Dict[str, Any]) -> List[str]:
    keys: List[str] = []
    for k in ("productId", "product_id", "product", "parentId", "parent_id"):
        v = variant.get(k)
        if v is not None:
            keys.append(_oid_str(v))
    return [k for k in keys if k]


def _format_external_product(doc: Dict[str, Any]) -> str:
    name = doc.get("name") or doc.get("productName") or ""
    brand = doc.get("brand") or "Unknown"
    desc = doc.get("description") or ""
    ing = doc.get("ingredients", "")
    if isinstance(ing, list):
        ing = ", ".join(str(x) for x in ing)
    price = doc.get("price") or doc.get("mrp") or (doc.get("keywords") or {}).get("mrp")
    cat = (
        doc.get("subcategory")
        or doc.get("category")
        or doc.get("main_category")
        or (doc.get("keywords") or {}).get("main_category")
        or ""
    )
    if isinstance(cat, list) and cat:
        cat = cat[0] if isinstance(cat[0], str) else str(cat[0])
    url = doc.get("url") or doc.get("product_url") or doc.get("link") or ""
    lines = [
        "External / market reference product (for routines and comparisons).",
        f"Name: {_truncate(name, 500)}",
        f"Brand: {_truncate(brand, 300)}",
        f"Category: {_truncate(cat, 300)}",
        f"Price / MRP: {price}",
        f"Description: {_truncate(desc, 4000)}",
        f"Ingredients (may be partial): {_truncate(ing, 8000)}",
        f"URL: {_truncate(url, 500)}",
    ]
    return "\n".join(lines)


def _format_branded_ingredient(doc: Dict[str, Any]) -> str:
    name = doc.get("ingredient_name") or ""
    inci = doc.get("original_inci_name") or ""
    cat = doc.get("category_decided") or doc.get("category") or ""
    notes = doc.get("notes") or doc.get("description") or ""
    supplier = doc.get("supplier_id") or doc.get("supplierId") or ""
    lines = [
        "Formulation / branded ingredient record.",
        f"Ingredient name: {_truncate(name, 500)}",
        f"INCI / original INCI: {_truncate(inci, 500)}",
        f"Category / function: {_truncate(cat, 400)}",
        f"Supplier reference: {_truncate(supplier, 200)}",
        f"Notes: {_truncate(notes, 6000)}",
    ]
    return "\n".join(lines)


def _format_inci(doc: Dict[str, Any]) -> str:
    name = doc.get("inciName") or doc.get("name") or ""
    cat = doc.get("category") or ""
    desc = doc.get("description") or doc.get("details") or ""
    lines = [
        "INCI dictionary entry.",
        f"INCI name: {_truncate(name, 600)}",
        f"Category: {_truncate(cat, 400)}",
        f"Description / details: {_truncate(desc, 8000)}",
    ]
    return "\n".join(lines)


def fetch_mongo_rag_documents(embedded_files: Set[str]) -> Tuple[List[Document], Set[str], List[str], Set[str]]:
    """
    Build Documents from MongoDB when snapshot changed vs manifest.

    Returns:
        documents: new chunks to embed
        new_manifest_keys: keys to add to embed manifest
        chroma_purge_logical: logical names used in metadata mongo_logical — delete these from Chroma before add
        embedded_files_update: full manifest set after removing stale mongo@ keys for updated sources
    """
    out_docs: List[Document] = []
    new_keys: Set[str] = set()
    chroma_purge: List[str] = []
    manifest_working = set(embedded_files)

    if not MONGO_RAG_INGEST_ENABLED:
        return out_docs, new_keys, chroma_purge, manifest_working

    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=20000, connectTimeoutMS=20000)
        client.admin.command("ping")
    except Exception as e:
        print(f"[mongo_ingest] MongoDB unavailable, skipping: {e}")
        return out_docs, new_keys, chroma_purge, manifest_working

    db = client[DB_NAME]

    def snapshot_unchanged(logical: str, coll_a, coll_b=None) -> bool:
        """True if manifest already has the current snapshot for this logical group."""
        h1 = _snapshot_hash(coll_a)
        if coll_b is not None:
            h2 = _snapshot_hash(coll_b)
            combined = hashlib.sha256(f"{h1}|{h2}".encode()).hexdigest()[:28]
        else:
            combined = h1
        key = _manifest_key(logical, combined)
        return key in manifest_working

    try:
        # --- Inventory: products + variants (single logical embedding) ---
        try:
            col_p = db[MONGO_RAG_PRODUCTS_COLLECTION]
            col_v = db[MONGO_RAG_VARIANTS_COLLECTION]
        except Exception:
            col_p = col_v = None

        if col_p is not None:
            if snapshot_unchanged("inventory", col_p, col_v):
                pass  # unchanged
            else:
                h1 = _snapshot_hash(col_p)
                h2 = _snapshot_hash(col_v) if col_v is not None else ""
                snap = hashlib.sha256(f"{h1}|{h2}".encode()).hexdigest()[:28]
                new_k = _manifest_key("inventory", snap)
                manifest_working = _strip_manifest_keys_for(manifest_working, "inventory")
                new_keys.add(new_k)
                chroma_purge.append("inventory_products")

                variant_map: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
                if col_v is not None:
                    vlim = MONGO_RAG_MAX_DOCS_PER_COLLECTION or 0
                    vcur = col_v.find({})
                    if vlim:
                        vcur = vcur.limit(vlim)
                    for vd in vcur:
                        for pk in _variant_product_keys(vd):
                            variant_map[pk].append(vd)

                plim = MONGO_RAG_MAX_DOCS_PER_COLLECTION or 0
                pcur = col_p.find(PRODUCTS_ACTIVE_QUERY)
                if plim:
                    pcur = pcur.limit(plim)
                for p in pcur:
                    pid = _oid_str(p.get("_id"))
                    text = _format_inventory_product(p, variant_map.get(pid, []))
                    meta = _chunk_metadata_for_chroma(
                        {
                            "source": "mongo",
                            "mongo_logical": "inventory_products",
                            "mongo_collection": MONGO_RAG_PRODUCTS_COLLECTION,
                            "type": "inventory_product",
                            "product_id": pid,
                            "slug": p.get("slug") or "",
                            "sku": p.get("sku") or p.get("easyEcomSku") or "",
                            "product_name": p.get("productName") or "",
                        }
                    )
                    out_docs.append(Document(page_content=text, metadata=meta))

        # --- External products (routine / market suggestions) ---
        try:
            col_e = db[MONGO_RAG_EXTERNAL_PRODUCTS_COLLECTION]
        except Exception:
            col_e = None

        if col_e is not None:
            if snapshot_unchanged("externalproducts", col_e, None):
                pass
            else:
                snap = _snapshot_hash(col_e)
                new_k = _manifest_key("externalproducts", snap)
                manifest_working = _strip_manifest_keys_for(manifest_working, "externalproducts")
                new_keys.add(new_k)
                chroma_purge.append("external_products")

                elim = MONGO_RAG_MAX_DOCS_PER_COLLECTION or 0
                ecur = col_e.find({})
                if elim:
                    ecur = ecur.limit(elim)
                for doc in ecur:
                    eid = _oid_str(doc.get("_id"))
                    text = _format_external_product(doc)
                    meta = _chunk_metadata_for_chroma(
                        {
                            "source": "mongo",
                            "mongo_logical": "external_products",
                            "mongo_collection": MONGO_RAG_EXTERNAL_PRODUCTS_COLLECTION,
                            "type": "external_product",
                            "doc_id": eid,
                        }
                    )
                    out_docs.append(Document(page_content=text, metadata=meta))

        # --- Branded ingredients ---
        try:
            col_bi = db[MONGO_RAG_BRANDED_INGREDIENTS_COLLECTION]
        except Exception:
            col_bi = None

        if col_bi is not None:
            if not snapshot_unchanged("ingre_branded", col_bi, None):
                snap = _snapshot_hash(col_bi)
                new_k = _manifest_key("ingre_branded", snap)
                manifest_working = _strip_manifest_keys_for(manifest_working, "ingre_branded")
                new_keys.add(new_k)
                chroma_purge.append("ingre_branded")

                lim = MONGO_RAG_MAX_DOCS_PER_COLLECTION or 0
                cur = col_bi.find({})
                if lim:
                    cur = cur.limit(lim)
                for doc in cur:
                    iid = _oid_str(doc.get("_id"))
                    text = _format_branded_ingredient(doc)
                    meta = _chunk_metadata_for_chroma(
                        {
                            "source": "mongo",
                            "mongo_logical": "ingre_branded",
                            "mongo_collection": MONGO_RAG_BRANDED_INGREDIENTS_COLLECTION,
                            "type": "ingredient_branded",
                            "doc_id": iid,
                        }
                    )
                    out_docs.append(Document(page_content=text, metadata=meta))

        # --- INCI ---
        try:
            col_inci = db[MONGO_RAG_INCI_COLLECTION]
        except Exception:
            col_inci = None

        if col_inci is not None:
            if not snapshot_unchanged("ingre_inci", col_inci, None):
                snap = _snapshot_hash(col_inci)
                new_k = _manifest_key("ingre_inci", snap)
                manifest_working = _strip_manifest_keys_for(manifest_working, "ingre_inci")
                new_keys.add(new_k)
                chroma_purge.append("ingre_inci")

                lim = MONGO_RAG_MAX_DOCS_PER_COLLECTION or 0
                cur = col_inci.find({})
                if lim:
                    cur = cur.limit(lim)
                for doc in cur:
                    cid = _oid_str(doc.get("_id"))
                    text = _format_inci(doc)
                    meta = _chunk_metadata_for_chroma(
                        {
                            "source": "mongo",
                            "mongo_logical": "ingre_inci",
                            "mongo_collection": MONGO_RAG_INCI_COLLECTION,
                            "type": "ingredient_inci",
                            "doc_id": cid,
                        }
                    )
                    out_docs.append(Document(page_content=text, metadata=meta))

    except PyMongoError as e:
        print(f"[mongo_ingest] MongoDB error: {e}")
    finally:
        try:
            client.close()
        except Exception:
            pass

    return out_docs, new_keys, chroma_purge, manifest_working


def purge_mongo_logical_from_chroma(vectorstore, logical_names: List[str]) -> None:
    """Remove prior Mongo-sourced vectors for these logical groups before re-inserting."""
    if not logical_names:
        return
    coll = getattr(vectorstore, "_collection", None)
    if coll is None:
        return
    for logical in logical_names:
        try:
            coll.delete(where={"mongo_logical": logical})
        except Exception as e:
            print(f"[mongo_ingest] Chroma delete warning for {logical}: {e}")
