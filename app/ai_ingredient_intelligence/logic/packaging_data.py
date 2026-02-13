"""
Packaging Data for Cost Calculation
====================================

Defines packaging costs for all common packaging types.
Costs include: bottle/jar, carton box, and labeling.

All costs are in Indian Rupees (₹).
"""

from typing import Dict, List, Optional

# Packaging type definitions
PACKAGING_TYPES = {
    # Liquid products (ml)
    "dropper_bottle_30ml": {
        "type": "Dropper bottle 30ml",
        "category": "liquid",
        "size": "30ml",
        "bottle_cost": 15.0,
        "carton_box_cost": 7.0,
        "labeling_cost": 4.0,
        "total": 26.0
    },
    "dropper_bottle_50ml": {
        "type": "Dropper bottle 50ml",
        "category": "liquid",
        "size": "50ml",
        "bottle_cost": 18.0,
        "carton_box_cost": 8.0,
        "labeling_cost": 5.0,
        "total": 31.0
    },
    "dropper_bottle_100ml": {
        "type": "Dropper bottle 100ml",
        "category": "liquid",
        "size": "100ml",
        "bottle_cost": 22.0,
        "carton_box_cost": 9.0,
        "labeling_cost": 6.0,
        "total": 37.0
    },
    "pump_bottle_30ml": {
        "type": "Pump bottle 30ml",
        "category": "liquid",
        "size": "30ml",
        "bottle_cost": 20.0,
        "carton_box_cost": 7.0,
        "labeling_cost": 4.0,
        "total": 31.0
    },
    "pump_bottle_50ml": {
        "type": "Pump bottle 50ml",
        "category": "liquid",
        "size": "50ml",
        "bottle_cost": 25.0,
        "carton_box_cost": 8.0,
        "labeling_cost": 5.0,
        "total": 38.0
    },
    "pump_bottle_100ml": {
        "type": "Pump bottle 100ml",
        "category": "liquid",
        "size": "100ml",
        "bottle_cost": 25.0,
        "carton_box_cost": 8.0,
        "labeling_cost": 6.0,
        "total": 39.0
    },
    "airless_pump_30ml": {
        "type": "Airless pump 30ml",
        "category": "liquid",
        "size": "30ml",
        "bottle_cost": 30.0,
        "carton_box_cost": 7.0,
        "labeling_cost": 4.0,
        "total": 41.0
    },
    "airless_pump_50ml": {
        "type": "Airless pump 50ml",
        "category": "liquid",
        "size": "50ml",
        "bottle_cost": 35.0,
        "carton_box_cost": 8.0,
        "labeling_cost": 5.0,
        "total": 48.0
    },
    "airless_pump_100ml": {
        "type": "Airless pump 100ml",
        "category": "liquid",
        "size": "100ml",
        "bottle_cost": 40.0,
        "carton_box_cost": 9.0,
        "labeling_cost": 6.0,
        "total": 55.0
    },
    "spray_bottle_50ml": {
        "type": "Spray bottle 50ml",
        "category": "liquid",
        "size": "50ml",
        "bottle_cost": 12.0,
        "carton_box_cost": 7.0,
        "labeling_cost": 4.0,
        "total": 23.0
    },
    "spray_bottle_100ml": {
        "type": "Spray bottle 100ml",
        "category": "liquid",
        "size": "100ml",
        "bottle_cost": 15.0,
        "carton_box_cost": 8.0,
        "labeling_cost": 5.0,
        "total": 28.0
    },
    "spray_bottle_200ml": {
        "type": "Spray bottle 200ml",
        "category": "liquid",
        "size": "200ml",
        "bottle_cost": 18.0,
        "carton_box_cost": 9.0,
        "labeling_cost": 6.0,
        "total": 33.0
    },
    
    # Solid/Cream products (g)
    "plastic_jar_30g": {
        "type": "Plastic Jar 30g",
        "category": "solid",
        "size": "30g",
        "bottle_cost": 12.0,
        "carton_box_cost": 7.0,
        "labeling_cost": 3.0,
        "total": 22.0
    },
    "plastic_jar_50g": {
        "type": "Plastic Jar 50g",
        "category": "solid",
        "size": "50g",
        "bottle_cost": 15.0,
        "carton_box_cost": 7.0,
        "labeling_cost": 4.0,
        "total": 26.0
    },
    "plastic_jar_100g": {
        "type": "Plastic Jar 100g",
        "category": "solid",
        "size": "100g",
        "bottle_cost": 18.0,
        "carton_box_cost": 8.0,
        "labeling_cost": 5.0,
        "total": 31.0
    },
    "glass_jar_30g": {
        "type": "Glass Jar 30g",
        "category": "solid",
        "size": "30g",
        "bottle_cost": 20.0,
        "carton_box_cost": 7.0,
        "labeling_cost": 3.0,
        "total": 30.0
    },
    "glass_jar_50g": {
        "type": "Glass Jar 50g",
        "category": "solid",
        "size": "50g",
        "bottle_cost": 25.0,
        "carton_box_cost": 7.0,
        "labeling_cost": 4.0,
        "total": 36.0
    },
    "glass_jar_100g": {
        "type": "Glass Jar 100g",
        "category": "solid",
        "size": "100g",
        "bottle_cost": 30.0,
        "carton_box_cost": 8.0,
        "labeling_cost": 5.0,
        "total": 43.0
    },
    "tube_30g": {
        "type": "Tube 30g",
        "category": "solid",
        "size": "30g",
        "bottle_cost": 8.0,
        "carton_box_cost": 6.0,
        "labeling_cost": 3.0,
        "total": 17.0
    },
    "tube_50g": {
        "type": "Tube 50g",
        "category": "solid",
        "size": "50g",
        "bottle_cost": 10.0,
        "carton_box_cost": 7.0,
        "labeling_cost": 4.0,
        "total": 21.0
    },
    "tube_100g": {
        "type": "Tube 100g",
        "category": "solid",
        "size": "100g",
        "bottle_cost": 12.0,
        "carton_box_cost": 8.0,
        "labeling_cost": 5.0,
        "total": 25.0
    },
    "airless_jar_30g": {
        "type": "Airless Jar 30g",
        "category": "solid",
        "size": "30g",
        "bottle_cost": 28.0,
        "carton_box_cost": 7.0,
        "labeling_cost": 3.0,
        "total": 38.0
    },
    "airless_jar_50g": {
        "type": "Airless Jar 50g",
        "category": "solid",
        "size": "50g",
        "bottle_cost": 32.0,
        "carton_box_cost": 7.0,
        "labeling_cost": 4.0,
        "total": 43.0
    },
    "airless_jar_100g": {
        "type": "Airless Jar 100g",
        "category": "solid",
        "size": "100g",
        "bottle_cost": 38.0,
        "carton_box_cost": 8.0,
        "labeling_cost": 5.0,
        "total": 51.0
    }
}


def get_packaging_by_type(packaging_type: str) -> Optional[Dict]:
    """
    Get packaging data by type key.
    
    Args:
        packaging_type: Packaging type key (e.g., "dropper_bottle_30ml")
    
    Returns:
        Packaging data dictionary or None if not found
    """
    return PACKAGING_TYPES.get(packaging_type)


def get_packaging_by_size(size: str, category: str = "liquid") -> List[Dict]:
    """
    Get all packaging options for a specific size.
    
    Args:
        size: Size string (e.g., "30ml", "50g")
        category: "liquid" or "solid"
    
    Returns:
        List of packaging options for that size
    """
    results = []
    for key, data in PACKAGING_TYPES.items():
        if data.get("size") == size and data.get("category") == category:
            results.append({
                "key": key,
                **data
            })
    return results


def get_all_packaging_options() -> Dict[str, Dict]:
    """
    Get all packaging options.
    
    Returns:
        Dictionary of all packaging types
    """
    return PACKAGING_TYPES.copy()


def get_packaging_options_by_category(category: str = "liquid") -> List[Dict]:
    """
    Get all packaging options for a category.
    
    Args:
        category: "liquid" or "solid"
    
    Returns:
        List of packaging options for that category
    """
    results = []
    for key, data in PACKAGING_TYPES.items():
        if data.get("category") == category:
            results.append({
                "key": key,
                **data
            })
    return results

