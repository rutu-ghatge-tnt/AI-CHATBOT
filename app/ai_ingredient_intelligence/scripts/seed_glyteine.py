"""One-off seed script for Glyteine branded ingredient."""

import re
import sys
import unicodedata
from pathlib import Path

from bson.objectid import ObjectId
from pymongo import MongoClient

project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from app.config import DB_NAME, MONGO_URI


def normalize_text(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", s).strip().lower()


CHEM_ALIASES = {
    "Peptide": "Peptides",
}


def find_category_id(col, name: str) -> ObjectId | None:
    doc = col.find_one({"functionalName": name}, {"_id": 1})
    if doc:
        return doc["_id"]
    doc = col.find_one(
        {"functionalName": {"$regex": f"^{re.escape(name)}$", "$options": "i"}},
        {"_id": 1},
    )
    return doc["_id"] if doc else None


def get_or_create_functional_category(col, name: str) -> ObjectId:
    existing = find_category_id(col, name)
    if existing:
        return existing
    return col.insert_one(
        {
            "functionalName": name,
            "functionalName_normalized": normalize_text(name),
            "level": 1,
            "parent_id": None,
        }
    ).inserted_id


def find_chemical_class_id(col, name: str) -> ObjectId | None:
    lookup = CHEM_ALIASES.get(name, name)
    doc = col.find_one({"chemicalClassName": lookup}, {"_id": 1})
    if doc:
        return doc["_id"]
    doc = col.find_one(
        {"chemicalClassName": {"$regex": f"^{re.escape(lookup)}$", "$options": "i"}},
        {"_id": 1},
    )
    return doc["_id"] if doc else None


def get_or_create_supplier(col, name: str) -> ObjectId:
    doc = col.find_one({"supplierName": name}, {"_id": 1})
    if doc:
        return doc["_id"]
    doc = col.find_one(
        {"supplierName": {"$regex": f"^{re.escape(name)}$", "$options": "i"}},
        {"_id": 1},
    )
    if doc:
        return doc["_id"]
    return col.insert_one({"supplierName": name, "isValid": False}).inserted_id


def get_or_create_inci(col, name: str) -> ObjectId:
    norm = normalize_text(name)
    doc = col.find_one({"inciName_normalized": norm}, {"_id": 1})
    if doc:
        return doc["_id"]
    return col.insert_one({"inciName": name, "inciName_normalized": norm}).inserted_id


def main() -> None:
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]

    branded_col = db["ingre_branded_ingredients"]
    inci_col = db["ingre_inci"]
    supplier_col = db["ingre_suppliers"]
    func_cat_col = db["ingre_functional_categories"]
    chem_class_col = db["ingre_chemical_classes"]

    ingredient_name = "Glyteine"
    original_inci_name = "Gamma-Glutamylcysteine"

    func_names = [
        "Antioxidant",
        "Skin Conditioning",
        "Anti-aging",
        "Even Skin Tone",
        "Brightening",
    ]
    func_ids: list[ObjectId] = []
    for name in func_names:
        fid = get_or_create_functional_category(func_cat_col, name)
        func_ids.append(fid)
        print(f"  functional: {name} -> {fid}")

    chem_id = find_chemical_class_id(chem_class_col, "Peptide")
    print(f"  chemical class: Peptide -> {chem_id}")

    supplier_name = "INID Research Pvt Ltd, Mumbai"
    supplier_id = get_or_create_supplier(supplier_col, supplier_name)
    print(f"  supplier: {supplier_name} -> {supplier_id}")

    inci_id = get_or_create_inci(inci_col, original_inci_name)
    print(f"  inci: {original_inci_name} -> {inci_id}")

    description = (
        "Glyteine®️ is γ-L-glutamyl-L-cysteine (GGC), a dipeptide of glutamate and cysteine "
        "and the direct precursor of glutathione — the body's master intracellular antioxidant, "
        "used by every cell for oxidative defense, detoxification, mitochondrial energy and repair. "
        "Glutathione's importance has been understood for decades, yet most attempts to raise it disappoint, "
        "because glutathione taken directly is largely broken down before it reaches the inside of the cell, "
        "and the cell's own production is capped by a built-in rate-limiting step.\n"
        "Glyteine solves this differently. Unlike glutathione or NAC, it is taken up intact and enters "
        "the synthesis pathway downstream of that rate-limiting control point — delivering the exact substrate "
        "the cell needs to build glutathione on demand, and raising glutathione inside the cell where "
        "antioxidant defense actually happens. Taken orally, a single dose elevates intracellular glutathione "
        "within approximately 90 minutes.\n"
        "When used orally as a supplement, Glyteine functions as an antioxidant that restores and elevates "
        "intracellular glutathione, supporting the cellular antioxidant system that underpins healthy aging "
        "and whole-body resilience. Because the effect is measured inside the cell rather than in the "
        "bloodstream alone, it addresses the antioxidant capacity that ordinary glutathione supplements "
        "struggle to reach.\n"
        "When used topically in skincare, Glyteine acts as an antioxidant active that defends skin against "
        "UV-induced oxidative stress — in human skin-explant testing it reduced UV lipid-peroxidation markers "
        "by ~49%, outperforming finished glutathione, which was associated with structural damage to the "
        "explant (BIO-EC, France). In a 28-day clinical study on Indian skin (Fitzpatrick III–V), a "
        "Glyteine-powered serum visibly brightened skin, reduced melanin content and improved skin-tone "
        "evenness, with 100% of participants showing measurable improvement (Mascot Spincontrol India 2025).\n"
        "Because it works through a single mechanism — raising intracellular glutathione and lowering "
        "oxidative stress — Glyteine has been studied across a wide range of biological systems, including "
        "skin, brain and neural tissue, respiratory and airway cells, vascular and endothelial function, liver, "
        "and immune and mitochondrial pathways, with one consistent finding throughout: reduced oxidative "
        "stress and restored cellular glutathione. Its overall benefit is foundational rather than narrow: "
        "it strengthens the cellular antioxidant system that underpins healthy aging and whole-body resilience "
        "— with skin as the visible entry point.\n"
        "Supplied as a white to off-white powder for use in oral cellular-glutathione supplements and "
        "topical antioxidant, brightening and even-tone skincare."
    )

    norm_name = normalize_text(ingredient_name)
    name_filter = {
        "$or": [
            {"ingredient_name_normalized": norm_name},
            {
                "ingredient_name": {
                    "$regex": f"^{re.escape(ingredient_name)}$",
                    "$options": "i",
                }
            },
        ]
    }
    existing = branded_col.find_one(name_filter, {"_id": 1})

    branded_doc = {
        "ingredient_name": ingredient_name,
        "ingredient_name_normalized": norm_name,
        "original_inci_name": original_inci_name,
        "inci_ids": [inci_id],
        "functional_category_ids": func_ids,
        "chemical_class_ids": [chem_id] if chem_id else [],
        "supplier_id": supplier_id,
        "description": description,
        "documents_id": [],
        "approved": False,
        "isDeleted": False,
        "isLocked": False,
    }

    if existing:
        branded_col.replace_one({"_id": existing["_id"]}, branded_doc)
        print(f"\nUpdated Glyteine -> {existing['_id']}")
    else:
        result = branded_col.insert_one(branded_doc)
        print(f"\nInserted Glyteine -> {result.inserted_id}")


if __name__ == "__main__":
    main()
