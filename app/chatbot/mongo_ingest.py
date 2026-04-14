# app/chatbot/mongo_ingest.py
"""Load MongoDB documents into LangChain Documents for chatbot RAG (inventory, ingredients, external products)."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import quote, urlparse

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
    SKINBB_PUBLIC_BASE_URL,
)

MANIFEST_PREFIX = "mongo@"
_PUBLISH_STATUS_RE = re.compile(r"^publish(ed)?$", re.I)


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


def _mongo_and(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    if not a:
        return b
    if not b:
        return a
    return {"$and": [a, b]}


def _snapshot_hash(coll, match: Optional[Dict[str, Any]] = None) -> str:
    """Cheap change detector: count + latest timestamp or max _id (optional `match` for filtered collections)."""
    q = match or {}
    try:
        count = coll.count_documents(q)
    except Exception:
        count = 0
    last_marker = ""
    for field in ("updatedAt", "updated_at", "modifiedAt", "createdAt", "created_at"):
        try:
            doc = coll.find_one(_mongo_and(q, {field: {"$exists": True}}), sort=[(field, -1)])
            if doc and doc.get(field) is not None:
                last_marker = f"{field}:{doc.get(field)!s}"
                break
        except Exception:
            continue
    if not last_marker:
        try:
            doc = coll.find_one(q, sort=[("_id", -1)]) if q else coll.find_one(sort=[("_id", -1)])
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


def _variant_shadem_query_value(variant: Dict[str, Any]) -> str:
    """Value for PDP variant query param (`shadem` on current storefront)."""
    for key in ("size", "optionSize", "variantSize", "volume", "capacity", "label"):
        val = variant.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    opt = variant.get("title") or variant.get("name") or variant.get("optionTitle") or ""
    if opt and str(opt).strip():
        return str(opt).strip()
    return ""


def _shop_product_pdp_url(base: str, slug: str, product_id: str, shadem: str | None) -> str:
    """Match storefront PDP pattern: /product/{slug}?id={mongoId}&shadem=..."""
    root = (base or "").strip().rstrip("/")
    if not root or not slug or not product_id:
        return ""
    path_slug = quote(str(slug).strip(), safe="-_")
    qid = quote(str(product_id).strip(), safe="")
    url = f"{root}/product/{path_slug}?id={qid}"
    if shadem and str(shadem).strip():
        url += f"&shadem={quote(str(shadem).strip(), safe='')}"
    return url


def _shop_deep_link_lines(base: str, slug: str, product_id: str, variants: List[Dict[str, Any]]) -> List[str]:
    if not base or not slug or not product_id:
        return []
    lines = [
        "Shop deep links (copy these URLs exactly when recommending this product; include id and variant query params):",
    ]
    seen: Set[str] = set()
    if variants:
        for v in variants[:80]:
            sz = _variant_shadem_query_value(v)
            url = _shop_product_pdp_url(base, slug, product_id, sz or None)
            if not url or url in seen:
                continue
            seen.add(url)
            label = sz or "default variant"
            lines.append(f"  - {label}: {url}")
    if not seen:
        url = _shop_product_pdp_url(base, slug, product_id, None)
        if url:
            lines.append(f"  - PDP: {url}")
    return lines


def _inventory_brand_display(product: Dict[str, Any], brand_ref: Any) -> str:
    """Human brand string for RAG text; avoids embedding-only ObjectIds with no searchable name."""
    for key in ("brandName", "brand_name", "brandTitle", "brand_title", "vendorName", "vendor_name"):
        v = product.get(key)
        if v is not None and str(v).strip():
            return str(v).strip()
    if isinstance(brand_ref, dict) and brand_ref.get("name"):
        return str(brand_ref["name"]).strip()
    if isinstance(brand_ref, ObjectId):
        return f"(brand reference id: {_oid_str(brand_ref)})"
    return str(brand_ref).strip() if brand_ref else ""


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
    brand_line = _inventory_brand_display(product, brand_ref)

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

    pid = _oid_str(product.get("_id"))
    # PDP route is /product/[slug]; many Next builds resolve the document from ?id=.
    # If catalog slug is empty, use product id as path segment so deep links still ingest.
    pdp_path_slug = (slug or "").strip() or pid

    lines = [
        "SkinBB shop catalog product (MongoDB `products` collection, published/live status only in this index).",
        f"Product name: {_truncate(name, 500)}",
        f"URL slug: {_truncate(slug, 320)}" + (" (empty in DB; PDP path uses Mongo id)" if not (slug or "").strip() and pid else ""),
        f"MongoDB product id (use as PDP query id=): {_truncate(pid, 40)}",
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

    base = (SKINBB_PUBLIC_BASE_URL or "").strip().rstrip("/")
    if base and pdp_path_slug and pid and _product_eligible_for_shop_links(product):
        lines.extend(_shop_deep_link_lines(base, pdp_path_slug, pid, variants))

    return "\n".join(lines)


PRODUCTS_ACTIVE_QUERY = {"$or": [{"isDeleted": {"$exists": False}}, {"isDeleted": False}]}

# RAG inventory: only `products` rows that are live in shop (not drafts) and not external-only rows.
PRODUCTS_PUBLISHED_QUERY: Dict[str, Any] = {
    "$and": [
        PRODUCTS_ACTIVE_QUERY,
        {"status": {"$regex": r"^publish(ed)?$", "$options": "i"}},
        {"$nor": [{"isExternalProduct": True}]},
    ]
}


def _product_eligible_for_shop_links(product: Dict[str, Any]) -> bool:
    """Shop deep links only for published, in-house catalog rows."""
    if product.get("isExternalProduct") is True:
        return False
    st = product.get("status")
    if st is None or not str(st).strip():
        return False
    return bool(_PUBLISH_STATUS_RE.match(str(st).strip()))


def _retailer_label_from_url(url: str) -> str:
    u = (url or "").lower()
    if "nykaa.com" in u:
        return "Nykaa"
    if "amazon." in u or "amzn." in u:
        return "Amazon"
    if "flipkart" in u:
        return "Flipkart"
    if "purplle" in u:
        return "Purplle"
    if "tirabeauty" in u or "tira" in u and "beauty" in u:
        return "Tira Beauty"
    if not u.strip():
        return "unknown retailer"
    try:
        host = urlparse(url).netloc.lower().split(":")[0]
        return host or "third-party site"
    except Exception:
        return "third-party site"


def _clean_external_legal_blob(text: Any, max_len: int = 350) -> str:
    """externalproducts often stores repeated manufacturer/importer walls in description."""
    if text is None or not isinstance(text, str):
        return ""
    t = text.replace("\xa0", " ").replace("&nbsp;", " ")
    t = re.sub(r"\s+", " ", t).strip()
    if not t:
        return ""
    if len(t) > 450 and (t.lower().count("expiry date") > 1 or t.count("Manufacturer") > 2):
        m = re.search(
            r"Expiry Date:\s*.{0,60}?\d{1,2}\s+\w+\s+\d{4}",
            t,
            re.I,
        )
        if m:
            return _truncate(m.group(0).strip(), 120)
    return _truncate(t, max_len)


def _format_external_keywords_block(kw: Any) -> str:
    if not isinstance(kw, dict):
        return ""
    parts: List[str] = []
    for key in (
        "product_type_id",
        "form",
        "target_area",
        "main_category",
        "subcategory",
        "price_tier",
    ):
        v = kw.get(key)
        if v is None or v == []:
            continue
        if isinstance(v, list):
            v = ", ".join(str(x) for x in v[:12])
        s = str(v).strip()
        if s:
            parts.append(f"{key}: {s}")
    for key in (
        "concerns",
        "benefits",
        "functionality",
        "application",
        "market_positioning",
        "functional_categories",
    ):
        v = kw.get(key)
        if isinstance(v, list) and v:
            parts.append(f"{key}: {', '.join(str(x) for x in v[:18])}")
    return _truncate("; ".join(parts), 2000)


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
    kw = doc.get("keywords") or {}
    desc_raw = doc.get("description") or ""
    desc = _clean_external_legal_blob(desc_raw, max_len=400)
    ing = doc.get("ingredients", "")
    if isinstance(ing, list):
        ing = ", ".join(str(x) for x in ing)
    price = doc.get("price") or doc.get("mrp") or kw.get("mrp")
    if isinstance(price, list) and price:
        price = price[0]
    cat = (
        doc.get("subcategory")
        or doc.get("category")
        or doc.get("main_category")
        or kw.get("main_category")
        or ""
    )
    if isinstance(cat, list) and cat:
        cat = cat[0] if isinstance(cat[0], str) else str(cat[0])
    url = doc.get("url") or doc.get("product_url") or doc.get("link") or ""
    retailer = _retailer_label_from_url(url)
    kw_line = _format_external_keywords_block(kw)
    lines = [
        "External retailer product — NOT SkinBB or BB Shop inventory. Use for ingredient/education/comparison "
        "only. Do not give users links to third-party product pages; SkinSage only shares buy links for "
        "SkinBB catalog items (Shop deep links).",
        f"Retailer channel (reference only, no outbound product URL): {retailer}",
        f"Name: {_truncate(name, 500)}",
        f"Brand: {_truncate(brand, 300)}",
        f"Category: {_truncate(str(cat), 300)}",
        f"Price / MRP: {price}",
    ]
    if kw_line:
        lines.append(f"Product tags (structured): {kw_line}")
    if desc:
        lines.append(f"Notes (trimmed from listing text): {desc}")
    lines.append(f"Ingredients (may be partial): {_truncate(ing, 8000)}")
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

    def snapshot_unchanged(
        logical: str,
        coll_a,
        coll_b=None,
        *,
        match_a: Optional[Dict[str, Any]] = None,
        match_b: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """True if manifest already has the current snapshot for this logical group."""
        h1 = _snapshot_hash(coll_a, match_a)
        if coll_b is not None:
            h2 = _snapshot_hash(coll_b, match_b)
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
            if snapshot_unchanged("inventory", col_p, col_v, match_a=PRODUCTS_PUBLISHED_QUERY):
                pass  # unchanged
            else:
                h1 = _snapshot_hash(col_p, PRODUCTS_PUBLISHED_QUERY)
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
                pcur = col_p.find(PRODUCTS_PUBLISHED_QUERY)
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
                            "brand_label": (
                                (p.get("brandName") or p.get("brand_name") or "")
                                or _inventory_brand_display(p, p.get("brand"))
                            )[:200],
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
                    ext_url = doc.get("url") or doc.get("product_url") or doc.get("link") or ""
                    meta = _chunk_metadata_for_chroma(
                        {
                            "source": "mongo",
                            "mongo_logical": "external_products",
                            "mongo_collection": MONGO_RAG_EXTERNAL_PRODUCTS_COLLECTION,
                            "type": "external_product",
                            "doc_id": eid,
                            "retailer": _retailer_label_from_url(str(ext_url)),
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
