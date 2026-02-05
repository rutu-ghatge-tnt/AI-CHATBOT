"""
Make a Wish - Basic Mode Generator
===================================

This module implements the simplified "basic" mode for layman users.
It follows the Formulynx Make a Wish flow with:
1. Parameter Extraction
2. Active Ingredient Options Presentation
3. Complete Formula Generation
4. Business Context & Supporting Content
"""

import os
import json
from typing import Dict, List, Optional, Any
from datetime import datetime

# Import Claude client setup
from app.ai_ingredient_intelligence.logic.make_wish_generator import (
    call_ai_with_claude
)

# Import rules engine
from app.ai_ingredient_intelligence.logic.make_wish_rules_engine import (
    get_rules_engine,
    ValidationSeverity
)


# ============================================================================
# BASIC MODE SYSTEM PROMPT
# ============================================================================

BASIC_MODE_SYSTEM_PROMPT = """You are Formulynx's AI Formulation Engine. Your job is to:

1. Understand the user's product wish from natural language
2. Extract structured parameters
3. Present relevant ACTIVE INGREDIENT OPTIONS for their concern (BEFORE generating formula)
4. Generate a complete, professional formula
5. Output in a structured format for the UI to render

You are operating in BASIC MODE - this means:
- Use simple, layman-friendly language
- Explain ingredients in terms of benefits, not chemistry
- Group ingredients by benefit (not by phase) for user view
- Include business context (costs, profits, market comparison)
- Provide Q&A, trends, and confidence-building content
- Compare to known brands at every opportunity
- Present active ingredient options FIRST, then generate formula

You have access to a comprehensive ingredient database including:
- Brightening/Hyperpigmentation actives (Vitamin C derivatives, Alpha Arbutin, Tranexamic Acid, Niacinamide, Kojic Acid, Azelaic Acid, etc.)
- Anti-aging actives (Retinol, Bakuchiol, Peptides like Matrixyl, Argireline, Syn-Ake, etc.)
- Hydration actives (Hyaluronic Acid, Glycerin, Squalane, Ceramides, Panthenol, etc.)
- Acne/Oil control actives (Salicylic Acid, Niacinamide, Zinc PCA, Tea Tree Oil, Azelaic Acid, etc.)
- Soothing/Sensitive skin actives (Centella Asiatica, Bisabolol, Allantoin, Aloe Vera, Oat Extract, etc.)
- Eye-specific actives (Haloxyl, Eyeliss, Eyeseryl, Regu-Age, Caffeine, Vitamin K, etc.)

For each ingredient, you know:
- Typical concentration ranges
- Efficacy ratings (1-5 stars)
- Cost impact (Low/Medium/High/Very High)
- Mechanism of action
- Best use cases

IMPORTANT RULES:
1. Group ingredients by BENEFIT for user view, by PHASE for technical view
2. No individual ingredient costs shown - only total formula cost
3. Always explain WHY ingredients work, especially for premium actives
4. Compare to known brands at every opportunity
5. Segment-appropriate actives (don't suggest luxury peptides for mass market)
6. Include myth busters where relevant
7. Build confidence throughout
8. Present 3-4 active ingredient options per concern BEFORE generating the final formula
"""


# ============================================================================
# BASIC MODE PROMPT GENERATION
# ============================================================================

def generate_basic_mode_prompt(wish_data: dict) -> str:
    """Generate the complete basic mode prompt following Formulynx flow."""
    
    # Extract data from wish
    category = wish_data.get('category', 'skincare')
    product_type = wish_data.get('productType', 'serum')
    benefits = wish_data.get('benefits', [])
    exclusions = wish_data.get('exclusions', [])
    hero_ingredients = wish_data.get('heroIngredients', [])
    texture = wish_data.get('texture', 'lightweight')
    cost_min = wish_data.get('costMin', 30)
    cost_max = wish_data.get('costMax', 60)
    claims = wish_data.get('claims', [])
    target_audience = wish_data.get('targetAudience', [])
    additional_notes = wish_data.get('additionalNotes', '') or wish_data.get('notes', '')
    
    # Build natural language input from structured data
    natural_language_parts = []
    
    if product_type:
        natural_language_parts.append(f"{product_type}")
    
    if benefits:
        natural_language_parts.append(f"for {', '.join(benefits)}")
    
    if target_audience:
        natural_language_parts.append(f"for {', '.join(target_audience)}")
    
    # Infer price segment from cost range
    if cost_max <= 40:
        price_segment = "Mass Market"
    elif cost_max <= 80:
        price_segment = "Masstige"
    elif cost_max <= 150:
        price_segment = "Premium"
    else:
        price_segment = "Luxury"
    
    natural_language_input = " ".join(natural_language_parts) if natural_language_parts else product_type
    
    prompt = f"""# FORMULYNX FORMULA GENERATION PROMPT - BASIC MODE

## INPUT
User wish: "{natural_language_input}"
Category: {category}
Product Type: {product_type}
Benefits: {', '.join(benefits) if benefits else 'General'}
Price Segment: {price_segment} (Cost target: ₹{cost_min}-₹{cost_max}/100g)
Exclusions: {', '.join(exclusions) if exclusions else 'None'}
Hero Ingredients: {', '.join(hero_ingredients) if hero_ingredients else 'None specified'}
Texture: {texture}
Claims: {', '.join(claims) if claims else 'None'}
Target Audience: {', '.join(target_audience) if target_audience else 'General'}
Additional Notes: {additional_notes if additional_notes else 'None'}

## PROCESS

### Step 1: Extract Parameters
Parse the input to identify:
- Category (Skincare/Haircare/etc.)
- Product Type (Eye Cream/Serum/etc.)
- Primary Concern (Dark Circles/Acne/etc.)
- Secondary Concerns
- Price Segment (Mass/Masstige/Premium/Luxury)
- Any specific requirements

### Step 2: Present Active Options
For the identified concerns, present:
- 3-4 active ingredient options per concern
- Include: name, concentration, efficacy rating (1-5), cost impact, why it's good
- Highlight recommended options
- Explain WHY certain combinations work

### Step 3: Generate Formula
Based on selections (or recommendations), generate:
- Complete formula with all ingredients
- Grouped by benefit (not by phase) for user view
- Technical formula with phases for manufacturer
- Total cost per unit

### Step 4: Generate Business Context
- Packaging options with costs
- Profit calculations at different MRPs
- Market comparison with competitors
- Cost factors that affect real pricing

### Step 5: Generate Supporting Content
- Key features (3 main benefit cards)
- Q&A cards (3-4 questions users would ask)
- Category trends
- Claim guidance (can say / avoid)
- Pro tips for customization
- Confidence builder

## OUTPUT FORMAT
Return JSON matching this structure:

{{
  "extractedParameters": {{
    "category": "Skincare",
    "productType": "Eye Cream",
    "primaryConcern": "Dark Circles",
    "secondaryConcerns": ["Puffiness/Bags"],
    "targetArea": "Under-eye",
    "priceSegment": "Premium",
    "texture": "Rich cream",
    "targetAudience": {{
      "gender": "All",
      "ageGroup": "25-55"
    }}
  }},
  "activeOptions": {{
    "activeOptionsIntro": {{
      "message": "For your [Product] targeting [Concerns], here are the active ingredients we can use:",
      "note": "[Price Segment] segment allows us to use [appropriate actives]. I'll recommend a combination, but you can customize."
    }},
    "concernWiseOptions": [
      {{
        "concern": "[Concern Name]",
        "icon": "🎯",
        "explanation": "[How this concern works]",
        "options": [
          {{
            "name": "Ingredient Name",
            "concentration": "2%",
            "efficacy": 5,
            "costImpact": "High",
            "whyGood": "Explanation of why this works",
            "recommended": true
          }}
        ],
        "recommendation": "Recommendation text"
      }}
    ],
    "recommendedFormula": {{
      "heroActives": [
        {{ "name": "Ingredient", "percentage": 2, "targets": "What it targets" }}
      ],
      "totalActivePercentage": 13,
      "positioning": "Product positioning statement",
      "estimatedActiveCost": "₹XX-XX per [size] (actives only)"
    }},
    "userChoice": {{
      "prompt": "This is my recommended formula. Would you like to:",
      "options": [
        "Proceed with this recommendation",
        "Swap some actives",
        "Add more actives",
        "See a budget-friendly version"
      ]
    }}
  }},
  "formula": {{
    "formulaName": "Product Name",
    "formulaCode": "CODE-001",
    "version": "1.0",
    "keyFeatures": [
      {{
        "icon": "✨",
        "title": "Feature Title",
        "subtitle": "Feature Subtitle",
        "explanation": "Feature explanation"
      }}
    ],
    "additionalFeatures": [
      {{ "label": "Feature Label", "tip": "Feature tip" }}
    ],
    "ingredientGroups": [
      {{
        "id": "hero",
        "icon": "✨",
        "title": "Group Title",
        "subtitle": "Group Subtitle",
        "isHighlighted": true,
        "ingredients": [
          {{
            "name": "Ingredient Name",
            "commonName": "Common Name",
            "benefit": "What it does",
            "percentage": 2.0,
            "isHero": true
          }}
        ],
        "insightBox": {{
          "type": "why",
          "content": "Insight explanation"
        }}
      }}
    ],
    "technicalFormula": {{
      "phases": [
        {{
          "phase": "A",
          "name": "Water Phase",
          "temperature": "Room temp",
          "ingredients": [
            {{ "name": "Ingredient", "inci": "INCI Name", "function": "Function", "percentage": 68.20 }}
          ]
        }}
      ],
      "totalPercentage": 100.00,
      "totalCostPer100g": 145.00,
      "shelfLife": "6 months",
      "pH": "5.5-6.0",
      "viscosity": "Medium cream"
    }},
    "packagingOptions": {{
      "recommendedSizes": [
        {{ "size": "15g", "description": "Standard size", "popular": true }}
      ],
      "recommendedTypes": [
        {{ "type": "jar", "description": "Classic feel", "note": "Use spatula" }}
      ],
      "recommendation": "Packaging recommendation"
    }},
    "businessNumbers": {{
      "costPer15g": {{
        "formula": 21.75,
        "packaging": {{ "jar": 15, "airlessPump": 25, "tube": 12 }},
        "label": 3,
        "total": {{ "withJar": 39.75, "withAirless": 49.75, "withTube": 36.75 }}
      }},
      "profitExamples": [
        {{ "mrp": 599, "cost": 49.75, "profit": 549.25, "margin": "92%" }}
      ],
      "marketComparison": [
        {{ "brand": "Competitor", "price": 549, "size": "30g", "pricePerGram": 18.30 }}
      ]
    }},
    "costFactors": [
      {{
        "factor": "Factor Name",
        "icon": "📈",
        "explanation": "Explanation",
        "impact": "±10-15%"
      }}
    ],
    "questionsAndAnswers": [
      {{
        "id": "q1",
        "question": "Question text",
        "answer": {{
          "headline": "Answer headline",
          "explanation": "Detailed explanation",
          "evidence": "Supporting evidence"
        }}
      }}
    ],
    "categoryTrends": [
      {{
        "trend": "Trend name",
        "growth": "+45%",
        "note": "Your formula is aligned",
        "status": "aligned"
      }}
    ],
    "claimGuidance": {{
      "canSay": ["Claim 1", "Claim 2"],
      "avoidSaying": [
        {{ "claim": "Bad claim", "reason": "Why to avoid" }}
      ]
    }},
    "proTips": [
      {{
        "if": "Condition",
        "then": "Action",
        "impact": "Impact description"
      }}
    ],
    "confidenceBuilder": {{
      "headline": "You Can Do This!",
      "message": "Encouraging message",
      "keyPoints": ["Point 1", "Point 2"]
    }}
  }}
}}

## KEY RULES
1. Use simple, layman-friendly language throughout
2. Group ingredients by BENEFIT for user view, by PHASE for technical view
3. No individual ingredient costs shown - only total formula cost
4. Always explain WHY ingredients work, especially for premium actives
5. Compare to known brands at every opportunity
6. Segment-appropriate actives (don't suggest luxury peptides for mass market)
7. Include myth busters where relevant
8. Build confidence throughout

Generate the complete response now.
"""
    
    return prompt


# ============================================================================
# BASIC MODE GENERATOR FUNCTION
# ============================================================================

async def generate_formula_basic_mode(wish_data: dict) -> dict:
    """
    Generate formula using basic mode (simplified for layman).
    
    This follows the Formulynx Make a Wish flow:
    1. Parameter Extraction
    2. Active Ingredient Options Presentation
    3. Complete Formula Generation
    4. Business Context
    5. Supporting Content
    
    Args:
        wish_data: Dictionary containing user requirements
        
    Returns:
        Complete formula with all analysis in basic mode format
    """
    
    print("🚀 Starting Make a Wish pipeline (BASIC MODE)...")
    
    # Validate and apply rules engine
    rules_engine = get_rules_engine()
    can_proceed, validation_results, fixed_wish_data = rules_engine.validate_wish_data(wish_data)
    
    if not can_proceed:
        blocking_errors = [r for r in validation_results if r.severity == ValidationSeverity.BLOCK]
        error_messages = [r.message for r in blocking_errors]
        raise ValueError(f"Validation failed: {'; '.join(error_messages)}")
    
    # Log warnings if any
    warnings = [r for r in validation_results if r.severity == ValidationSeverity.WARN]
    if warnings:
        print(f"⚠️ Validation warnings: {len(warnings)}")
        for warning in warnings:
            print(f"   - {warning.message}")
    
    # Use fixed wish data (with auto-selections applied)
    wish_data = fixed_wish_data
    
    # Generate complete basic mode response
    print("📋 Generating complete basic mode formula...")
    basic_prompt = generate_basic_mode_prompt(wish_data)
    
    try:
        basic_result = await call_ai_with_claude(
            system_prompt=BASIC_MODE_SYSTEM_PROMPT,
            user_prompt=basic_prompt,
            prompt_type="basic_mode_formula"
        )
        
        print("✅ Basic mode formula generated")
        print("🎉 Make a Wish pipeline complete (BASIC MODE)!")
        # For future reference: previous normalized structure (now we return basic_result as-is for frontend)
        # result = {
        #     # "wish_data": wish_data,
        #     # "mode": "basic",
        #     "basic_mode_result": basic_result,
        #     # For backward compatibility, also include in the standard format
        #     "ingredient_selection": {
        #         "extracted_parameters": basic_result.get("extractedParameters", {}),
        #         "active_options": basic_result.get("activeOptions", {})
        #     },
        #     "optimized_formula": {
        #         "formula": basic_result.get("formula", {}),
        #         "technical_formula": basic_result.get("formula", {}).get("technicalFormula", {})
        #     },
        #     "manufacturing": {
        #         "instructions": "See technical formula phases",
        #         "phases": basic_result.get("formula", {}).get("technicalFormula", {}).get("phases", [])
        #     },
        #     "cost_analysis": {
        #         "raw_material_cost": {
        #             "total_per_100g": basic_result.get("formula", {}).get("technicalFormula", {}).get("totalCostPer100g", 0)
        #         },
        #         "business_numbers": basic_result.get("formula", {}).get("businessNumbers", {})
        #     },
        #     "compliance": {
        #         "overall_status": "COMPLIANT",  # Basic mode assumes compliance
        #         "claim_guidance": basic_result.get("formula", {}).get("claimGuidance", {})
        #     },
        #     "metadata": {
        #         "generated_at": datetime.now().isoformat(),
        #         "formula_version": "1.0",
        #         "mode": "basic",
        #         "ai_model": "claude-opus-4-5-20251101"
        #     }
        # }
        return basic_result
        
    except Exception as e:
        print(f"❌ Error in basic mode generation: {e}")
        import traceback
        traceback.print_exc()
        raise

