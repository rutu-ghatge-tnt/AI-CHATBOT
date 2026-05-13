from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Tuple

from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient


def _ts() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S.000000")


SKIN_TYPES = {"normal": "Normal", "combination": "Combination", "dry": "Dry", "oily": "Oily", "sensitive": "Sensitive"}
HAIR_TYPES = {"straight": "Straight", "wavy": "Wavy", "curly": "Curly"}
SKIN_CONCERNS = {
    "dryness": "Dryness",
    "dullness": "Dullness",
    "roughness": "Roughness",
    "oily-skin": "Oily Skin",
    "acne": "Acne",
    "tan": "Tan",
    "spots": "Spots",
    "uneven-skintone": "Uneven Skintone",
    "melasma": "Melasma",
    "scars": "Scars",
    "dark-circles": "Dark Circles",
    "puffy-eyes": "Puffy Eyes",
    "enlarged-pores": "Enlarged Pores",
    "rosacea": "Rosacea",
    "fine-lines": "Fine Lines",
    "wrinkles": "Wrinkles",
    "sagging": "Sagging",
    "sun-damage": "Sun Damage",
}
HAIR_CONCERNS = {
    "frizz": "Frizz",
    "hair-fall": "Hair Fall",
    "hair-thinning": "Hair Thinning",
    "brittle-hair": "Brittle Hair",
    "split-ends": "Split Ends",
    "dull-hair": "Dull Hair",
    "heat-damage": "Heat Damage",
}
SCALP_CONCERNS = {
    "dandruff": "Dandruff",
    "itchy-scalp": "Itchy Scalp",
    "oily-scalp": "Oily Scalp",
    "dry-scalp": "Dry Scalp",
}

SKIN_TYPE_ALIASES = {"all": None, "all-skin-types": None, "normal-skin": "normal", "dry-skin": "dry"}
HAIR_TYPE_ALIASES = {
    "all-hair-types": None,
    "straight-fine": "straight",
    "straight-medium": "straight",
    "straight-thick": "straight",
    "wavy-fine": "wavy",
    "wavy-medium": "wavy",
    "curly-fine": "curly",
    "curly-medium": "curly",
    "curly-coarse": "curly",
    "coily": "curly",
    "kinky": "curly",
}
SKIN_CONCERN_ALIASES = {
    "oiliness": "oily-skin",
    "tanning": "tan",
    "dark-spots": "spots",
    "blackheads": "spots",
    "breakouts": "acne",
    "blemishes": "acne",
    "pigmentation": "uneven-skintone",
    "hyperpigmentation": "uneven-skintone",
    "uneven-skin-tone": "uneven-skintone",
    "scarring": "scars",
    "redness": "rosacea",
    "sagging-skin": "sagging",
    "dehydration": "dryness",
    "aging": "wrinkles",
    "no-specific": None,
}
HAIR_CONCERN_ALIASES = {
    "hair-loss": "hair-fall",
    "thinning": "hair-thinning",
    "thinning-hair": "hair-thinning",
    "breakage": "brittle-hair",
    "hair-breakage": "brittle-hair",
    "brittleness": "brittle-hair",
    "dullness": "dull-hair",
    "no-specific": None,
    "dandruff": None,
    "dry-scalp": None,
    "oily-scalp": None,
    "scalp-itchiness": None,
}
SCALP_CONCERN_ALIASES = {"itchy": "itchy-scalp", "oily": "oily-scalp", "dry": "dry-scalp", "sensitive": None}


def _norm(v: str) -> str:
    return (v or "").strip().lower().replace("_", "-").replace(" ", "-")


def _canon(raw: str, allow: Mapping[str, str], aliases: Mapping[str, Optional[str]]) -> Optional[str]:
    v = _norm(raw)
    if not v:
        return None
    if v in allow:
        return v
    if v in aliases:
        mapped = aliases[v]
        if mapped is None:
            return None
        v = _norm(mapped)
    return v if v in allow else None


def _score(doc: Dict[str, Any]) -> int:
    return int(bool(doc.get("appIcon"))) + int(bool(doc.get("webIcon"))) + int(bool(doc.get("isActive", True)))


def _rewrite_oids(arr: Any, id_map: Dict[ObjectId, Optional[ObjectId]]) -> Optional[List[ObjectId]]:
    if not isinstance(arr, list):
        return None
    out: List[ObjectId] = []
    seen: set[ObjectId] = set()
    for x in arr:
        if not isinstance(x, ObjectId):
            continue
        t = id_map.get(x, x)
        if t is not None and t not in seen:
            seen.add(t)
            out.append(t)
    old = [x for x in arr if isinstance(x, ObjectId)]
    return None if old == out else out


def plan_collection(col, allow: Dict[str, str], aliases: Dict[str, Optional[str]]) -> Dict[str, Any]:
    by_key: Dict[str, List[Dict[str, Any]]] = {}
    drop: List[Dict[str, Any]] = []
    for d in col.find({}):
        key = _canon(str(d.get("value") or d.get("label") or ""), allow, aliases)
        if key is None:
            drop.append(d)
            continue
        by_key.setdefault(key, []).append(d)
    id_map: Dict[ObjectId, Optional[ObjectId]] = {}
    update_label: List[Tuple[ObjectId, str, str]] = []
    delete_ids: List[ObjectId] = []
    keep_keys = set()
    for k, grp in by_key.items():
        keep_keys.add(k)
        keep = max(grp, key=_score)
        keep_id = keep["_id"]
        if str(keep.get("value", "")).strip() != k or str(keep.get("label", "")).strip() != allow[k]:
            update_label.append((keep_id, k, allow[k]))
        for d in grp:
            if d["_id"] == keep_id:
                id_map[d["_id"]] = keep_id
            else:
                id_map[d["_id"]] = keep_id
                delete_ids.append(d["_id"])
    for d in drop:
        id_map[d["_id"]] = None
        delete_ids.append(d["_id"])
    insert = [(v, l) for v, l in allow.items() if v not in keep_keys]
    return {"id_map": id_map, "update_label": update_label, "delete_ids": delete_ids, "insert": insert}


def run() -> None:
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.dry_run and not args.apply:
        raise SystemExit("Use --dry-run or --apply")

    uri = os.getenv("MONGO_URI")
    db_name = os.getenv("DB_NAME", "skin_bb")
    if not uri:
        raise SystemExit("MONGO_URI missing")

    db = MongoClient(uri)[db_name]
    steps = [
        ("skin_types", SKIN_TYPES, SKIN_TYPE_ALIASES, "skinTypes"),
        ("hair_types", HAIR_TYPES, HAIR_TYPE_ALIASES, "hairTypes"),
        ("skin_concerns", SKIN_CONCERNS, SKIN_CONCERN_ALIASES, "skinConcerns"),
        ("hair_concerns", HAIR_CONCERNS, HAIR_CONCERN_ALIASES, "hairConcerns"),
        ("scalp_concerns", SCALP_CONCERNS, SCALP_CONCERN_ALIASES, None),
        ("product_skin_types", SKIN_TYPES, SKIN_TYPE_ALIASES, None),
        ("product_hair_types", HAIR_TYPES, HAIR_TYPE_ALIASES, None),
        ("product_skin_concerns", SKIN_CONCERNS, SKIN_CONCERN_ALIASES, None),
        ("product_hair_concerns", HAIR_CONCERNS, HAIR_CONCERN_ALIASES, None),
    ]
    plans: List[Tuple[str, Dict[str, Any], Optional[str]]] = []
    for name, allow, aliases, ref_field in steps:
        p = plan_collection(db[name], allow, aliases)
        print(
            f"[plan] {name}: delete={len(p['delete_ids'])} insert={len(p['insert'])} "
            f"label_fixes={len(p['update_label'])}"
        )
        plans.append((name, p, ref_field))
    if args.dry_run:
        print("--dry-run: no database writes.")
        return

    for name, p, ref_field in plans:
        if ref_field:
            for bucket in (db["products"], db["combos"]):
                for d in bucket.find({ref_field: {"$exists": True, "$ne": []}}):
                    new_arr = _rewrite_oids(d.get(ref_field), p["id_map"])
                    if new_arr is not None:
                        bucket.update_one({"_id": d["_id"]}, {"$set": {ref_field: new_arr}})
        if p["delete_ids"]:
            db[name].delete_many({"_id": {"$in": p["delete_ids"]}})
        for oid, val, lbl in p["update_label"]:
            db[name].update_one({"_id": oid}, {"$set": {"value": val, "label": lbl, "updatedAt": _ts()}})
        sample = db[name].find_one({}, sort=[("updatedAt", -1)]) or {}
        for val, lbl in p["insert"]:
            body = {
                "value": val,
                "label": lbl,
                "createdAt": _ts(),
                "updatedAt": _ts(),
                "isActive": True,
                "redirectUrl": sample.get("redirectUrl", "shop"),
                "linkType": sample.get("linkType", "shelf"),
                "__v": sample.get("__v", 0),
            }
            db[name].insert_one(body)
        print(f"[done] {name}: inserted {len(p['insert'])} deleted {len(p['delete_ids'])}")

    touched = 0
    for u in db["user_details"].find({}):
        s: Dict[str, Any] = {}
        st = u.get("skinType")
        if isinstance(st, str):
            k = _canon(st, SKIN_TYPES, SKIN_TYPE_ALIASES)
            s["skinType"] = k or "normal"
        sc = u.get("skinConcerns")
        if isinstance(sc, list):
            vals = []
            for x in sc:
                if isinstance(x, str):
                    k = _canon(x, SKIN_CONCERNS, SKIN_CONCERN_ALIASES)
                    if k and k not in vals:
                        vals.append(k)
            s["skinConcerns"] = vals
        ht = u.get("hairType")
        if isinstance(ht, list):
            vals = []
            for x in ht:
                if isinstance(x, str):
                    k = _canon(x, HAIR_TYPES, HAIR_TYPE_ALIASES)
                    if k and k not in vals:
                        vals.append(k)
            s["hairType"] = vals
        hc = u.get("hairConcerns")
        if isinstance(hc, list):
            vals = []
            for x in hc:
                if isinstance(x, str):
                    k = _canon(x, HAIR_CONCERNS, HAIR_CONCERN_ALIASES)
                    if k and k not in vals:
                        vals.append(k)
            s["hairConcerns"] = vals
        if s:
            db["user_details"].update_one({"_id": u["_id"]}, {"$set": s})
            touched += 1
    print(f"[done] user_details string fields touched: {touched}")
    print("Finished.")


if __name__ == "__main__":
    run()
