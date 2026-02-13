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

This post-processes the AI-generated cost analysis and adds ALL packaging options
with costs already calculated.
"""

from typing import Dict, Any, List
import re
from app.ai_ingredient_intelligence.logic.packaging_data import (
    get_all_packaging_options,
    get_packaging_options_by_category
)
from app.ai_ingredient_intelligence.logic.formula_generator import get_unit_for_product_type


def extract_size_value(size_str: str) -> float:
    """Extract numeric value from size string (e.g., '30g' -> 30.0, '100g' -> 100.0). All sizes are in grams."""
    match = re.search(r'(\d+(?:\.\d+)?)', size_str)
    return float(match.group(1)) if match else 0.0


def calculate_formula_cost_with_margin(base_formula_cost: float) -> float:
    """Calculate formula cost with 20% margin added."""
    return base_formula_cost * 1.20


def calculate_packaging_cost(bottle_cost: float, carton_box_cost: float, labeling_cost: float) -> float:
    """Calculate total packaging cost."""
    return bottle_cost + carton_box_cost + labeling_cost


def calculate_wastage_cost(formula_cost: float, packaging_cost: float) -> float:
    """Calculate wastage cost (5% of formula + packaging)."""
    return (formula_cost + packaging_cost) * 0.05


def calculate_manufacturer_margin(formula_cost: float, packaging_cost: float, wastage_cost: float) -> float:
    """Calculate manufacturer margin (20% of formula + packaging + wastage)."""
    return (formula_cost + packaging_cost + wastage_cost) * 0.20


def calculate_overhead_cost(wastage_cost: float, manufacturer_margin: float) -> float:
    """Calculate overhead cost (wastage + manufacturer margin)."""
    return wastage_cost + manufacturer_margin


def calculate_final_cost(formula_cost: float, packaging_cost: float, overhead_cost: float) -> float:
    """Calculate final cost (formula + packaging + overhead)."""
    return formula_cost + packaging_cost + overhead_cost


def calculate_cost_for_packaging_option(
    packaging_key: str,
    packaging_data: Dict[str, Any],
    base_formula_cost_per_100g: float
) -> Dict[str, Any]:
    """
    Calculate complete cost breakdown for a specific packaging option.
    
    Args:
        packaging_key: Key like "dropper_bottle_30g"
        packaging_data: Packaging data from packaging_data.py
        base_formula_cost_per_100g: Base formula cost per 100g (from DB, all in grams)
    
    Returns:
        Complete cost breakdown
    """
    size = packaging_data.get('size', '')
    size_value = extract_size_value(size)
    
    # Calculate base formula cost for this size
    base_formula_cost_for_size = (size_value / 100.0) * base_formula_cost_per_100g
    
    # Apply 20% margin to formula cost
    formula_cost = calculate_formula_cost_with_margin(base_formula_cost_for_size)
    
    # Get packaging costs
    bottle_cost = packaging_data.get('bottle_cost', 0.0)
    carton_box_cost = packaging_data.get('carton_box_cost', 0.0)
    labeling_cost = packaging_data.get('labeling_cost', 0.0)
    
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
        "packaging_key": packaging_key,
        "type": packaging_data.get('type', ''),
        "size": size,
        "category": packaging_data.get('category', ''),
        "formula_cost": {
            "base": round(base_formula_cost_for_size, 2),
            "with_margin_20_percent": round(formula_cost, 2),
            "margin_amount": round(formula_cost - base_formula_cost_for_size, 2)
        },
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


def post_process_cost_analysis(cost_analysis: Dict[str, Any], product_type: str) -> Dict[str, Any]:
    """
    Post-process the AI-generated cost analysis to apply new calculation rules
    and add ALL packaging options with costs calculated.
    
    Args:
        cost_analysis: AI-generated cost analysis dictionary
        product_type: Product type (e.g., "serum", "cream") to determine category
    
    Returns:
        Updated cost analysis with all packaging options and new calculation structure
    """
    if not cost_analysis or not isinstance(cost_analysis, dict):
        return cost_analysis
    
    # Get base formula cost per 100g (everything is in grams now)
    raw_material_cost = cost_analysis.get('raw_material_cost', {})
    base_formula_cost_per_100g = (
        raw_material_cost.get('total_per_100g', 0) or
        raw_material_cost.get('total_per_100ml', 0) or  # Fallback for old data
        0.0
    )
    
    if base_formula_cost_per_100g == 0:
        # Try to get from cost_estimate
        cost_estimate = cost_analysis.get('cost_estimate', {})
        raw_material_per_100g = cost_estimate.get('raw_material_per_100g', {})
        base_formula_cost_per_100g = (
            raw_material_per_100g.get('best_estimate', 0) or
            raw_material_per_100g.get('realistic', 0) or
            0.0
        )
    
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
    
    # Determine category (liquid or solid) based on product type
    # Note: Everything is now in grams, but we still categorize by product type
    unit = get_unit_for_product_type(product_type)
    category = "liquid" if unit == "ml" else "solid"
    
    # Get all packaging options for this category (all sizes are in grams now)
    all_packaging_options = get_packaging_options_by_category(category)
    
    # Calculate costs for ALL packaging options
    packaging_options_with_costs = {}
    for opt in all_packaging_options:
        packaging_key = opt['key']
        packaging_data = opt
        calculated_cost = calculate_cost_for_packaging_option(
            packaging_key,
            packaging_data,
            base_formula_cost_per_100g
        )
        packaging_options_with_costs[packaging_key] = calculated_cost
    
    # Add to cost_analysis
    cost_analysis['packaging_options'] = packaging_options_with_costs
    
    # Group by size for easier frontend access
    packaging_by_size = {}
    for key, data in packaging_options_with_costs.items():
        size = data.get('size', '')
        if size not in packaging_by_size:
            packaging_by_size[size] = []
        packaging_by_size[size].append(data)
    
    cost_analysis['packaging_by_size'] = packaging_by_size
    
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
        ],
        "total_packaging_options": len(packaging_options_with_costs)
    }
    
    return cost_analysis
