"""
Distributor Fetcher Logic
==========================

Business logic for fetching distributor information for branded ingredients.
Extracted from analyze_inci.py for better modularity.
"""

from typing import List, Dict
from bson import ObjectId
from app.ai_ingredient_intelligence.models.schemas import AnalyzeInciItem
from app.ai_ingredient_intelligence.db.collections import (
    distributor_col, 
    branded_ingredients_col,
    inci_col,
    suppliers_col
)


async def fetch_distributors_for_branded_ingredients(items: List[AnalyzeInciItem]) -> Dict[str, List[Dict]]:
    """
    Fetch distributor information for all branded ingredients in a single batch call.
    
    Args:
        items: List of AnalyzeInciItem objects (only branded ingredients with ingredient_id will be processed)
    
    Returns:
        Dict mapping ingredient_name to list of distributors: { 'ingredient_name': [distributor1, distributor2, ...] }
    """
    # Collect all branded ingredients with IDs
    branded_ingredients = []
    for item in items:
        if item.tag == 'B' and item.ingredient_id:
            branded_ingredients.append({
                "name": item.ingredient_name,
                "id": item.ingredient_id
            })
    
    if not branded_ingredients:
        return {}
    
    try:
        # Collect all ingredient IDs and names
        all_ingredient_ids = []
        ingredient_id_map = {}  # Maps ingredient_name -> list of IDs
        
        for ing in branded_ingredients:
            ingredient_name = ing["name"]
            ingredient_id = ing.get("id")
            
            if ingredient_id:
                try:
                    ObjectId(ingredient_id)  # Validate format
                    all_ingredient_ids.append(ingredient_id)
                    if ingredient_name not in ingredient_id_map:
                        ingredient_id_map[ingredient_name] = []
                    ingredient_id_map[ingredient_name].append(ingredient_id)
                except:
                    pass
        
        if not all_ingredient_ids:
            return {}
        
        # Build query conditions
        query_conditions = []
        
        # Primary: Search by ingredientIds array using $in operator
        ingredient_ids_as_objectids = []
        for ing_id_str in all_ingredient_ids:
            try:
                ingredient_ids_as_objectids.append(ObjectId(ing_id_str))
            except:
                pass
        
        if ingredient_ids_as_objectids:
            query_conditions.append({
                "$or": [
                    {"ingredientIds": {"$in": ingredient_ids_as_objectids}},  # ObjectId format
                    {"ingredientIds": {"$in": all_ingredient_ids}}  # String format
                ]
            })
        
        # Backward compatibility: Also search by ingredient names (case-insensitive)
        all_ingredient_names = [ing["name"] for ing in branded_ingredients]
        if all_ingredient_names:
            name_regex_conditions = [
                {"ingredientName": {"$regex": f"^{name}$", "$options": "i"}}
                for name in all_ingredient_names
            ]
            if name_regex_conditions:
                query_conditions.append({"$or": name_regex_conditions})
        
        # Build final query
        if not query_conditions:
            return {}
        
        query = {"$or": query_conditions} if len(query_conditions) > 1 else query_conditions[0]
        
        # Single database query for all distributors
        all_distributors = await distributor_col.find(query).sort("createdAt", -1).to_list(length=None)
        
        # OPTIMIZED: Batch fetch all ingredient names in one query instead of individual find_one calls
        # Collect all unique ingredient IDs from all distributors
        all_ingredient_ids_to_fetch = set()
        for distributor in all_distributors:
            if "ingredientIds" in distributor and distributor.get("ingredientIds"):
                for ing_id in distributor["ingredientIds"]:
                    try:
                        if isinstance(ing_id, str):
                            try:
                                ing_id_obj = ObjectId(ing_id)
                                all_ingredient_ids_to_fetch.add(ing_id_obj)
                            except:
                                continue
                        else:
                            all_ingredient_ids_to_fetch.add(ing_id)
                    except:
                        pass
        
        # Batch fetch all ingredient documents in one query (including supplier info and INCI names)
        ingredient_id_to_name_map = {}
        ingredient_id_to_supplier_map = {}  # Maps ingredient_id -> supplier_name
        ingredient_id_to_inci_map = {}  # Maps ingredient_id -> list of INCI names
        
        if all_ingredient_ids_to_fetch:
            ingredient_docs = await branded_ingredients_col.find(
                {"_id": {"$in": list(all_ingredient_ids_to_fetch)}}
            ).to_list(length=None)
            
            # Collect supplier IDs and INCI IDs
            supplier_ids = set()
            all_inci_ids = set()
            for ing_doc in ingredient_docs:
                ing_id = ing_doc["_id"]
                ingredient_id_to_name_map[ing_id] = ing_doc.get("ingredient_name", "")
                
                # Get supplier ID
                supplier_id = ing_doc.get("supplier_id")
                if supplier_id:
                    try:
                        if isinstance(supplier_id, str):
                            supplier_id = ObjectId(supplier_id)
                        supplier_ids.add(supplier_id)
                        ingredient_id_to_supplier_map[ing_id] = supplier_id
                    except:
                        pass
                
                # Get INCI IDs
                inci_ids = ing_doc.get("inci_ids", [])
                if inci_ids:
                    for inci_id in inci_ids:
                        try:
                            if isinstance(inci_id, str):
                                inci_id = ObjectId(inci_id)
                            all_inci_ids.add(inci_id)
                        except:
                            pass
            
            # Batch fetch supplier names - fetch ALL suppliers (old behavior, no isValid filter)
            if supplier_ids:
                supplier_docs = await suppliers_col.find(
                    {"_id": {"$in": list(supplier_ids)}},
                    {"supplierName": 1}
                ).to_list(length=None)
                supplier_id_to_name = {doc["_id"]: doc.get("supplierName", "") for doc in supplier_docs}
                
                # Update ingredient_id_to_supplier_map with supplier names
                for ing_id, supplier_id in ingredient_id_to_supplier_map.items():
                    supplier_name = supplier_id_to_name.get(supplier_id, "")
                    if supplier_name:  # Only store non-empty supplier names
                        ingredient_id_to_supplier_map[ing_id] = supplier_name
                    else:
                        ingredient_id_to_supplier_map[ing_id] = None
            
            # Batch fetch INCI names
            if all_inci_ids:
                inci_docs = await inci_col.find(
                    {"_id": {"$in": list(all_inci_ids)}},
                    {"inciName": 1}
                ).to_list(length=None)
                
                # Map INCI IDs to names
                inci_id_to_name = {doc["_id"]: doc.get("inciName", "") for doc in inci_docs if doc.get("inciName")}
                
                # Build ingredient_id -> INCI names map
                for ing_doc in ingredient_docs:
                    ing_id = ing_doc["_id"]
                    inci_ids = ing_doc.get("inci_ids", [])
                    inci_names = []
                    for inci_id in inci_ids:
                        try:
                            if isinstance(inci_id, str):
                                inci_id = ObjectId(inci_id)
                            inci_name = inci_id_to_name.get(inci_id)
                            if inci_name and inci_name not in inci_names:
                                inci_names.append(inci_name)
                        except:
                            pass
                    # Also check original_inci_name
                    original_inci = ing_doc.get("original_inci_name", "")
                    if original_inci and original_inci not in inci_names:
                        inci_names.insert(0, original_inci)
                    if inci_names:
                        ingredient_id_to_inci_map[ing_id] = inci_names
        
        # Process distributors: convert ObjectId to string and fetch ingredient names, supplier info, and INCI names from maps
        processed_distributors = []
        seen_distributor_ids = set()  # Track processed distributor IDs to avoid duplicates
        
        for distributor in all_distributors:
            distributor_id = str(distributor["_id"])
            
            # Skip if we've already processed this distributor (avoid duplicates)
            if distributor_id in seen_distributor_ids:
                continue
            seen_distributor_ids.add(distributor_id)
            
            distributor["_id"] = distributor_id
            
            # CRITICAL: Use firmName from distributor document for distributor name (NOT from supplier table)
            distributor_name = distributor.get("firmName", "")
            if distributor_name:
                distributor["distributorName"] = distributor_name
            else:
                distributor["distributorName"] = None
            
            # Fetch ingredientName, supplierName, and INCI names from ingredientIds using the pre-fetched maps
            if "ingredientIds" in distributor and distributor.get("ingredientIds"):
                ingredient_names = []
                supplier_names = []
                inci_names = []
                
                for ing_id in distributor["ingredientIds"]:
                    try:
                        if isinstance(ing_id, str):
                            try:
                                ing_id_obj = ObjectId(ing_id)
                            except:
                                continue
                        else:
                            ing_id_obj = ing_id
                        
                        # Use pre-fetched maps instead of individual queries
                        ingredient_name = ingredient_id_to_name_map.get(ing_id_obj)
                        if ingredient_name and ingredient_name not in ingredient_names:
                            ingredient_names.append(ingredient_name)
                        
                        supplier_name = ingredient_id_to_supplier_map.get(ing_id_obj)
                        if supplier_name and supplier_name not in supplier_names:  # Only add non-None, non-empty, unique supplier names
                            supplier_names.append(supplier_name)
                        
                        # Get INCI names for this ingredient
                        ing_inci_names = ingredient_id_to_inci_map.get(ing_id_obj, [])
                        for inci_name in ing_inci_names:
                            if inci_name and inci_name not in inci_names:
                                inci_names.append(inci_name)
                    except Exception as e:
                        pass
                
                # Set ingredientName - ensure uniqueness
                if ingredient_names:
                    unique_ingredient_names = list(dict.fromkeys(ingredient_names))  # Preserve order, remove duplicates
                    distributor["ingredientName"] = unique_ingredient_names[0] if len(unique_ingredient_names) == 1 else ", ".join(unique_ingredient_names)
                else:
                    distributor["ingredientName"] = distributor.get("ingredientName", "")
                
                # Set supplierName - ensure uniqueness (from supplier table, NOT distributor)
                if supplier_names:
                    unique_suppliers = list(dict.fromkeys(supplier_names))  # Preserve order, remove duplicates
                    distributor["supplierName"] = unique_suppliers[0] if len(unique_suppliers) == 1 else ", ".join(unique_suppliers)
                else:
                    distributor["supplierName"] = None
                
                # Set INCI names - ensure uniqueness
                if inci_names:
                    unique_inci_names = list(dict.fromkeys(inci_names))  # Preserve order, remove duplicates
                    distributor["inciNames"] = unique_inci_names
                else:
                    distributor["inciNames"] = []
            else:
                distributor["ingredientName"] = distributor.get("ingredientName", "")
                distributor["supplierName"] = None
                distributor["inciNames"] = []
            
            processed_distributors.append(distributor)
        
        # Group distributors by ingredient name
        result_map = {}
        
        # Initialize result map with empty arrays for all requested ingredients
        for ing in branded_ingredients:
            result_map[ing["name"]] = []
        
        # Group distributors by matching ingredient
        for distributor in processed_distributors:
            distributor_ingredient_name = distributor.get("ingredientName", "")
            
            # Try to match distributor to requested ingredients
            matched = False
            for ing in branded_ingredients:
                ingredient_name = ing["name"]
                normalized_name = ingredient_name.strip().lower()
                distributor_normalized = distributor_ingredient_name.strip().lower()
                
                # Check if distributor matches this ingredient
                # Match by exact name or if distributor's ingredientIds contains this ingredient's ID
                if (normalized_name == distributor_normalized or 
                    (ingredient_name in ingredient_id_map and 
                     distributor.get("ingredientIds") and
                     any(str(ing_id) in [str(x) for x in distributor.get("ingredientIds", [])] 
                         for ing_id in ingredient_id_map[ingredient_name]))):
                    result_map[ingredient_name].append(distributor)
                    matched = True
                    break
            
            # If no match found but distributor has ingredientName, try fuzzy match
            if not matched and distributor_ingredient_name:
                for ing in branded_ingredients:
                    ingredient_name = ing["name"]
                    if ingredient_name.strip().lower() == distributor_ingredient_name.strip().lower():
                        result_map[ingredient_name].append(distributor)
                        break
        
        return result_map
            
    except Exception as e:
        print(f"Error fetching distributors for branded ingredients: {e}")
        # Return empty dict on error - don't fail the whole analysis
        return {}

