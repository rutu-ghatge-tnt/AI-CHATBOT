"""
Cost Calculation Post-Processor for Make a Wish
================================================

Applies the new cost calculation rules:
1. Formula cost + 20% = adjusted formula cost
2. Packaging cost = bottle + carton box + labeling
3. Wastage cost = 5% of (formula + packaging)
4. Manufacturer margin = 20% of (formula + packaging + wastage)
5. Overhead cost = wastage + manufacturer margin
6. Final cost = formula cost + packaging cost + overhead

This post-processes the AI-generated cost analysis to apply these rules.
"""

from typing import Dict, Any, Optional
import re


def extract_size_value(size_str: str) -> float:
    """Extract numeric value from size string (e.g., '30ml' -> 30.0, '100g' -> 100.0)."""
    match = re.search(r'(\d+(?:\.\d+)?)', size_str)
    return float(match.group(1)) if match else 0.0


def calculate_formula_cost_with_margin(base_formula_cost: float) -> float:
    """
    Calculate formula cost with 20% margin added.
    
    Args:
        base_formula_cost: Base formula cost (from DB, per kg converted to per unit)
    
    Returns:
        Formula cost with 20% margin
    """
    return base_formula_cost * 1.20


def calculate_packaging_cost(
    bottle_cost: float,
    carton_box_cost: float,
    labeling_cost: float
) -> float:
    """
    Calculate total packaging cost.
    
    Args:
        bottle_cost: Bottle cost
        carton_box_cost: Carton box cost
        labeling_cost: Labeling cost
    
    Returns:
        Total packaging cost
    """
    return bottle_cost + carton_box_cost + labeling_cost


def calculate_wastage_cost(formula_cost: float, packaging_cost: float) -> float:
    """
    Calculate wastage cost (5% of formula + packaging).
    
    Args:
        formula_cost: Formula cost (with 20% margin)
        packaging_cost: Total packaging cost
    
    Returns:
        Wastage cost
    """
    return (formula_cost + packaging_cost) * 0.05


def calculate_manufacturer_margin(
    formula_cost: float,
    packaging_cost: float,
    wastage_cost: float
) -> float:
    """
    Calculate manufacturer margin (20% of formula + packaging + wastage).
    
    Args:
        formula_cost: Formula cost (with 20% margin)
        packaging_cost: Total packaging cost
        wastage_cost: Wastage cost
    
    Returns:
        Manufacturer margin
    """
    return (formula_cost + packaging_cost + wastage_cost) * 0.20


def calculate_overhead_cost(wastage_cost: float, manufacturer_margin: float) -> float:
    """
    Calculate overhead cost (wastage + manufacturer margin).
    
    Args:
        wastage_cost: Wastage cost
        manufacturer_margin: Manufacturer margin
    
    Returns:
        Overhead cost
    """
    return wastage_cost + manufacturer_margin


def calculate_final_cost(
    formula_cost: float,
    packaging_cost: float,
    overhead_cost: float
) -> float:
    """
    Calculate final cost (formula + packaging + overhead).
    
    Args:
        formula_cost: Formula cost (with 20% margin)
        packaging_cost: Total packaging cost
        overhead_cost: Overhead cost
    
    Returns:
        Final cost
    """
    return formula_cost + packaging_cost + overhead_cost


def process_cost_for_size(
    size: str,
    base_formula_cost_per_100g: float,
    packaging_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Process cost calculation for a specific size.
    
    Args:
        size: Size string (e.g., '30ml', '50g', '100ml')
        base_formula_cost_per_100g: Base formula cost per 100g/ml (from DB)
        packaging_data: Packaging data containing bottle_cost, carton_box_cost, labeling_cost
    
    Returns:
        Complete cost breakdown for the size
    """
    # Extract size value
    size_value = extract_size_value(size)
    
    # Calculate formula cost for this size (proportional to 100g/ml)
    base_formula_cost_for_size = (size_value / 100.0) * base_formula_cost_per_100g
    
    # Apply 20% margin to formula cost
    formula_cost = calculate_formula_cost_with_margin(base_formula_cost_for_size)
    
    # Extract packaging costs
    # Try multiple field names for compatibility
    bottle_cost = (
        packaging_data.get('bottle_cost', 0.0) or
        packaging_data.get('packaging_cost', 0.0) or
        0.0
    )
    carton_box_cost = packaging_data.get('carton_box_cost', 0.0) or 0.0
    labeling_cost = (
        packaging_data.get('labeling_cost', 0.0) or
        packaging_data.get('labelling_cost', 0.0) or
        0.0
    )
    
    # Calculate total packaging cost
    packaging_cost = calculate_packaging_cost(bottle_cost, carton_box_cost, labeling_cost)
    
    # Calculate wastage (5% of formula + packaging)
    wastage_cost = calculate_wastage_cost(formula_cost, packaging_cost)
    
    # Calculate manufacturer margin (20% of formula + packaging + wastage)
    manufacturer_margin = calculate_manufacturer_margin(formula_cost, packaging_cost, wastage_cost)
    
    # Calculate overhead (wastage + manufacturer margin)
    overhead_cost = calculate_overhead_cost(wastage_cost, manufacturer_margin)
    
    # Calculate final cost
    final_cost = calculate_final_cost(formula_cost, packaging_cost, overhead_cost)
    
    return {
        "size": size,
        "formula_cost": round(formula_cost, 2),
        "formula_cost_base": round(base_formula_cost_for_size, 2),  # Before 20% margin
        "formula_cost_margin": round(formula_cost - base_formula_cost_for_size, 2),  # 20% margin amount
        "packaging": {
            "bottle_cost": round(bottle_cost, 2),
            "carton_box_cost": round(carton_box_cost, 2),
            "labeling_cost": round(labeling_cost, 2),
            "total": round(packaging_cost, 2)
        },
        "wastage_cost": round(wastage_cost, 2),
        "manufacturer_margin": round(manufacturer_margin, 2),
        "overhead": {
            "wastage": round(wastage_cost, 2),
            "manufacturer_margin": round(manufacturer_margin, 2),
            "total": round(overhead_cost, 2)
        },
        "final_cost": round(final_cost, 2),
        "breakdown": {
            "formula_cost": round(formula_cost, 2),
            "packaging_cost": round(packaging_cost, 2),
            "overhead_cost": round(overhead_cost, 2),
            "total": round(final_cost, 2)
        }
    }


def post_process_cost_analysis(cost_analysis: Dict[str, Any]) -> Dict[str, Any]:
    """
    Post-process the AI-generated cost analysis to apply new calculation rules.
    
    This function:
    1. Takes the base formula cost and adds 20%
    2. For each packaging option and size, calculates:
       - Packaging cost (bottle + carton + labeling)
       - Wastage (5% of formula + packaging)
       - Manufacturer margin (20% of formula + packaging + wastage)
       - Overhead (wastage + manufacturer margin)
       - Final cost (formula + packaging + overhead)
    
    Args:
        cost_analysis: AI-generated cost analysis dictionary
    
    Returns:
        Updated cost analysis with new calculation structure
    """
    if not cost_analysis or not isinstance(cost_analysis, dict):
        return cost_analysis
    
    # Get base formula cost per 100g/ml
    raw_material_cost = cost_analysis.get('raw_material_cost', {})
    base_formula_cost_per_100g = (
        raw_material_cost.get('total_per_100g', 0) or
        raw_material_cost.get('total_per_100ml', 0) or
        0.0
    )
    
    if base_formula_cost_per_100g == 0:
        # Try to get from cost_estimate
        cost_estimate = cost_analysis.get('cost_estimate', {})
        raw_material_per_100g = cost_estimate.get('raw_material_per_100g', {})
        base_formula_cost_per_100g = raw_material_per_100g.get('best_estimate', 0) or raw_material_per_100g.get('realistic', 0)
    
    if base_formula_cost_per_100g == 0:
        print("⚠️ Warning: Could not find base formula cost, skipping post-processing")
        return cost_analysis
    
    # Calculate adjusted formula cost (with 20% margin)
    adjusted_formula_cost_per_100g = calculate_formula_cost_with_margin(base_formula_cost_per_100g)
    
    # Update raw_material_cost to show adjusted cost
    if 'raw_material_cost' not in cost_analysis:
        cost_analysis['raw_material_cost'] = {}
    
    cost_analysis['raw_material_cost']['base_per_100g'] = round(base_formula_cost_per_100g, 2)
    cost_analysis['raw_material_cost']['adjusted_per_100g'] = round(adjusted_formula_cost_per_100g, 2)
    cost_analysis['raw_material_cost']['margin_percent'] = 20.0
    cost_analysis['raw_material_cost']['margin_amount'] = round(adjusted_formula_cost_per_100g - base_formula_cost_per_100g, 2)
    
    # Process packaging estimates
    packaging_estimate = cost_analysis.get('packaging_estimate', {})
    processed_packaging = {}
    
    for option_key, option_data in packaging_estimate.items():
        if not isinstance(option_data, dict):
            continue
        
        # Extract size from type (e.g., "Dropper bottle 30ml" -> "30ml")
        packaging_type = option_data.get('type', '')
        size_match = re.search(r'(\d+(?:\.\d+)?)\s*(ml|g)', packaging_type, re.IGNORECASE)
        if not size_match:
            # Try to find size in other fields
            size = option_data.get('size') or option_key
        else:
            size = f"{size_match.group(1)}{size_match.group(2).lower()}"
        
        # Process cost for this packaging option
        processed_cost = process_cost_for_size(
            size,
            base_formula_cost_per_100g,
            option_data
        )
        
        # Merge with original packaging data
        processed_packaging[option_key] = {
            **option_data,
            **processed_cost
        }
    
    cost_analysis['packaging_estimate'] = processed_packaging
    
    # Process total_product_cost.with_packaging_per_unit
    total_product_cost = cost_analysis.get('total_product_cost', {})
    with_packaging = total_product_cost.get('with_packaging_per_unit', {})
    processed_with_packaging = {}
    
    for size, size_data in with_packaging.items():
        if not isinstance(size_data, dict):
            continue
        
        # Get base formula cost for this size
        base_formula_for_size = size_data.get('formula_cost', 0)
        if base_formula_for_size == 0:
            # Calculate from per_100g
            size_value = extract_size_value(size)
            base_formula_for_size = (size_value / 100.0) * base_formula_cost_per_100g
        
        # Process cost for this size
        processed_cost = process_cost_for_size(
            size,
            base_formula_cost_per_100g,
            size_data
        )
        
        processed_with_packaging[size] = processed_cost
    
    total_product_cost['with_packaging_per_unit'] = processed_with_packaging
    
    # Process with_overhead_20_percent (now with new calculation)
    with_overhead = total_product_cost.get('with_overhead_20_percent', {})
    processed_with_overhead = {}
    
    for size, size_data in with_overhead.items():
        if not isinstance(size_data, dict):
            continue
        
        # Get the processed cost from with_packaging_per_unit
        if size in processed_with_packaging:
            processed_cost = processed_with_packaging[size]
            processed_with_overhead[size] = {
                "formula_cost": processed_cost['formula_cost'],
                "packaging_cost": processed_cost['packaging']['total'],
                "wastage_cost": processed_cost['wastage_cost'],
                "manufacturer_margin": processed_cost['manufacturer_margin'],
                "overhead_cost": processed_cost['overhead']['total'],
                "final_cost": processed_cost['final_cost'],
                "breakdown": processed_cost['breakdown']
            }
        else:
            # Fallback: calculate from size_data
            base_formula_for_size = size_data.get('subtotal_before_overhead', 0) / 1.2  # Reverse the old 20% overhead
            if base_formula_for_size == 0:
                size_value = extract_size_value(size)
                base_formula_for_size = (size_value / 100.0) * base_formula_cost_per_100g
            
            # Get packaging data from with_packaging
            packaging_data = with_packaging.get(size, {})
            processed_cost = process_cost_for_size(
                size,
                base_formula_cost_per_100g,
                packaging_data
            )
            
            processed_with_overhead[size] = {
                "formula_cost": processed_cost['formula_cost'],
                "packaging_cost": processed_cost['packaging']['total'],
                "wastage_cost": processed_cost['wastage_cost'],
                "manufacturer_margin": processed_cost['manufacturer_margin'],
                "overhead_cost": processed_cost['overhead']['total'],
                "final_cost": processed_cost['final_cost'],
                "breakdown": processed_cost['breakdown']
            }
    
    total_product_cost['with_overhead_calculated'] = processed_with_overhead
    
    # Add summary section
    cost_analysis['cost_calculation_summary'] = {
        "formula_cost_margin_percent": 20.0,
        "wastage_percent": 5.0,
        "manufacturer_margin_percent": 20.0,
        "calculation_steps": [
            "1. Formula cost = Base formula cost + 20% margin",
            "2. Packaging cost = Bottle + Carton box + Labeling",
            "3. Wastage cost = 5% of (Formula cost + Packaging cost)",
            "4. Manufacturer margin = 20% of (Formula cost + Packaging cost + Wastage cost)",
            "5. Overhead cost = Wastage cost + Manufacturer margin",
            "6. Final cost = Formula cost + Packaging cost + Overhead cost"
        ]
    }
    
    return cost_analysis

