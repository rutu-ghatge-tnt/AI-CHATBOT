"""
Make a Wish API Endpoint
========================

This module provides the API endpoint for the "Make a Wish" feature.

ENDPOINT: POST /api/make-wish/generate

WHAT IT DOES:
- Accepts wish data from frontend
- Runs complete 5-stage AI pipeline
- Returns comprehensive formula with all analysis

STAGES:
1. Ingredient Selection
2. Formula Optimization
3. Manufacturing Process
4. Cost Analysis
5. Compliance Check
"""

from fastapi import APIRouter, HTTPException, Header, Depends, Query, BackgroundTasks, Body
from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from bson import ObjectId
import time
import httpx
import os

# Import authentication - Using JWT tokens
from app.ai_ingredient_intelligence.auth import verify_jwt_token

from app.ai_ingredient_intelligence.logic.make_wish_generator import (
    generate_formula_from_wish
)
from app.ai_ingredient_intelligence.logic.make_wish_rules_engine import (
    get_rules_engine,
    ValidationSeverity
)
from app.ai_ingredient_intelligence.models.schemas import (
    MakeWishRequest,
    MakeWishResponse
)
from pydantic import BaseModel, Field
from typing import Optional
from app.ai_ingredient_intelligence.db.collections import wish_history_col

# Import Claude client from make_wish_generator (already initialized)
try:
    from app.ai_ingredient_intelligence.logic.make_wish_generator import (
        claude_client,
        claude_model
    )
    claude_api_key = os.getenv("CLAUDE_API_KEY")
    CLAUDE_AVAILABLE = claude_client is not None and claude_api_key is not None
except (ImportError, AttributeError):
    claude_client = None
    claude_model = None
    CLAUDE_AVAILABLE = False
    print("⚠️ Warning: Claude client not available. Using default business strategy prompt.")

router = APIRouter(prefix="/make-wish", tags=["Make a Wish"])

# Gamma API configuration
GAMMA_API_KEY = os.getenv("GAMMA_API_KEY")
GAMMA_API_BASE_URL = "https://public-api.gamma.app/v1.0"
GAMMA_GENERATE_ENDPOINT = f"{GAMMA_API_BASE_URL}/generations"


# ============================================================================
# HELPER FUNCTIONS FOR GAMMA API
# ============================================================================

def format_wish_data_for_gamma(wish_response: Dict[str, Any]) -> str:
    """
    Transform MakeWishResponse data into structured text for Gamma API.
    Formats ALL data from all 5 stages of the Make a Wish pipeline into comprehensive presentation-ready content.
    Includes every field and nested data available in the wish response.
    """
    sections = []
    
    # Executive Summary - COMPLETE wish_data
    sections.append("=" * 80)
    sections.append("EXECUTIVE SUMMARY - COMPLETE WISH DATA")
    sections.append("=" * 80)
    
    wish_data = wish_response.get("wish_data", {})
    sections.append(f"\nProduct Type: {wish_data.get('productType', 'N/A')}")
    sections.append(f"Category: {wish_data.get('category', 'N/A').title()}")
    sections.append(f"Benefits: {', '.join(wish_data.get('benefits', []))}")
    
    if wish_data.get('heroIngredients'):
        sections.append(f"Hero Ingredients: {', '.join(wish_data.get('heroIngredients', []))}")
    if wish_data.get('exclusions'):
        sections.append(f"Exclusions: {', '.join(wish_data.get('exclusions', []))}")
    if wish_data.get('texture'):
        sections.append(f"Texture: {wish_data.get('texture', 'N/A')}")
    if wish_data.get('costMin') and wish_data.get('costMax'):
        sections.append(f"Cost Range: ₹{wish_data.get('costMin')} - ₹{wish_data.get('costMax')} per unit")
    
    # Additional wish_data fields
    if wish_data.get('claims'):
        sections.append(f"Claims: {', '.join(wish_data.get('claims', []))}")
    if wish_data.get('targetAudience'):
        sections.append(f"Target Audience: {', '.join(wish_data.get('targetAudience', []))}")
    if wish_data.get('additionalNotes'):
        sections.append(f"Additional Notes: {wish_data.get('additionalNotes', '')}")
    if wish_data.get('mode'):
        sections.append(f"Mode: {wish_data.get('mode', 'advanced').title()}")
    if wish_data.get('preferences'):
        prefs = wish_data.get('preferences', {})
        if prefs.get('keyIngredients'):
            sections.append(f"Key Ingredients Preference: {', '.join(prefs.get('keyIngredients', []))}")
        if prefs.get('avoidIngredients'):
            sections.append(f"Avoid Ingredients: {', '.join(prefs.get('avoidIngredients', []))}")
        if prefs.get('claims'):
            sections.append(f"Preferred Claims: {', '.join(prefs.get('claims', []))}")
    
    # Stage 1: Ingredient Selection
    sections.append("\n" + "=" * 80)
    sections.append("STAGE 1: INGREDIENT SELECTION")
    sections.append("=" * 80)
    
    ingredient_selection = wish_response.get("ingredient_selection", {})
    if 'ingredients' in ingredient_selection:
        sections.append(f"\nTotal Ingredients Selected: {len(ingredient_selection['ingredients'])}")
        sections.append("\nSelected Ingredients:")
        for idx, ing in enumerate(ingredient_selection['ingredients'], 1):
            name = ing.get('ingredient_name', 'Unknown')
            inci = ing.get('inci_name', '')
            percent = ing.get('recommended_percent', 0)
            function = ing.get('functional_category', '')
            phase = ing.get('phase', '')
            is_hero = "⭐ HERO" if ing.get('is_hero', False) else ""
            is_active = "🔬 ACTIVE" if ing.get('is_active', False) else ""
            
            sections.append(f"\n{idx}. {name} {is_hero} {is_active}")
            if inci:
                sections.append(f"   INCI: {inci}")
            if percent:
                sections.append(f"   Recommended: {percent}%")
            if function:
                sections.append(f"   Function: {function}")
            if phase:
                sections.append(f"   Phase: {phase}")
            if ing.get('notes'):
                sections.append(f"   Notes: {ing.get('notes')}")
    
    # Formula Name and Type
    if ingredient_selection.get('formula_name'):
        sections.append(f"\nSuggested Formula Name: {ingredient_selection.get('formula_name')}")
    if ingredient_selection.get('formula_type'):
        sections.append(f"Formula Type: {ingredient_selection.get('formula_type', 'N/A')}")
    
    # Target pH
    if ingredient_selection.get('target_ph'):
        ph_info = ingredient_selection.get('target_ph', {})
        sections.append(f"Target pH Range: {ph_info.get('min', '')} - {ph_info.get('max', '')}")
    
    # Phases Information
    if ingredient_selection.get('phases'):
        sections.append("\nManufacturing Phases:")
        for phase in ingredient_selection.get('phases', []):
            sections.append(f"  Phase {phase.get('id', '')}: {phase.get('name', '')}")
            sections.append(f"    Process Temp: {phase.get('process_temp', 'N/A')}")
            sections.append(f"    Instructions: {phase.get('instructions', 'N/A')}")
            if phase.get('ingredient_names'):
                sections.append(f"    Ingredients: {', '.join(phase.get('ingredient_names', []))}")
    
    # Insights
    if ingredient_selection.get('insights'):
        sections.append("\nKey Insights:")
        for insight in ingredient_selection.get('insights', []):
            icon = insight.get('icon', '•')
            category = insight.get('category', '')
            title = insight.get('title', '')
            text = insight.get('text', '')
            sections.append(f"  {icon} [{category.upper()}] {title}: {text}")
    
    # Warnings
    if ingredient_selection.get('warnings'):
        sections.append("\nWarnings:")
        for warning in ingredient_selection.get('warnings', []):
            severity = warning.get('severity', 'info').upper()
            category = warning.get('category', '')
            text = warning.get('text', '')
            solution = warning.get('solution', '')
            sections.append(f"  [{severity}] [{category.upper()}] {text}")
            if solution:
                sections.append(f"    Solution: {solution}")
    
    # Ingredient Synergies
    if ingredient_selection.get('ingredient_synergies'):
        sections.append("\nIngredient Synergies:")
        for synergy in ingredient_selection.get('ingredient_synergies', []):
            ingredients = synergy.get('ingredients', [])
            benefit = synergy.get('benefit', '')
            sections.append(f"  {', '.join(ingredients)}: {benefit}")
    
    # Ingredient Conflicts
    if ingredient_selection.get('ingredient_conflicts'):
        sections.append("\nIngredient Conflicts:")
        for conflict in ingredient_selection.get('ingredient_conflicts', []):
            ingredients = conflict.get('ingredients', [])
            issue = conflict.get('issue', '')
            solution = conflict.get('solution', '')
            sections.append(f"  {', '.join(ingredients)}: {issue}")
            if solution:
                sections.append(f"    Solution: {solution}")
    
    # Reasoning
    if ingredient_selection.get('reasoning'):
        sections.append("\nSelection Reasoning:")
        sections.append(f"  {ingredient_selection.get('reasoning', '')}")
    
    # Stage 2: Optimized Formula
    sections.append("\n" + "=" * 80)
    sections.append("STAGE 2: OPTIMIZED FORMULA")
    sections.append("=" * 80)
    
    optimized_formula = wish_response.get("optimized_formula", {})
    formula_info = optimized_formula.get("optimized_formula", {})
    
    if formula_info.get('name'):
        sections.append(f"\nFormula Name: {formula_info.get('name')}")
    if formula_info.get('total_percentage'):
        sections.append(f"Total Percentage: {formula_info.get('total_percentage')}%")
    if formula_info.get('estimated_cost_per_g'):
        sections.append(f"Estimated Cost: ₹{formula_info.get('estimated_cost_per_g')}/g")
    if formula_info.get('target_ph'):
        ph_range = formula_info.get('target_ph', {})
        sections.append(f"Target pH: {ph_range.get('min', '')} - {ph_range.get('max', '')}")
    
    if 'ingredients' in optimized_formula:
        sections.append("\nOptimized Ingredient Percentages:")
        sections.append("-" * 80)
        sections.append(f"{'Ingredient':<40} {'Percentage':<15} {'Phase':<10} {'Function':<15}")
        sections.append("-" * 80)
        for ing in optimized_formula['ingredients']:
            name = ing.get('name', 'Unknown')
            percent = ing.get('percent', 0)
            phase = ing.get('phase', '')
            function = ing.get('function', '')
            sections.append(f"{name:<40} {percent:<15}% {phase:<10} {function:<15}")
    
    # Cost Breakdown
    if optimized_formula.get('cost_breakdown'):
        cost_breakdown = optimized_formula.get('cost_breakdown', {})
        sections.append("\nCost Breakdown:")
        sections.append(f"  Total per g: ₹{cost_breakdown.get('total_per_g', 0)}")
        sections.append(f"  Actives: ₹{cost_breakdown.get('actives_cost', 0)}")
        sections.append(f"  Base: ₹{cost_breakdown.get('base_cost', 0)}")
        sections.append(f"  Functional: ₹{cost_breakdown.get('functional_cost', 0)}")
        sections.append(f"  Preservation: ₹{cost_breakdown.get('preservation_cost', 0)}")
        if cost_breakdown.get('cost_vs_target'):
            sections.append(f"  Cost vs Target: {cost_breakdown.get('cost_vs_target', 'N/A')}")
    
    # Phase Summary
    if optimized_formula.get('phase_summary'):
        sections.append("\nPhase Summary:")
        for phase_sum in optimized_formula.get('phase_summary', []):
            sections.append(f"  Phase {phase_sum.get('phase', '')}: {phase_sum.get('name', '')} - {phase_sum.get('total_percent', 0)}% ({phase_sum.get('ingredients_count', 0)} ingredients)")
    
    # Insights from Optimized Formula
    if optimized_formula.get('insights'):
        sections.append("\nOptimization Insights:")
        for insight in optimized_formula.get('insights', []):
            icon = insight.get('icon', '•')
            title = insight.get('title', '')
            text = insight.get('text', '')
            sections.append(f"  {icon} {title}: {text}")
    
    # Warnings from Optimized Formula
    if optimized_formula.get('warnings'):
        sections.append("\nOptimization Warnings:")
        for warning in optimized_formula.get('warnings', []):
            severity = warning.get('severity', 'info').upper()
            text = warning.get('text', '')
            affected = warning.get('affected_ingredients', [])
            solution = warning.get('solution', '')
            sections.append(f"  [{severity}] {text}")
            if affected:
                sections.append(f"    Affected Ingredients: {', '.join(affected)}")
            if solution:
                sections.append(f"    Solution: {solution}")
    
    # Stability Notes
    if optimized_formula.get('stability_notes'):
        sections.append("\nStability Notes:")
        for note in optimized_formula.get('stability_notes', []):
            sections.append(f"  • {note}")
    
    # pH Adjustment
    if optimized_formula.get('ph_adjustment'):
        ph_adj = optimized_formula.get('ph_adjustment', {})
        sections.append("\npH Adjustment:")
        sections.append(f"  Expected Initial pH: {ph_adj.get('expected_initial_ph', 'N/A')}")
        sections.append(f"  Target pH: {ph_adj.get('target_ph', 'N/A')}")
        sections.append(f"  Adjuster: {ph_adj.get('adjuster', 'N/A')}")
        sections.append(f"  Estimated Amount: {ph_adj.get('estimated_amount', 'N/A')}")
    
    # Stage 3: Manufacturing Process
    sections.append("\n" + "=" * 80)
    sections.append("STAGE 3: MANUFACTURING PROCESS")
    sections.append("=" * 80)
    
    manufacturing = wish_response.get("manufacturing", {})
    if manufacturing.get('process_type'):
        sections.append(f"\nProcess Type: {manufacturing.get('process_type', '').title()}")
    if manufacturing.get('difficulty_level'):
        sections.append(f"Difficulty Level: {manufacturing.get('difficulty_level', '').title()}")
    if manufacturing.get('estimated_time'):
        time_info = manufacturing.get('estimated_time', {})
        sections.append(f"Lab Scale (100g): {time_info.get('lab_scale_100g', 'N/A')}")
        sections.append(f"Pilot Scale (5kg): {time_info.get('pilot_scale_5kg', 'N/A')}")
    
    if 'manufacturing_steps' in manufacturing:
        sections.append("\nManufacturing Steps:")
        for step in manufacturing['manufacturing_steps']:
            step_num = step.get('step_number', '')
            title = step.get('title', '')
            phase = step.get('phase', '')
            temp = step.get('temperature', '')
            duration = step.get('duration', '')
            
            sections.append(f"\nStep {step_num}: {title}")
            if phase:
                sections.append(f"  Phase: {phase}")
            if temp:
                sections.append(f"  Temperature: {temp}")
            if duration:
                sections.append(f"  Duration: {duration}")
            if step.get('ingredients'):
                sections.append(f"  Ingredients: {', '.join(step.get('ingredients', []))}")
            if step.get('instructions'):
                for instruction in step.get('instructions', []):
                    sections.append(f"    • {instruction}")
    
    # Equipment
    if manufacturing.get('equipment_needed'):
        equipment = manufacturing.get('equipment_needed', {})
        if equipment.get('essential'):
            sections.append("\nEssential Equipment:")
            for item in equipment.get('essential', []):
                sections.append(f"  • {item.get('item', '')}: {item.get('purpose', '')}")
        if equipment.get('recommended'):
            sections.append("\nRecommended Equipment:")
            for item in equipment.get('recommended', []):
                sections.append(f"  • {item.get('item', '')}: {item.get('purpose', '')}")
    
    # Critical Parameters
    if manufacturing.get('critical_parameters'):
        sections.append("\nCritical Parameters:")
        for param in manufacturing.get('critical_parameters', []):
            sections.append(f"  {param.get('parameter', '')} ({param.get('stage', '')}):")
            sections.append(f"    Target: {param.get('target', 'N/A')}")
            sections.append(f"    Method: {param.get('method', 'N/A')}")
            if param.get('adjustment'):
                sections.append(f"    Adjustment: {param.get('adjustment', 'N/A')}")
    
    # Troubleshooting
    if manufacturing.get('troubleshooting'):
        sections.append("\nTroubleshooting Guide:")
        for issue in manufacturing.get('troubleshooting', []):
            sections.append(f"  Issue: {issue.get('issue', 'N/A')}")
            sections.append(f"    Cause: {issue.get('cause', 'N/A')}")
            sections.append(f"    Solution: {issue.get('solution', 'N/A')}")
    
    # Packaging Guidelines
    if manufacturing.get('packaging_guidelines'):
        pkg = manufacturing.get('packaging_guidelines', {})
        sections.append("\nPackaging Guidelines:")
        if pkg.get('recommended_packaging'):
            sections.append(f"  Recommended: {', '.join(pkg.get('recommended_packaging', []))}")
        if pkg.get('avoid'):
            sections.append(f"  Avoid: {', '.join(pkg.get('avoid', []))}")
        if pkg.get('fill_temperature'):
            sections.append(f"  Fill Temperature: {pkg.get('fill_temperature', 'N/A')}")
        if pkg.get('storage'):
            sections.append(f"  Storage: {pkg.get('storage', 'N/A')}")
    
    # Quality Control
    if manufacturing.get('quality_control'):
        qc = manufacturing.get('quality_control', {})
        sections.append("\nQuality Control:")
        if qc.get('in_process'):
            sections.append("  In-Process Checks:")
            for check in qc.get('in_process', []):
                sections.append(f"    • {check}")
        if qc.get('final_product'):
            sections.append("  Final Product Checks:")
            for check in qc.get('final_product', []):
                sections.append(f"    • {check}")
    
    # Scale Up Notes
    if manufacturing.get('scale_up_notes'):
        sections.append("\nScale-Up Notes:")
        for note in manufacturing.get('scale_up_notes', []):
            sections.append(f"  • {note}")
    
    # Safety Precautions
    if manufacturing.get('safety_precautions'):
        sections.append("\nSafety Precautions:")
        for precaution in manufacturing.get('safety_precautions', []):
            sections.append(f"  • {precaution}")
    
    # Stage 4: Cost Analysis
    sections.append("\n" + "=" * 80)
    sections.append("STAGE 4: COST ANALYSIS")
    sections.append("=" * 80)
    
    cost_analysis = wish_response.get("cost_analysis", {})
    
    # Raw Material Cost
    if cost_analysis.get('raw_material_cost'):
        rm_cost = cost_analysis.get('raw_material_cost', {})
        sections.append("\nRaw Material Cost:")
        sections.append(f"  Total per g: ₹{rm_cost.get('total_per_g', 0)}")
        sections.append(f"  Total per 100g: ₹{rm_cost.get('total_per_100g', 0)}")
        
        if rm_cost.get('breakdown_by_category'):
            breakdown = rm_cost.get('breakdown_by_category', {})
            sections.append("\n  Breakdown by Category:")
            sections.append(f"    Actives: ₹{breakdown.get('actives', 0)}")
            sections.append(f"    Base: ₹{breakdown.get('base_ingredients', 0)}")
            sections.append(f"    Functional: ₹{breakdown.get('functional_ingredients', 0)}")
            sections.append(f"    Preservatives: ₹{breakdown.get('preservatives', 0)}")
    
    # Cost Estimate with ranges
    if cost_analysis.get('cost_estimate'):
        cost_est = cost_analysis.get('cost_estimate', {})
        if cost_est.get('raw_material_per_g'):
            per_g = cost_est.get('raw_material_per_g', {})
            sections.append("\nCost Estimate (per g):")
            sections.append(f"  Optimistic: ₹{per_g.get('optimistic', 0)}")
            sections.append(f"  Realistic: ₹{per_g.get('realistic', 0)}")
            sections.append(f"  Conservative: ₹{per_g.get('conservative', 0)}")
            sections.append(f"  Range: {per_g.get('display_range', 'N/A')}")
            sections.append(f"  Confidence: {per_g.get('confidence', 'N/A').title()}")
    
    # Total Product Cost
    if cost_analysis.get('total_product_cost'):
        total_cost = cost_analysis.get('total_product_cost', {})
        if total_cost.get('with_packaging_per_unit'):
            sections.append("\nTotal Product Cost (with packaging):")
            for size, cost_data in total_cost.get('with_packaging_per_unit', {}).items():
                sections.append(f"  {size}: ₹{cost_data.get('total', 0)}")
                sections.append(f"    - Formula: ₹{cost_data.get('formula_cost', 0)}")
                sections.append(f"    - Packaging: ₹{cost_data.get('packaging_cost', 0)}")
                sections.append(f"    - Labelling: ₹{cost_data.get('labelling_cost', 0)}")
                sections.append(f"    - Carton: ₹{cost_data.get('carton_box_cost', 0)}")
    
    # Top Cost Drivers
    if cost_analysis.get('raw_material_cost', {}).get('top_cost_drivers'):
        sections.append("\nTop Cost Drivers:")
        for driver in cost_analysis.get('raw_material_cost', {}).get('top_cost_drivers', []):
            sections.append(f"  {driver.get('ingredient', '')}: ₹{driver.get('cost', 0)} ({driver.get('percentage', 0)}%) - {driver.get('contribution', '')} of total")
    
    # Cost Estimate Details
    if cost_analysis.get('cost_estimate'):
        cost_est = cost_analysis.get('cost_estimate', {})
        if cost_est.get('raw_material_per_100g'):
            per_100g = cost_est.get('raw_material_per_100g', {})
            sections.append("\nCost Estimate (per 100g):")
            sections.append(f"  Optimistic: ₹{per_100g.get('optimistic', 0)}")
            sections.append(f"  Realistic: ₹{per_100g.get('realistic', 0)}")
            sections.append(f"  Conservative: ₹{per_100g.get('conservative', 0)}")
            sections.append(f"  Range: {per_100g.get('display_range', 'N/A')}")
        
        # Confidence Breakdown
        if cost_est.get('confidence_breakdown'):
            conf = cost_est.get('confidence_breakdown', {})
            sections.append("\nConfidence Breakdown:")
            if conf.get('high_confidence_ingredients'):
                high = conf.get('high_confidence_ingredients', {})
                sections.append(f"  High Confidence: {high.get('count', 0)} ingredients, ₹{high.get('cost_contribution', 0)} ({high.get('percentage_of_total', '0%')})")
            if conf.get('medium_confidence_ingredients'):
                med = conf.get('medium_confidence_ingredients', {})
                sections.append(f"  Medium Confidence: {med.get('count', 0)} ingredients, ₹{med.get('cost_contribution', 0)} ({med.get('percentage_of_total', '0%')})")
            if conf.get('low_confidence_ingredients'):
                low = conf.get('low_confidence_ingredients', {})
                sections.append(f"  Low Confidence: {low.get('count', 0)} ingredients, ₹{low.get('cost_contribution', 0)} ({low.get('percentage_of_total', '0%')})")
                if low.get('names'):
                    sections.append(f"    Ingredients: {', '.join(low.get('names', []))}")
                if low.get('recommendation'):
                    sections.append(f"    Recommendation: {low.get('recommendation', '')}")
        
        # Top Cost Drivers (detailed)
        if cost_est.get('top_cost_drivers'):
            sections.append("\nDetailed Top Cost Drivers:")
            for driver in cost_est.get('top_cost_drivers', []):
                sections.append(f"  {driver.get('ingredient', '')}:")
                sections.append(f"    Percentage in Formula: {driver.get('percentage_in_formula', 0)}%")
                sections.append(f"    Cost per kg Range: {driver.get('cost_per_kg_range', 'N/A')}")
                sections.append(f"    Cost per g Range: {driver.get('cost_per_g_range', 'N/A')}")
                sections.append(f"    Share of Total: {driver.get('share_of_total', 'N/A')}")
                sections.append(f"    Confidence: {driver.get('confidence', 'N/A').title()}")
                if driver.get('note'):
                    sections.append(f"    Note: {driver.get('note', '')}")
        
        # Disclaimers
        if cost_est.get('disclaimers'):
            sections.append("\nCost Estimation Disclaimers:")
            for disclaimer in cost_est.get('disclaimers', []):
                sections.append(f"  • {disclaimer}")
    
    # Packaging Estimate
    if cost_analysis.get('packaging_estimate'):
        sections.append("\nPackaging Options:")
        for option_key, option_data in cost_analysis.get('packaging_estimate', {}).items():
            sections.append(f"  {option_data.get('type', option_key)}:")
            sections.append(f"    Packaging: ₹{option_data.get('packaging_cost', 0)}")
            sections.append(f"    Labelling: ₹{option_data.get('labelling_cost', 0)}")
            sections.append(f"    Carton: ₹{option_data.get('carton_box_cost', 0)}")
            sections.append(f"    Total: ₹{option_data.get('total_packaging_cost', 0)}")
            sections.append(f"    Total Unit Cost: ₹{option_data.get('total_unit', 0)}")
    
    # Total Product Cost with Overhead
    if cost_analysis.get('total_product_cost', {}).get('with_overhead_20_percent'):
        sections.append("\nTotal Product Cost (with 20% Manufacturing Overhead):")
        for size, cost_data in cost_analysis.get('total_product_cost', {}).get('with_overhead_20_percent', {}).items():
            sections.append(f"  {size}:")
            sections.append(f"    Subtotal: ₹{cost_data.get('subtotal_before_overhead', 0)}")
            sections.append(f"    Overhead (20%): ₹{cost_data.get('manufacturing_overhead_20_percent', 0)}")
            sections.append(f"    Total: ₹{cost_data.get('total', 0)}")
    
    # Pricing Recommendations
    if cost_analysis.get('pricing_recommendations'):
        pricing = cost_analysis.get('pricing_recommendations', {})
        sections.append("\nPricing Recommendations:")
        if pricing.get('d2c_mrp_5x'):
            sections.append("\n  D2C MRP (5x markup):")
            for size, price in pricing.get('d2c_mrp_5x', {}).items():
                sections.append(f"    {size}: ₹{price}")
        if pricing.get('retail_mrp_6x'):
            sections.append("\n  Retail MRP (6x markup):")
            for size, price in pricing.get('retail_mrp_6x', {}).items():
                sections.append(f"    {size}: ₹{price}")
        if pricing.get('premium_positioning_8x'):
            sections.append("\n  Premium Positioning (8x markup):")
            for size, price in pricing.get('premium_positioning_8x', {}).items():
                sections.append(f"    {size}: ₹{price}")
    
    # Cost Optimization Suggestions
    if cost_analysis.get('cost_optimization_suggestions'):
        sections.append("\nCost Optimization Suggestions:")
        for suggestion in cost_analysis.get('cost_optimization_suggestions', []):
            sections.append(f"  • {suggestion.get('suggestion', '')}")
            sections.append(f"    Savings: {suggestion.get('savings', 'N/A')}")
            sections.append(f"    Impact: {suggestion.get('impact', 'N/A')}")
    
    # Competitor Comparison
    if cost_analysis.get('competitor_comparison'):
        comp = cost_analysis.get('competitor_comparison', {})
        sections.append("\nCompetitor Comparison:")
        if comp.get('similar_products'):
            sections.append("  Similar Products:")
            for product in comp.get('similar_products', []):
                sections.append(f"    {product.get('brand', '')} - {product.get('product', '')}:")
                sections.append(f"      MRP: ₹{product.get('mrp', 0)} ({product.get('size', 'N/A')})")
                sections.append(f"      Price per {product.get('size_unit', 'unit')}: {product.get('price_per_unit_display', 'N/A')}")
                if product.get('advantage'):
                    sections.append(f"      Advantage: {product.get('advantage', '')}")
        if comp.get('your_product'):
            your_prod = comp.get('your_product', {})
            sections.append("  Your Product:")
            sections.append(f"    Recommended MRP: ₹{your_prod.get('recommended_mrp', 0)} ({your_prod.get('size', 'N/A')})")
            sections.append(f"    Price per {your_prod.get('size_unit', 'unit')}: {your_prod.get('price_per_unit_display', 'N/A')}")
        if comp.get('competitive_position'):
            sections.append(f"  Competitive Position: {comp.get('competitive_position', 'N/A')}")
        if comp.get('advantages'):
            sections.append("  Advantages:")
            for adv in comp.get('advantages', []):
                sections.append(f"    • {adv.get('competitor_brand', '')}: {adv.get('advantage', '')}")
    
    # Validation Report
    if cost_analysis.get('validation_report'):
        val = cost_analysis.get('validation_report', {})
        sections.append("\nCost Validation Report:")
        sections.append(f"  Water Cost Check: {val.get('water_cost_check', 'N/A')}")
        sections.append(f"  Total vs Benchmark: {val.get('total_vs_benchmark', 'N/A')}")
        sections.append(f"  Active Cost Ratio: {val.get('active_cost_ratio', 'N/A')}")
        sections.append(f"  MRP Plausibility: {val.get('mrp_plausibility', 'N/A')}")
        sections.append(f"  Ingredient Ratio Check: {val.get('ingredient_ratio_check', 'N/A')}")
        sections.append(f"  Competitor Alignment: {val.get('competitor_alignment', 'N/A')}")
        sections.append(f"  Overall Confidence: {val.get('overall_confidence', 'N/A').upper()}")
        if val.get('flags'):
            sections.append("  Flags:")
            for flag in val.get('flags', []):
                sections.append(f"    ⚠️ {flag}")
    
    # Stage 5: Compliance
    sections.append("\n" + "=" * 80)
    sections.append("STAGE 5: COMPLIANCE CHECK")
    sections.append("=" * 80)
    
    compliance = wish_response.get("compliance", {})
    sections.append(f"\nOverall Status: {compliance.get('overall_status', 'N/A')}")
    
    # BIS Compliance
    if compliance.get('bis_compliance'):
        bis = compliance.get('bis_compliance', {})
        sections.append(f"\nBIS (India) Compliance: {bis.get('status', 'N/A')}")
        if bis.get('issues'):
            sections.append("  Issues:")
            for issue in bis.get('issues', []):
                sections.append(f"    • {issue}")
        if bis.get('warnings'):
            sections.append("  Warnings:")
            for warning in bis.get('warnings', []):
                sections.append(f"    • {warning}")
    
    # EU Compliance
    if compliance.get('eu_compliance'):
        eu = compliance.get('eu_compliance', {})
        sections.append(f"\nEU Compliance: {eu.get('status', 'N/A')}")
        if eu.get('warnings'):
            sections.append("  Warnings:")
            for warning in eu.get('warnings', []):
                if isinstance(warning, dict):
                    sections.append(f"    • {warning.get('ingredient', '')}: {warning.get('concern', '')}")
                else:
                    sections.append(f"    • {warning}")
    
    # FDA Compliance
    if compliance.get('fda_compliance'):
        fda = compliance.get('fda_compliance', {})
        sections.append(f"\nFDA (US) Compliance: {fda.get('status', 'N/A')}")
    
    # Required Warnings
    if compliance.get('required_warnings'):
        sections.append("\nRequired Warnings:")
        for warning in compliance.get('required_warnings', []):
            sections.append(f"  • {warning}")
    
    # Ingredient Status
    if compliance.get('ingredient_status'):
        sections.append("\nIngredient Compliance Status:")
        for ing_status in compliance.get('ingredient_status', []):
            sections.append(f"  {ing_status.get('ingredient', '')}:")
            sections.append(f"    BIS: {ing_status.get('bis', 'N/A')}")
            sections.append(f"    EU: {ing_status.get('eu', 'N/A')}")
            sections.append(f"    FDA: {ing_status.get('fda', 'N/A')}")
            sections.append(f"    Concentration: {ing_status.get('concentration', 'N/A')}")
            sections.append(f"    Limit: {ing_status.get('limit', 'N/A')}")
            sections.append(f"    Status: {ing_status.get('status', 'N/A')}")
    
    # Claims Guidance
    if compliance.get('claims_guidance'):
        claims = compliance.get('claims_guidance', {})
        sections.append("\nClaims Guidance:")
        if claims.get('allowed_claims'):
            sections.append("  Allowed Claims:")
            for claim in claims.get('allowed_claims', []):
                sections.append(f"    ✓ {claim}")
        if claims.get('claims_needing_substantiation'):
            sections.append("  Claims Needing Substantiation:")
            for claim in claims.get('claims_needing_substantiation', []):
                sections.append(f"    ⚠ {claim}")
        if claims.get('prohibited_claims'):
            sections.append("  Prohibited Claims:")
            for claim in claims.get('prohibited_claims', []):
                sections.append(f"    ✗ {claim}")
    
    # Recommendations
    if compliance.get('recommendations'):
        sections.append("\nCompliance Recommendations:")
        for rec in compliance.get('recommendations', []):
            sections.append(f"  • {rec}")
    
    # Metadata
    if wish_response.get('metadata'):
        sections.append("\n" + "=" * 80)
        sections.append("METADATA")
        sections.append("=" * 80)
        metadata = wish_response.get('metadata', {})
        if metadata.get('generated_at'):
            sections.append(f"Generated At: {metadata.get('generated_at', 'N/A')}")
        if metadata.get('processing_time'):
            sections.append(f"Processing Time: {metadata.get('processing_time', 'N/A')} seconds")
        if metadata.get('formula_version'):
            sections.append(f"Formula Version: {metadata.get('formula_version', 'N/A')}")
        if metadata.get('model_used'):
            sections.append(f"Model Used: {metadata.get('model_used', 'N/A')}")
        if metadata.get('stages_completed'):
            sections.append(f"Stages Completed: {', '.join(metadata.get('stages_completed', []))}")
    
    # History ID
    if wish_response.get('history_id'):
        sections.append(f"\nHistory ID: {wish_response.get('history_id', 'N/A')}")
    
    sections.append("\n" + "=" * 80)
    sections.append("END OF COMPREHENSIVE WISH DATA REPORT")
    sections.append("=" * 80)
    sections.append("\nThis presentation includes ALL data from the Make a Wish 5-stage pipeline:")
    sections.append("1. Complete wish requirements and preferences")
    sections.append("2. Full ingredient selection with all details")
    sections.append("3. Complete optimized formula with all percentages and analysis")
    sections.append("4. Comprehensive manufacturing process with all steps and guidelines")
    sections.append("5. Detailed cost analysis with all pricing recommendations")
    sections.append("6. Complete compliance check with all regulatory information")
    sections.append("7. All metadata and additional information")
    
    return "\n".join(sections)


# ============================================================================
# EXPORT ENDPOINTS
# ============================================================================

@router.post("/export-to-inspiration-board")
async def export_make_wish_to_board(
    request: dict,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """Export make a wish formulations to inspiration board"""
    try:
        # Extract user_id from JWT token (already verified by verify_jwt_token)
        user_id = current_user.get("user_id") or current_user.get("_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID not found in JWT token")
        
        board_id = request.get("board_id")
        history_ids = request.get("history_ids", [])
        
        if not board_id:
            raise HTTPException(status_code=400, detail="Board ID is required")
        
        if not history_ids:
            raise HTTPException(status_code=400, detail="At least one history ID is required")
        
        # Use the inspiration boards export endpoint
        from app.ai_ingredient_intelligence.models.inspiration_boards_schemas import (
            ExportToBoardRequest, ExportItemRequest
        )
        
        # Create export request
        export_request = ExportToBoardRequest(
            board_id=board_id,
            exports=[
                ExportItemRequest(
                    feature_type="make_wish",
                    history_ids=history_ids
                )
            ]
        )
        
        # Call the inspiration boards export endpoint
        from app.ai_ingredient_intelligence.api.inspiration_boards import export_to_board_endpoint
        result = await export_to_board_endpoint(export_request, background_tasks, current_user)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"ERROR exporting make a wish to board: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# MAIN ENDPOINTS
# ============================================================================


@router.post("/generate", response_model=MakeWishResponse)
async def generate_make_wish_formula(
    request: MakeWishRequest,
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Generate a cosmetic formulation using the complete 5-stage "Make a Wish" AI pipeline.
    
    AUTO-SAVE: Results are automatically saved to wish history if user is authenticated.
    Provide optional "name" and "tag" in request to customize the saved history item.
    
    REQUEST BODY:
    {
        "category": "skincare" or "haircare",
        "productType": "serum",
        "benefits": ["Brightening", "Hydration"],
        "exclusions": ["Silicone-free", "Paraben-free"],
        "heroIngredients": ["Niacinamide", "Hyaluronic Acid"],
        "costMin": 30,
        "costMax": 60,
        "texture": "lightweight",
        "claims": ["Vegan", "Dermatologist-tested"],
        "targetAudience": ["oily-skin", "young-adults"],
        "additionalNotes": "Additional requirements",
        "mode": "basic" or "advanced" (optional, default: "advanced"),
        "name": "Formula Name" (optional, for auto-saving),
        "tag": "optional-tag" (optional),
        "notes": "User notes" (optional),
        "history_id": "existing_history_id" (optional, to update existing history)
    }
    
    MODE OPTIONS:
    - "advanced" (default): Full 5-stage pipeline for formulators/scientists
    - "basic": Simplified flow for layman users with active ingredient options, business context, and simplified explanations
    
    RESPONSE:
    Complete formula with:
    - Ingredient selection
    - Optimized percentages
    - Manufacturing process
    - Cost analysis
    - Compliance check
    - history_id (if auto-saved)
    """
    start_time = time.time()
    
    # 🔹 Auto-save: Extract user info and required name/tag for history
    user_id_value = current_user.get("user_id") or current_user.get("_id")
    name = request.name.strip() if request.name else ""
    tag = request.tag
    notes = request.notes  # This is the notes field from MakeWishRequest (for history)
    provided_history_id = request.history_id
    history_id = None
    
    # Validate name is provided if auto-save is enabled (user_id is present) and no existing history_id
    if user_id_value and not provided_history_id and not name:
        raise HTTPException(status_code=400, detail="name is required for auto-save")
    
    # Validate history_id if provided
    if provided_history_id:
        try:
            if ObjectId.is_valid(provided_history_id):
                existing_item = await wish_history_col.find_one({
                    "_id": ObjectId(provided_history_id),
                    "user_id": user_id_value
                })
                if existing_item:
                    history_id = provided_history_id
                    print(f"[AUTO-SAVE] Using existing history_id: {history_id}")
                else:
                    print(f"[AUTO-SAVE] Warning: Provided history_id {provided_history_id} not found or doesn't belong to user, creating new one")
            else:
                print(f"[AUTO-SAVE] Warning: Invalid history_id format: {provided_history_id}, creating new one")
        except Exception as e:
            print(f"[AUTO-SAVE] Warning: Error validating history_id: {e}, creating new one")
    
    try:
        # Convert Pydantic model to dict (exclude autosave fields from wish_data)
        wish_data = request.model_dump(exclude={"name", "tag", "notes", "history_id"})
        
        # Validate required fields
        if not wish_data.get("productType"):
            raise HTTPException(
                status_code=400,
                detail="productType is required"
            )
        
        if not wish_data.get("benefits") or len(wish_data.get("benefits", [])) == 0:
            raise HTTPException(
                status_code=400,
                detail="At least one benefit is required"
            )
        
        # Set defaults
        wish_data.setdefault("category", "skincare")
        wish_data.setdefault("texture", "lightweight")
        wish_data.setdefault("exclusions", [])
        wish_data.setdefault("heroIngredients", [])
        wish_data.setdefault("claims", [])
        wish_data.setdefault("targetAudience", [])
        wish_data.setdefault("additionalNotes", "")
        wish_data.setdefault("mode", "advanced")  # Default to advanced mode
        
        # Validate mode
        mode = wish_data.get("mode", "advanced").lower()
        if mode not in ["basic", "advanced"]:
            raise HTTPException(
                status_code=400,
                detail="mode must be either 'basic' or 'advanced'"
            )
        wish_data["mode"] = mode
        
        if wish_data.get("costMin") is None:
            wish_data["costMin"] = 30
        if wish_data.get("costMax") is None:
            wish_data["costMax"] = 60
        
        # Validate cost range
        if wish_data["costMin"] >= wish_data["costMax"]:
            raise HTTPException(
                status_code=400,
                detail="costMax must be greater than costMin"
            )
        if wish_data["costMin"] < 0 or wish_data["costMax"] < 0:
            raise HTTPException(
                status_code=400,
                detail="Cost values must be positive"
            )
        
        # Validate using rules engine
        rules_engine = get_rules_engine()
        can_proceed, validation_results, fixed_wish_data = rules_engine.validate_wish_data(wish_data)
        
        if not can_proceed:
            blocking_errors = [r for r in validation_results if r.severity == ValidationSeverity.BLOCK]
            error_messages = [r.message for r in blocking_errors]
            raise HTTPException(
                status_code=400,
                detail=f"Validation failed: {'; '.join(error_messages)}"
            )
        
        # Use fixed wish data (with auto-selections applied)
        wish_data = fixed_wish_data
        
        # Log validation warnings
        warnings = [r for r in validation_results if r.severity == ValidationSeverity.WARN]
        if warnings:
            print(f"⚠️ Validation warnings: {len(warnings)}")
            for warning in warnings:
                print(f"   - {warning.message}")
        
        print(f"📝 Generating Make a Wish formula...")
        print(f"   Mode: {wish_data.get('mode', 'advanced').upper()}")
        print(f"   Category: {wish_data['category']}")
        print(f"   Product Type: {wish_data['productType']}")
        print(f"   Benefits: {', '.join(wish_data['benefits'])}")
        print(f"   Exclusions: {', '.join(wish_data.get('exclusions', []))}")
        print(f"   Hero Ingredients: {', '.join(wish_data.get('heroIngredients', []))}")
        print(f"   Cost Range: ₹{wish_data['costMin']} - ₹{wish_data['costMax']}/unit")
        
        # Create a unique identifier for the wish data to check for duplicates
        # Use a combination of key fields to identify similar wishes
        import json
        wish_data_for_comparison = {
            "category": wish_data.get("category"),
            "productType": wish_data.get("productType"),
            "benefits": sorted(wish_data.get("benefits", [])),
            "exclusions": sorted(wish_data.get("exclusions", [])),
            "heroIngredients": sorted(wish_data.get("heroIngredients", [])),
            "costMin": wish_data.get("costMin"),
            "costMax": wish_data.get("costMax"),
            "texture": wish_data.get("texture")
        }
        wish_data_hash = json.dumps(wish_data_for_comparison, sort_keys=True)
        
        # 🔹 Auto-save: Save initial state with "in_progress" status if user_id provided and no existing history_id
        if user_id_value and not history_id:
            try:
                # Check if a history item with the same wish data already exists for this user
                existing_history_item = await wish_history_col.find_one({
                    "user_id": user_id_value,
                    "wish_data_hash": wish_data_hash
                }, sort=[("created_at", -1)])  # Get the most recent one
                
                if existing_history_item:
                    history_id = str(existing_history_item["_id"])
                    print(f"[AUTO-SAVE] Found existing history item with same wish data, reusing history_id: {history_id}")
                else:
                    # Name is required - already validated above
                    # Truncate if too long
                    if len(name) > 100:
                        name = name[:100]
                    
                    # Save initial state
                    history_doc = {
                        "user_id": user_id_value,
                        "name": name,
                        "tag": tag,
                        "notes": notes,
                        "wish_data": wish_data,
                        "wish_data_hash": wish_data_hash,
                        "status": "in_progress",
                        "created_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()
                    }
                    result = await wish_history_col.insert_one(history_doc)
                    history_id = str(result.inserted_id)
                    print(f"[AUTO-SAVE] Saved initial state with history_id: {history_id}")
            except Exception as e:
                print(f"[AUTO-SAVE] Warning: Failed to save initial state: {e}")
                import traceback
                traceback.print_exc()
                # Continue with generation even if saving fails
        
        # Generate formula using 5-stage pipeline
        try:
            result = await generate_formula_from_wish(wish_data)
        except ValueError as ve:
            raise HTTPException(
                status_code=400,
                detail=f"Formula generation validation error: {str(ve)}"
            )
        except Exception as gen_error:
            print(f"❌ Error in generate_formula_from_wish: {gen_error}")
            import traceback
            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail=f"Error during formula generation: {str(gen_error)}"
            )
        
        # Validate response structure
        if not result or not isinstance(result, dict):
            raise HTTPException(
                status_code=500,
                detail="Invalid formula structure returned"
            )
        
        processing_time = time.time() - start_time
        print(f"✅ Make a Wish formula generated in {processing_time:.2f}s")
        
        # Extract key metrics
        optimized = result.get("optimized_formula", {})
        cost_analysis = result.get("cost_analysis", {})
        compliance = result.get("compliance", {})
        
        print(f"   Formula Cost: ₹{cost_analysis.get('raw_material_cost', {}).get('total_per_100g', 0)}/unit")
        print(f"   Compliance: {compliance.get('overall_status', 'UNKNOWN')}")
        print(f"   Ingredients: {len(optimized.get('ingredients', []))}")
        
        # 🔹 Auto-save: Update history with "completed" status and formula_result
        if user_id_value and history_id:
            try:
                update_doc = {
                    "formula_result": result,
                    "status": "completed",
                    "updated_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()
                }
                
                await wish_history_col.update_one(
                    {"_id": ObjectId(history_id), "user_id": user_id_value},
                    {"$set": update_doc}
                )
                print(f"[AUTO-SAVE] Updated history {history_id} with completed status and formula result")
            except Exception as e:
                print(f"[AUTO-SAVE] Warning: Failed to update history: {e}")
                import traceback
                traceback.print_exc()
                # Don't fail the response if saving fails
        elif user_id_value and name:
            # Create new history item if we didn't have history_id but have name
            try:
                if len(name) > 100:
                    name = name[:100]
                
                history_doc = {
                    "user_id": user_id_value,
                    "name": name,
                    "tag": tag,
                    "notes": notes,
                    "wish_data": wish_data,
                    "wish_data_hash": wish_data_hash,
                    "formula_result": result,
                    "status": "completed",
                    "created_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()
                }
                result_insert = await wish_history_col.insert_one(history_doc)
                history_id = str(result_insert.inserted_id)
                print(f"[AUTO-SAVE] Created new history {history_id} with completed status and formula result")
            except Exception as e:
                print(f"[AUTO-SAVE] Warning: Failed to create history: {e}")
                import traceback
                traceback.print_exc()
                # Don't fail the response if saving fails
        
        # Add history_id to result if available
        if history_id:
            result["history_id"] = history_id
        
        # Return response
        return MakeWishResponse(**result)
    
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid request data: {str(e)}"
        )
    except Exception as e:
        print(f"❌ Unexpected error generating Make a Wish formula: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


# ============================================================================
# PPT GENERATION ENDPOINT
# ============================================================================

class GeneratePPTRequest(BaseModel):
    """Request schema for PPT generation - accepts either history_id or full wish data"""
    history_id: Optional[str] = Field(default=None, description="History ID to fetch wish data from database")
    wish_data: Optional[Dict[str, Any]] = Field(default=None, description="Full wish data object")
    ingredient_selection: Optional[Dict[str, Any]] = Field(default=None, description="Ingredient selection data")
    optimized_formula: Optional[Dict[str, Any]] = Field(default=None, description="Optimized formula data")
    manufacturing: Optional[Dict[str, Any]] = Field(default=None, description="Manufacturing process data")
    cost_analysis: Optional[Dict[str, Any]] = Field(default=None, description="Cost analysis data")
    compliance: Optional[Dict[str, Any]] = Field(default=None, description="Compliance data")
    
    class Config:
        extra = "allow"  # Allow additional fields
        # Make all fields truly optional
        json_schema_extra = {
            "example": {
                "history_id": "507f1f77bcf86cd799439011"
            }
        }


@router.post("/generate-ppt", response_model=None)
async def generate_wish_ppt(
    request: GeneratePPTRequest = Body(...),
    current_user: dict = Depends(verify_jwt_token)  # JWT token validation
):
    """
    Generate PowerPoint presentation from Make a Wish data using Gamma API.
    
    REQUEST BODY (either option):
    1. Using history_id:
       {
           "history_id": "mongodb_object_id_here"
       }
    
    2. Using full wish data:
       {
           "wish_data": {...},
           "ingredient_selection": {...},
           "optimized_formula": {...},
           "manufacturing": {...},
           "cost_analysis": {...},
           "compliance": {...}
       }
    
    RESPONSE:
    {
        "success": true,
        "presentation_id": "gamma_presentation_id",
        "download_url": "https://...",
        "edit_url": "https://...",
        "message": "Presentation generated successfully"
    }
    """
    print(f"\n{'='*80}")
    print(f"[DEBUG] 🚀 API CALL: /api/make-wish/generate-ppt")
    print(f"[DEBUG] Request received at: {datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()}")
    print(f"[DEBUG] Request type: {type(request)}")
    print(f"[DEBUG] Request keys: {list(request.keys()) if isinstance(request, dict) else 'N/A'}")
    print(f"{'='*80}\n")
    
    try:
        # Validate request is a dict
        if not isinstance(request, dict):
            raise HTTPException(
                status_code=400,
                detail=f"Request body must be a JSON object. Got: {type(request).__name__}"
            )
        
        # Validate request is not empty
        if not request:
            raise HTTPException(
                status_code=400,
                detail="Request body cannot be empty. Provide either 'history_id' or wish data fields."
            )
        
        # Check if Gamma API key is configured
        if not GAMMA_API_KEY:
            print(f"[DEBUG] ❌ Error: GAMMA_API_KEY not set")
            raise HTTPException(
                status_code=500,
                detail="GAMMA_API_KEY environment variable not set. Please configure it in your .env file."
            )
        
        # Extract user_id from JWT token
        user_id_value = current_user.get("user_id") or current_user.get("_id")
        if not user_id_value:
            raise HTTPException(status_code=400, detail="User ID not found in JWT token")
        
        # Get wish data - either from history_id or request body
        wish_response_data = None
        
        # Convert Pydantic model to dict for easier handling
        request_dict = request.model_dump(exclude_none=True)
        
        if request.history_id:
            # Fetch from database
            history_id = request.history_id
            if not history_id:
                raise HTTPException(status_code=400, detail="history_id is required when provided")
            
            # Validate ObjectId
            if not ObjectId.is_valid(history_id):
                raise HTTPException(
                status_code=400,
                detail=f"Invalid history_id format. Expected MongoDB ObjectId, got: {history_id[:50]}"
            )
            
            # Fetch from database
            history_doc = await wish_history_col.find_one({
                "_id": ObjectId(history_id),
                "user_id": user_id_value
            })
            
            if not history_doc:
                raise HTTPException(
                    status_code=404,
                    detail=f"History item not found or doesn't belong to user"
                )
            
            # Extract wish response data from history
            # Check if it's the new format (formula_data) or old format (formula_result)
            if "formula_data" in history_doc:
                # New format (revised make wish)
                wish_response_data = {
                    "wish_data": history_doc.get("wish_data", {}),
                    "ingredient_selection": history_doc.get("formula_data", {}).get("ingredient_selection", {}),
                    "optimized_formula": history_doc.get("formula_data", {}).get("optimized_formula", {}),
                    "manufacturing": history_doc.get("formula_data", {}).get("manufacturing", {}),
                    "cost_analysis": history_doc.get("formula_data", {}).get("cost_analysis", {}),
                    "compliance": history_doc.get("formula_data", {}).get("compliance", {})
                }
            elif "formula_result" in history_doc:
                # Old format (make wish)
                wish_response_data = history_doc.get("formula_result", {})
            else:
                raise HTTPException(
                    status_code=400,
                    detail="History item does not contain formula data. Please generate a formula first."
                )
            
            print(f"[DEBUG] ✅ Fetched wish data from history_id: {history_id}")
        
        elif request.wish_data or request.ingredient_selection:
            # Use data from request body directly
            wish_response_data = {
                "wish_data": request.wish_data or {},
                "ingredient_selection": request.ingredient_selection or {},
                "optimized_formula": request.optimized_formula or {},
                "manufacturing": request.manufacturing or {},
                "cost_analysis": request.cost_analysis or {},
                "compliance": request.compliance or {}
            }
            print(f"[DEBUG] ✅ Using wish data from request body")
        
        else:
            raise HTTPException(
                status_code=400,
                detail="Either 'history_id' or wish data fields ('wish_data', 'ingredient_selection', etc.) must be provided"
            )
        
        # Validate that we have at least some data
        if not wish_response_data or not wish_response_data.get("wish_data"):
            raise HTTPException(
                status_code=400,
                detail="Invalid wish data. Missing required fields."
            )
        
        # Step 1: Format wish data as structured text
        print(f"[DEBUG] 📝 Formatting wish data for Claude analysis...")
        formatted_wish_data = format_wish_data_for_gamma(wish_response_data)
        
        # Step 2: Send to Claude to generate business strategy presentation prompt
        print(f"[DEBUG] 🤖 Sending wish data to Claude to generate business strategy prompt...")
        
        business_strategy_prompt = None
        if CLAUDE_AVAILABLE and claude_client:
            try:
                claude_system_prompt = """You are a business strategy consultant specializing in cosmetic product development and commercialization. 
Your task is to analyze cosmetic formulation data and create a comprehensive business strategy presentation prompt for Gamma API.

The presentation should be at a BUSINESS STRATEGY LEVEL, focusing on:
- Market opportunity and positioning
- Business model and revenue projections
- Go-to-market strategy
- Competitive analysis and differentiation
- Investment requirements and ROI
- Risk assessment and mitigation
- Timeline and milestones
- Success metrics and KPIs

Create a detailed, professional prompt that will guide Gamma API to generate a business strategy presentation suitable for:
- Investors and stakeholders
- Business executives
- Strategic planning sessions
- Product launch planning

The prompt should be clear, structured, and include all necessary instructions for creating a compelling business strategy presentation."""

                claude_user_prompt = f"""Analyze the following cosmetic formulation data and create a comprehensive business strategy presentation prompt for Gamma API.

FORMULATION DATA:
{formatted_wish_data}

Your task:
1. Extract key business insights from the formulation data
2. Identify market opportunities and positioning
3. Highlight competitive advantages
4. Note cost structure and pricing strategy
5. Identify compliance and regulatory considerations
6. Create a detailed prompt for Gamma API that will generate a business strategy presentation

The prompt should:
- Be written in clear, professional language
- Include specific instructions for slide structure
- Emphasize business strategy, market positioning, and commercialization
- Include data visualization requirements
- Specify the target audience (investors, executives, stakeholders)
- Request executive summary, market analysis, financial projections, go-to-market strategy, and risk assessment

Return ONLY the prompt text that should be sent to Gamma API's additionalInstructions field. Do not include any explanations or meta-commentary."""

                claude_response = claude_client.messages.create(
                    model=claude_model,
                    max_tokens=4096,
                    temperature=0.3,
                    system=claude_system_prompt,
                    messages=[
                        {"role": "user", "content": claude_user_prompt}
                    ]
                )
                
                if claude_response.content and len(claude_response.content) > 0:
                    business_strategy_prompt = claude_response.content[0].text.strip()
                    print(f"[DEBUG] ✅ Claude generated business strategy prompt ({len(business_strategy_prompt)} characters)")
                else:
                    print(f"[DEBUG] ⚠️ Claude returned empty response, using default prompt")
                    business_strategy_prompt = None
                    
            except Exception as claude_error:
                print(f"[DEBUG] ⚠️ Claude prompt generation failed: {claude_error}")
                import traceback
                traceback.print_exc()
                business_strategy_prompt = None
        else:
            print(f"[DEBUG] ⚠️ Claude client not available, using default prompt")
        
        # Step 3: Prepare Gamma API request with Claude-generated prompt or default
        if business_strategy_prompt:
            additional_instructions = business_strategy_prompt
            print(f"[DEBUG] 📊 Using Claude-generated business strategy prompt")
        else:
            # Fallback to default business strategy prompt
            additional_instructions = (
                "Create a comprehensive BUSINESS STRATEGY presentation for a cosmetic product launch. "
                "Focus on business strategy, market positioning, and commercialization rather than technical formulation details. "
                "\n\nPRESENTATION STRUCTURE:\n"
                "1. Executive Summary - Product vision, market opportunity, key value propositions\n"
                "2. Market Analysis - Target market, size, growth trends, customer segments\n"
                "3. Competitive Positioning - Competitive landscape, differentiation strategy, unique selling points\n"
                "4. Business Model - Revenue streams, pricing strategy, distribution channels\n"
                "5. Financial Projections - Cost structure, pricing analysis, revenue forecasts, ROI projections\n"
                "6. Go-to-Market Strategy - Launch plan, marketing strategy, sales channels, partnerships\n"
                "7. Risk Assessment - Market risks, regulatory risks, mitigation strategies\n"
                "8. Timeline & Milestones - Product development timeline, launch schedule, key milestones\n"
                "9. Success Metrics - KPIs, success criteria, measurement framework\n"
                "10. Investment Requirements - Funding needs, resource requirements, budget allocation\n\n"
                "TONE: Professional, strategic, investor-ready\n"
                "AUDIENCE: Business executives, investors, stakeholders, strategic planners\n"
                "STYLE: Use data visualizations, charts, tables, and compelling visuals\n"
                "FOCUS: Business strategy, market opportunity, commercialization, ROI, competitive advantage"
            )
            print(f"[DEBUG] 📊 Using default business strategy prompt")
        
        gamma_request_payload = {
            "inputText": formatted_wish_data,
            "format": "presentation",
            "exportAs": "pptx",
            "textMode": "generate",
            "tone": "professional, strategic, business-focused, investor-ready",
            "audience": "business executives, investors, stakeholders, strategic planners, C-level executives",
            "amount": "comprehensive",
            "language": "en",
            "numCards": 25,  # More slides for comprehensive business strategy
            "additionalInstructions": additional_instructions
        }
        
        print(f"[DEBUG] 🚀 Calling Gamma API...")
        print(f"[DEBUG] Formatted text length: {len(formatted_text)} characters")
        
        # Call Gamma API
        async with httpx.AsyncClient(timeout=300.0) as client:
            try:
                response = await client.post(
                    GAMMA_GENERATE_ENDPOINT,
                    headers={
                        "X-API-KEY": GAMMA_API_KEY,
                        "Content-Type": "application/json"
                    },
                    json=gamma_request_payload
                )
                
                print(f"[DEBUG] Gamma API Response Status: {response.status_code}")
                
                if response.status_code not in [200, 201]:
                    error_text = response.text
                    try:
                        error_json = response.json()
                        error_text = str(error_json)
                    except:
                        pass
                    
                    print(f"[DEBUG] ❌ Gamma API Error: {error_text}")
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Gamma API error: {error_text}"
                    )
                
                # Parse response
                try:
                    gamma_response = response.json()
                except Exception as e:
                    print(f"[DEBUG] ❌ Failed to parse Gamma API response: {e}")
                    raise HTTPException(
                        status_code=500,
                        detail=f"Gamma API returned invalid JSON: {response.text[:200]}"
                    )
                
                print(f"[DEBUG] ✅ Gamma API Response: {gamma_response}")
                
                # Extract presentation details
                # Note: Gamma API response structure may vary - adjust based on actual API response
                presentation_id = gamma_response.get("presentation_id") or gamma_response.get("id")
                download_url = gamma_response.get("download_url") or gamma_response.get("url") or gamma_response.get("file_path")
                edit_url = gamma_response.get("edit_url") or gamma_response.get("edit_path")
                
                if not presentation_id:
                    # If no presentation_id, try to extract from other fields
                    presentation_id = gamma_response.get("generation_id") or "unknown"
                
                if not download_url:
                    print(f"[DEBUG] ⚠️ Warning: No download_url in Gamma response. Full response: {gamma_response}")
                    # Some APIs return the file directly or use a different structure
                    download_url = gamma_response.get("file") or gamma_response.get("presentation_url")
                
                return {
                    "success": True,
                    "presentation_id": presentation_id,
                    "download_url": download_url,
                    "edit_url": edit_url,
                    "message": "Presentation generated successfully",
                    "gamma_response": gamma_response  # Include full response for debugging
                }
                
            except httpx.TimeoutException:
                raise HTTPException(
                    status_code=504,
                    detail="Gamma API request timed out. Please try again."
                )
            except httpx.RequestError as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Error connecting to Gamma API: {str(e)}"
                )
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Unexpected error generating PPT: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

