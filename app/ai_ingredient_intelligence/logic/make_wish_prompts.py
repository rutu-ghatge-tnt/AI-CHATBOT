"""
Make A Wish - AI Prompts (Consolidated)
========================================

This module contains all AI prompts for the Make A Wish feature:
- Revised flow prompts (parse wish, ingredient selection, optimization, insights, alternatives)
- Basic mode prompt (Formulynx-style comprehensive prompt)

All prompts are organized in one place for clarity and maintainability.
"""

# ============================================================================
# REVISED FLOW PROMPTS
# ============================================================================

# STAGE 1: PARSE WISH PROMPT
PARSE_WISH_PROMPT = """
Parse this cosmetic wish and return JSON:

Wish: {wish_text}

Return ONLY valid JSON with this structure:
{{
    "category": "skincare",
    "product_type": {{
        "id": "serum",
        "name": "Serum",
        "icon": "flask",
        "confidence": 0.95
    }},
    "detected_ingredients": [
        {{"name": "Vitamin C", "confidence": 0.9, "has_alternatives": true}}
    ],
    "detected_benefits": ["brightening"],
    "detected_exclusions": ["paraben-free"],
    "detected_skin_types": [],
    "detected_hair_concerns": [],
    "auto_texture": {{
        "id": "watery",
        "label": "Light & Fast-Absorbing",
        "auto_selected": true
    }},
    "needs_clarification": [],
    "compatibility_issues": []
}}

Analyze the wish and fill in actual values. Return only JSON.
"""

# STAGE 2: INGREDIENT SELECTION WITH COMPLEXITY
INGREDIENT_SELECTION_COMPLEXITY_PROMPT = """
Select {max_ingredients} ingredients for {complexity} {product_type} with {active_slots} hero actives.

Requirements: {benefits}, {exclusions}, {texture}
Base: {base_ingredients}

Return JSON:
{{
    "selected_ingredients": [
        {{
            "id": "vitamin_c",
            "inci_name": "Ascorbic Acid",
            "display_name": "Vitamin C",
            "icon": "flask",
            "percentage_range": "10-15%",
            "phase": "C",
            "purpose": "brightening",
            "is_hero": true,
            "is_base": false,
            "has_alternatives": true
        }}
    ],
    "selection_summary": {{
        "total_ingredients": {max_ingredients},
        "hero_actives": {active_slots},
        "complexity_compliance": true
    }}
}}

Be concise.
"""

# STAGE 3: FORMULA OPTIMIZATION (REVISED)
FORMULA_OPTIMIZATION_REVISED_PROMPT = """
Optimize {product_type} ({texture}) formula to 100%:

{ingredients_list}

Rules: Total 100%, Water 60-80%, Preservative 1%, pH adjuster 0.2%

Return JSON:
{{
    "optimized_formula": {{
        "name": "Formula Name",
        "complexity": "{complexity}",
        "total_percentage": 100.0
    }},
    "ingredients": [
        {{
            "id": "water",
            "name": "Water",
            "inci": "Aqua",
            "percentage": "70.00%",
            "phase": "A",
            "function": "solvent",
            "is_hero": false,
            "is_base": true
        }}
    ]
}}

Be fast.
"""

# STAGE 4: INSIGHTS GENERATION
INSIGHTS_GENERATION_PROMPT = """
Generate insights for {formula_name} ({product_type}) with {complexity} complexity.

Key ingredients: {key_ingredients}
Benefits: {benefits}

Return JSON:
{{
    "why_these_ingredients": [
        {{
            "ingredient_name": "Ingredient Name",
            "icon": "flask",
            "explanation": "Why chosen",
            "complexity_reason": "Why for {complexity}"
        }}
    ],
    "challenges": [
        {{
            "title": "Challenge Title",
            "icon": "alert-triangle",
            "description": "What to expect",
            "tip": "How to handle",
            "severity": "info|attention"
        }}
    ],
    "marketing_tips": [
        {{
            "title": "Tip Title",
            "icon": "lightbulb",
            "content": "Actionable advice",
            "category": "positioning|pricing|targeting"
        }}
    ],
    "faq": [
        {{
            "question": "Common question",
            "answer": "Clear answer"
        }}
    ]
}}

Be practical and marketing-focused.
"""

# STAGE 5: ALTERNATIVES ANALYSIS
ALTERNATIVES_ANALYSIS_PROMPT = """
Analyze alternatives for {ingredient_name} in {product_type} ({complexity} complexity).

Current: {current_variant}
Available alternatives:
{alternatives_list}

Return JSON:
{{
    "current_analysis": {{
        "name": "{current_variant}",
        "inci": "INCI Name",
        "icon": "flask",
        "description": "Current ingredient description",
        "benefit_tag": "Key benefit",
        "suggested_percentage": "X-X%",
        "cost_impact": "baseline",
        "complexity_fit": ["{complexity}"]
    }},
    "alternatives": [
        {{
            "name": "Alternative Name",
            "inci": "INCI Name",
            "icon": "leaf",
            "description": "Description",
            "benefit_tag": "Unique benefit",
            "suggested_percentage": "X-X%",
            "cost_impact": "higher|similar|lower",
            "complexity_fit": ["complexity1", "complexity2"],
            "considerations": "Usage notes"
        }}
    ],
    "recommendation": {{
        "best_alternative": "Alternative Name",
        "reasoning": "Why best choice"
    }}
}}

Focus on practical formulation considerations.
"""

# ============================================================================
# BASIC MODE PROMPT (Formulynx-style)
# ============================================================================

def generate_basic_mode_prompt(wish_data: dict) -> str:
    """
    Generate the complete basic mode prompt following Formulynx flow.
    This is used for the simplified layman-friendly formula generation.
    """
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
# HELPER FUNCTIONS
# ============================================================================

def format_ingredients_list(ingredients):
    """Format ingredients for prompt"""
    return "\n".join([
        f"- {ing.get('display_name', ing.get('name', 'Unknown'))} ({ing.get('inci_name', 'Unknown')})\n"
        f"  Purpose: {ing.get('purpose', 'Unknown')}\n"
        f"  Range: {ing.get('percentage_range', 'Unknown')}\n"
        f"  Phase: {ing.get('phase', 'Unknown')}\n"
        f"  Hero: {ing.get('is_hero', False)}"
        for ing in ingredients
    ])

def format_alternatives_list(alternatives):
    """Format alternatives for prompt"""
    return "\n".join([
        f"- {alt.get('name', 'Unknown')}\n"
        f"  INCI: {alt.get('inci', 'Unknown')}\n"
        f"  Benefit: {alt.get('benefit', 'Unknown')}\n"
        f"  Percentage: {alt.get('percentage', 'Unknown')}\n"
        f"  Cost: {alt.get('cost_tier', 'Unknown')}\n"
        f"  Complexities: {', '.join(alt.get('complexity', []))}"
        for alt in alternatives
    ])
