"""
Make A Wish - AI Prompts (Consolidated)
========================================

This module contains all AI prompts for the Make A Wish feature:
- Revised flow prompts (parse wish, ingredient selection, optimization, insights, alternatives)
- Basic mode prompt (Formulynx-style comprehensive prompt)

All prompts are organized in one place for clarity and maintainability.
"""

# Configuration: Use MongoDB for costs (True) or Excel file (False)
USE_MONGODB_FOR_COSTS = True  # Set to False to use Excel file instead

# Import cost lookup utility
COST_LOOKUP_AVAILABLE = False
get_cost_reference_table = None
get_cost_reference_table_from_mongo = None

if USE_MONGODB_FOR_COSTS:
    try:
        from app.ai_ingredient_intelligence.utils.inci_cost_lookup_mongo import (
            get_cost_reference_table_from_mongo
        )
        COST_LOOKUP_AVAILABLE = True
        get_cost_reference_table = get_cost_reference_table_from_mongo
    except ImportError:
        print("Warning: MongoDB cost lookup not available. Falling back to Excel.")
        USE_MONGODB_FOR_COSTS = False

if not USE_MONGODB_FOR_COSTS:
    try:
        from app.ai_ingredient_intelligence.utils.inci_cost_lookup import (
            get_cost_reference_table_from_excel as get_cost_reference_table_excel
        )
        COST_LOOKUP_AVAILABLE = True
        get_cost_reference_table = get_cost_reference_table_excel
    except ImportError:
        COST_LOOKUP_AVAILABLE = False
        print("Warning: INCI cost lookup utility not available. Using default cost anchors only.")

# ============================================================================
# COST REFERENCE ANCHORS & REASONING INSTRUCTIONS
# ============================================================================

COST_REFERENCE_ANCHORS = """
## INDIAN MARKET INGREDIENT PRICING REFERENCE (2025-26)
These are approximate wholesale prices in INR/kg for small-to-mid quantity orders (1-25kg) 
from Indian distributors. Use these as ANCHORS to estimate costs for similar ingredients.
DO NOT use prices outside these ranges without explicit reasoning.

### CATEGORY A: Base & Commodity Ingredients (Very High Confidence)
| Ingredient | INR/kg (Generic) | INR/kg (Branded) | Notes |
|-----------|------------------|-------------------|-------|
| Purified Water | 0.5-2 | — | RO/DI water |
| Glycerin (IP Grade) | 80-150 | 200-350 (Vegetable, Kosher) | Very stable pricing |
| Propylene Glycol | 120-200 | — | |
| Propanediol (1,3) | 400-700 | 1200-1800 (Zemea™) | Bio-based premium |
| Cetearyl Alcohol | 200-350 | 450-600 (BASF Kolliwax) | |
| Cetyl Alcohol | 220-380 | — | |
| Stearic Acid | 100-180 | — | |
| Isopropyl Myristate | 250-400 | — | |
| Dimethicone (350cs) | 300-500 | 800-1200 (Dow Corning) | |
| Cyclomethicone | 350-550 | — | |
| Mineral Oil (LP) | 80-150 | — | |

### CATEGORY B: Emulsifiers & Thickeners (High Confidence)
| Ingredient | INR/kg (Generic) | INR/kg (Branded) | Notes |
|-----------|------------------|-------------------|-------|
| Polysorbate 60 | 250-400 | — | |
| Polysorbate 80 | 280-450 | — | |
| Sorbitan Stearate | 300-500 | — | |
| Carbomer 940 | 1800-3000 | 4000-6000 (Lubrizol) | |
| Xanthan Gum | 500-900 | 1500-2500 (CP Kelco) | |
| Hydroxyethylcellulose | 400-700 | — | |
| BTMS-50 | 800-1400 | — | For conditioners |
| GMS (Glyceryl Monostearate) | 180-300 | — | |

### CATEGORY C: Common Active Ingredients (Medium-High Confidence)
| Ingredient | INR/kg (Generic) | INR/kg (Branded) | Notes |
|-----------|------------------|-------------------|-------|
| Niacinamide (B3) | 800-1500 | 3500-5000 (Lonza NiacinamidePC) | Most common active |
| Ascorbic Acid (Vitamin C) | 1000-1800 | 7000-9000 (DSM Quali-C) | |
| Sodium Ascorbyl Phosphate | 2500-4000 | 6000-9000 | Stable Vit C |
| Ascorbyl Glucoside | 3000-5500 | 8000-12000 | Very stable Vit C |
| Ethyl Ascorbic Acid | 4000-7000 | — | |
| Alpha Arbutin | 3000-5000 | 7000-10000 | Chinese vs Korean |
| Kojic Acid | 1200-2200 | — | |
| Kojic Acid Dipalmitate | 2000-3500 | — | Stabilized version |
| Salicylic Acid | 600-1000 | 2000-3500 (branded) | |
| Glycolic Acid (70%) | 800-1500 | 3000-5000 (DuPont) | |
| Lactic Acid (88%) | 400-700 | 1500-2500 | |
| Azelaic Acid | 2500-4500 | 6000-9000 | |
| Tranexamic Acid | 3500-6000 | — | Rising in price |
| Retinol (Pure) | 15000-25000 | 40000-60000 (DSM) | Very expensive |
| Bakuchiol | 8000-15000 | 25000-40000 (Sytheon) | |
| Allantoin | 500-900 | — | |
| Panthenol (D-Panthenol) | 1200-2000 | 3000-5000 (DSM) | |

### CATEGORY D: Specialty & Peptide Actives (Medium Confidence — VERIFY)
| Ingredient | INR/kg (Generic) | INR/kg (Branded) | Notes |
|-----------|------------------|-------------------|-------|
| Hyaluronic Acid (Std MW) | 8000-15000 | 25000-40000 (Bloomage) | Price varies hugely by MW |
| Hyaluronic Acid (Low MW) | 15000-30000 | 40000-70000 | More expensive than standard |
| Sepiwhite MSH | — | 25000-45000 (Seppic) | Patented, no generic |
| Sepinov EMT 10 | — | 8000-15000 (Seppic) | |
| Matrixyl 3000 | — | 20000-40000 (Sederma) | Patented peptide |
| Ceramide Complex | 10000-20000 | 30000-55000 | |
| Glutathione | 8000-18000 | — | Topical stability debated |
| Centella Asiatica Extract | 2000-4000 | 8000-15000 (Bayer) | |
| Squalane (Olive) | 1500-2800 | 4000-7000 (Amyris/Neossance) | |
| Squalane (Sugarcane) | 2000-3500 | 5000-8000 | |
| Bisabolol (Natural) | 3000-5500 | 8000-12000 (Symrise) | |

### CATEGORY E: Preservatives & Chelating Agents (High Confidence)
| Ingredient | INR/kg (Generic) | INR/kg (Branded) | Notes |
|-----------|------------------|-------------------|-------|
| Phenoxyethanol | 600-1000 | 1500-2500 (Clariant) | |
| Ethylhexylglycerin | 1200-2000 | 3000-4500 | |
| Sodium Benzoate | 200-400 | — | Needs pH <5 |
| Potassium Sorbate | 300-600 | — | Needs pH <5 |
| Disodium EDTA | 250-450 | — | |
| DMDM Hydantoin | 300-500 | — | Formaldehyde-releaser, controversial |

### CATEGORY F: Oils, Butters & Emollients (High Confidence)
| Ingredient | INR/kg (Generic) | INR/kg (Branded) | Notes |
|-----------|------------------|-------------------|-------|
| Coconut Oil (RBD) | 150-250 | — | |
| Sweet Almond Oil | 400-700 | — | |
| Jojoba Oil | 1500-2800 | 3500-5500 | |
| Argan Oil | 3000-6000 | 8000-15000 | Moroccan origin premium |
| Rosehip Seed Oil | 2500-4500 | — | |
| Shea Butter (Refined) | 400-700 | 1200-2000 (AAK) | |
| Cocoa Butter | 500-900 | — | |
| Vitamin E (Tocopheryl Acetate) | 800-1400 | 2500-4000 (DSM) | |
| Caprylic/Capric Triglyceride | 400-700 | — | |

### CATEGORY G: Surfactants (High Confidence — for haircare)
| Ingredient | INR/kg (Generic) | INR/kg (Branded) | Notes |
|-----------|------------------|-------------------|-------|
| SLS (Sodium Lauryl Sulfate) | 100-200 | — | |
| SLES (28%) | 60-120 | — | Liquid |
| Cocamidopropyl Betaine | 150-300 | — | |
| Decyl Glucoside | 350-600 | 800-1400 | |
| Coco Glucoside | 300-550 | 700-1200 | |
| Sodium Cocoyl Isethionate | 500-900 | 1500-2500 | SCI chip |

### CATEGORY H: Botanical Extracts (Medium Confidence)
| Ingredient | INR/kg (Generic) | INR/kg (Branded) | Notes |
|-----------|------------------|-------------------|-------|
| Aloe Vera Extract (10:1) | 800-1500 | — | Concentrated |
| Green Tea Extract | 1500-3000 | — | |
| Licorice Root Extract | 2000-4000 | 6000-10000 | Glabridin content matters |
| Turmeric Extract (Curcumin) | 1500-3500 | — | |
| Tea Tree Oil | 1200-2200 | 3000-5000 (Thursday Plantation) | |
| Neem Extract | 600-1200 | — | |

### PRICING REASONING RULES:
1. **FIRST: Check the Excel database** (see section below) - if ingredient is found, use EXACT cost from database.
2. **If ingredient is in this reference table**: Use the range directly.
3. **If ingredient is NOT in this table but is similar**: Reason from the closest category. 
   Example: "Ceteareth-20 is an ethoxylated fatty alcohol emulsifier similar to Polysorbate 60 → estimate ₹300-500/kg"
4. **If ingredient is a patented/branded specialty**: Assume ₹15,000-50,000/kg unless you have specific knowledge. Flag as LOW CONFIDENCE.
5. **Never estimate below ₹50/kg** for any cosmetic ingredient except water.
6. **Never estimate above ₹80,000/kg** unless it's a rare peptide or precious botanical.
7. **Generic Chinese imports** are typically 40-60% of branded prices.
8. **Indian-manufactured commodities** (glycerin, stearic acid, SLS) are at the low end.
"""


def get_enhanced_cost_reference_anchors() -> str:
    """
    Get cost reference anchors with database data included.
    Uses MongoDB if available, otherwise falls back to Excel file.
    Falls back to base anchors if database lookup fails or returns empty.
    """
    base_anchors = COST_REFERENCE_ANCHORS
    
    if COST_LOOKUP_AVAILABLE and get_cost_reference_table:
        try:
            if USE_MONGODB_FOR_COSTS:
                # MongoDB version is async, need to handle differently
                # For now, return base anchors and let the async handler add the table
                return base_anchors
            else:
                # Excel version is synchronous
                db_table = get_cost_reference_table()
                if db_table and db_table.strip():  # Check for non-empty string
                    return db_table + "\n\n" + base_anchors
                else:
                    print("Warning: Excel cost lookup returned empty. Using default anchors only.")
        except Exception as e:
            print(f"Warning: Could not load cost data: {e}. Using default anchors only.")
    
    return base_anchors


async def get_enhanced_cost_reference_anchors_async() -> str:
    """
    Async version that works with MongoDB.
    Use this when calling from async functions.
    Falls back to base anchors if MongoDB fails or returns empty.
    """
    base_anchors = COST_REFERENCE_ANCHORS
    
    if COST_LOOKUP_AVAILABLE and get_cost_reference_table:
        try:
            if USE_MONGODB_FOR_COSTS:
                # MongoDB async version
                db_table = await get_cost_reference_table_from_mongo()
                if db_table and db_table.strip():  # Check for non-empty string
                    return db_table + "\n\n" + base_anchors
                else:
                    print("Warning: MongoDB cost lookup returned empty. Using default anchors only.")
            else:
                # Excel synchronous version (can be called in async context)
                import asyncio
                db_table = await asyncio.to_thread(get_cost_reference_table)
                if db_table and db_table.strip():  # Check for non-empty string
                    return db_table + "\n\n" + base_anchors
                else:
                    print("Warning: Excel cost lookup returned empty. Using default anchors only.")
        except Exception as e:
            print(f"Warning: Could not load cost data: {e}. Using default anchors only.")
    
    return base_anchors

COST_REASONING_INSTRUCTIONS = """
## COST ESTIMATION PROTOCOL (MANDATORY FOR EVERY INGREDIENT)

For EACH ingredient, you MUST follow this reasoning chain:

### Step 1: Classify the ingredient
- Is it a commodity (water, glycerin, stearic acid)?
- Is it a common active (niacinamide, salicylic acid)?
- Is it a specialty active (peptides, patented ingredients)?
- Is it a botanical extract?

### Step 2: Check the Reference Table
- If the ingredient is in the reference table → use that range
- If not → find the closest analogous ingredient and reason from there
- State which reference you used

### Step 3: Apply Modifiers
- Generic Chinese import? → Use low end of range
- Branded/patented? → Use high end or above
- Requires cold chain? → Add 10-15% logistics premium
- Import-dependent? → Add 10-20% for duties/shipping
- Small MOQ available? → Prices may be 20-40% higher than bulk

### Step 4: Assign Confidence
- HIGH: Commodity ingredients with stable, well-known pricing
- MEDIUM: Common actives available from multiple suppliers  
- LOW: Patented ingredients, rare botanicals, novel peptides

### Step 5: Calculate Cost Contribution
- Formula: (percentage / 100) × (cost_per_kg / 1000) = cost per g
- Calculate for BOTH low and high price estimates
- This gives the cost RANGE per g

### CRITICAL RULES:
- NEVER output a single point estimate. ALWAYS give low-mid-high.
- If confidence is LOW, widen the range by 40% in both directions.
- Water cost contribution should be ₹0.0002-0.0005 per g, not more.
- Total formula cost for a basic cream should be ₹0.30-0.80/g (generic).
- Total formula cost for a premium cream should be ₹0.80-2.00/g (generic).
- Total formula cost for a luxury cream should be ₹2.00-5.00/g.
- If your total exceeds these ranges, RE-CHECK your per-kg estimates.
"""

COST_VALIDATION_RULES = """
## MANDATORY COST SANITY CHECKS (Run these BEFORE finalizing output)

### Check 1: Water Cost Sanity
- Water is 50-80% of most formulas
- Water cost contribution should be ₹0.0001-0.001 per g MAX
- If water shows as a significant cost driver → ERROR in pricing

### Check 2: Total Formula Cost Benchmarks
Compare your calculated total against these Indian market benchmarks:

| Product Type | Budget (₹/g) | Mid-range | Premium | Luxury |
|-------------|--------------|-----------|---------|--------|
| Face Cream | 0.25-0.50 | 0.50-1.00 | 1.00-2.50 | 2.50-6.00 |
| Face Serum | 0.30-0.60 | 0.60-1.50 | 1.50-4.00 | 4.00-10.00 |
| Shampoo | 0.10-0.25 | 0.25-0.50 | 0.50-1.00 | 1.00-2.00 |
| Body Lotion | 0.15-0.35 | 0.35-0.70 | 0.70-1.50 | 1.50-3.00 |
| Sunscreen | 0.40-0.80 | 0.80-1.80 | 1.80-4.00 | — |
| Face Wash | 0.15-0.30 | 0.30-0.60 | 0.60-1.20 | — |

If your total falls OUTSIDE the expected range for the product type and segment, 
RECHECK every ingredient cost and explain the deviation.

### Check 3: Active Ingredient Cost Dominance
- Active ingredients should be 40-75% of total formula raw material cost
- Base ingredients (water, glycerin, emulsifiers) should be 15-35%
- Preservatives should be 3-8%
- If base ingredients dominate cost → actives are probably underpriced
- If any single base ingredient costs more than an active → re-verify

### Check 4: Per-Unit Retail Plausibility
After calculating cost per unit (e.g., per 50g jar):
- The landed cost × 4-5 should give a plausible D2C MRP
- Compare this MRP to actual market products
- If your suggested MRP is <₹200 for a "premium" product → costs are too low
- If your suggested MRP is >₹3000 for a 50g cream → costs may be too high

### Check 5: Ingredient-to-Ingredient Ratio
- Niacinamide at 5% should NOT cost more than Retinol at 0.3%
- Glycerin at 5% should NOT cost more than Hyaluronic Acid at 0.5%
- If cheap ingredients show higher cost than expensive ones → pricing error

### Check 6: Competitor Reverse-Engineering
For the given product category, check:
- Minimalist sells Alpha Arbutin 2% serum at ₹599/30ml
- Their gross margin is likely 60-75%
- So their cost per 30ml is likely ₹150-240
- That means formula cost per 100ml is ₹300-500 for a premium serum
- Does your estimate align with this logic?

### OUTPUT REQUIREMENT:
After calculating costs, include a "validation_report" section:
{
    "validation_report": {
        "water_cost_check": "PASS|FAIL - explanation",
        "total_vs_benchmark": "PASS|FAIL - your total ₹X/g vs expected range ₹Y-Z/g for [segment]",
        "active_cost_ratio": "PASS|FAIL - actives are X% of total (expected 40-75%)",
        "mrp_plausibility": "PASS|FAIL - suggested MRP ₹X vs market range ₹Y-Z",
        "ingredient_ratio_check": "PASS|FAIL - details",
        "competitor_alignment": "PASS|FAIL - explanation",
        "overall_confidence": "HIGH|MEDIUM|LOW",
        "flags": ["List of any concerns or low-confidence estimates"]
    }
}
"""

# ============================================================================
# REVISED FLOW PROMPTS
# ============================================================================

# STAGE 1: PARSE WISH PROMPT
PARSE_WISH_PROMPT = """
Parse this cosmetic wish and extract structured information. Keep it simple and fast - just extract what the user wants, don't generate a full formula.

Wish: {wish_text}

## YOUR TASK:

Extract the following information from the natural language wish:
1. Category (skincare or haircare)
2. Product type (serum, moisturizer, shampoo, etc.)
3. Ingredients mentioned (if any)
4. Benefits requested
5. Exclusions mentioned (silicone-free, sulfate-free, etc.)
6. Skin types or hair concerns (if mentioned)
7. Any compatibility issues between mentioned ingredients

## OUTPUT FORMAT (JSON):

{{
  "category": "skincare|haircare",
  "product_type": {{
    "id": "serum|moisturizer|cleanser|shampoo|conditioner|mask|toner|oil|gel|balm|etc.",
    "name": "Display name (e.g., 'Serum', 'Moisturizer', 'Shampoo')",
    "icon": "lucide icon name (e.g., 'droplet', 'sparkles', 'beaker')",
    "confidence": 0.95
  }},
  "detected_ingredients": [
    {{
      "name": "Ingredient name as mentioned (e.g., 'Vitamin C', 'Niacinamide')",
      "confidence": 0.9,
      "has_alternatives": true
    }}
  ],
  "detected_benefits": [
    "List of benefits mentioned (e.g., 'brightening', 'anti-aging', 'hydration')"
  ],
  "detected_exclusions": [
    "List of exclusions mentioned (e.g., 'silicone-free', 'sulfate-free', 'paraben-free')"
  ],
  "detected_skin_types": [
    "List of skin types mentioned (e.g., 'oily', 'dry', 'sensitive') - empty if not mentioned"
  ],
  "detected_hair_concerns": [
    "List of hair concerns mentioned (e.g., 'dandruff', 'hair fall') - empty if not mentioned"
  ],
  "compatibility_issues": [
    {{
      "severity": "critical|warning",
      "title": "Brief issue title",
      "problem": "Description of the compatibility issue",
      "solution": "Suggested solution",
      "ingredients_involved": ["Ingredient1", "Ingredient2"]
    }}
  ],
  "needs_clarification": [
    {{
      "question": "Question if wish is ambiguous",
      "reason": "Why clarification is needed"
    }}
  ]
}}

## IMPORTANT RULES:

1. **Keep it simple**: Only extract what's explicitly mentioned or clearly implied. Don't generate a full formula.
2. **Product type**: Use common IDs like: serum, moisturizer, cleanser, toner, mask, shampoo, conditioner, oil, gel, balm, sunscreen, face_wash
3. **Icon names**: Use Lucide icon names like: droplet, sparkles, beaker, flask, test-tube, syringe, etc.
4. **Confidence**: Use high confidence (0.8-1.0) if clear, lower (0.5-0.7) if ambiguous
5. **Ingredients**: Only list ingredients explicitly mentioned. Use common names (e.g., "Vitamin C" not "L-Ascorbic Acid")
6. **Benefits**: Extract from phrases like "for brightening", "gives glow", "reduces wrinkles", etc.
7. **Exclusions**: Look for words like "free", "without", "no" (e.g., "silicone-free" → exclude silicones)
8. **Compatibility issues**: Only flag if multiple incompatible ingredients are mentioned together

Return ONLY the JSON, no additional text.
"""


# ============================================================================
# INGREDIENT SELECTION SYSTEM PROMPT (Base)
# ============================================================================

INGREDIENT_SELECTION_SYSTEM_PROMPT = """You are an expert cosmetic formulator. Your task is to select appropriate ingredients for a cosmetic formula based on user requirements.

CRITICAL RULES:
1. Select ingredients that match the requested benefits
2. Respect all exclusions (e.g., if "Silicone-free", don't include any silicones)
3. Prioritize hero ingredients if specified
4. Consider cost targets
5. Include necessary base ingredients (water, preservatives, pH adjusters)
6. Select appropriate functional ingredients (humectants, emollients, actives, etc.)
7. Organize ingredients into phases (Water Phase, Active Phase, Preservation, etc.)

OUTPUT FORMAT (JSON):
{
    "ingredients": [
        {
            "ingredient_name": "Niacinamide",
            "inci_names": ["Niacinamide"],
            "functional_categories": ["Skin Lightening Agents", "Antioxidants"],
            "estimated_cost_per_kg": 5000,
            "usage_range": {"min": 2, "max": 5},
            "function": "Brightening agent",
            "is_hero": false,
            "phase": "B"
        }
    ],
    "phases": [
        {
            "id": "A",
            "name": "Water Phase",
            "temp": "70°C",
            "ingredients": ["Purified Water", "Glycerin"]
        },
        {
            "id": "B",
            "name": "Active Phase",
            "temp": "40°C",
            "ingredients": ["Niacinamide", "3-O-Ethyl Ascorbic Acid"]
        }
    ],
    "insights": [
        {
            "icon": "💡",
            "title": "Niacinamide",
            "text": "Effective at 2-5% for brightening and oil control"
        }
    ],
    "warnings": [
        {
            "type": "info",
            "text": "pH must be maintained at 5.0-6.5 for optimal stability"
        }
    ],
    "reasoning": "Brief explanation of ingredient choices"
}

IMPORTANT:
- Use standard INCI names
- Provide realistic cost estimates in ₹/kg (Indian Rupees per kilogram)
- Provide safe usage percentage ranges
- Mark hero ingredients with is_hero: true
- Include at least 5-10 ingredients for a complete formula
- Always include: Water (Aqua), Preservative, pH Adjuster
- Organize into phases: Water Phase (A), Active Phase (B), Preservation (C/D)
- Generate insights explaining key ingredient choices
- Add warnings for important considerations (pH, stability, etc.)
"""


def get_ingredient_selection_system_prompt() -> str:
    """Get the ingredient selection system prompt with enhanced cost data (sync version)."""
    # For Excel (sync), use sync version
    if not USE_MONGODB_FOR_COSTS:
        return INGREDIENT_SELECTION_SYSTEM_PROMPT + get_enhanced_cost_reference_anchors() + COST_REASONING_INSTRUCTIONS
    else:
        # For MongoDB, return base prompt (will be enhanced in async version)
        return INGREDIENT_SELECTION_SYSTEM_PROMPT + COST_REFERENCE_ANCHORS + COST_REASONING_INSTRUCTIONS


async def get_ingredient_selection_system_prompt_async() -> str:
    """Get the ingredient selection system prompt with enhanced cost data (async version for MongoDB)."""
    enhanced_anchors = await get_enhanced_cost_reference_anchors_async()
    return INGREDIENT_SELECTION_SYSTEM_PROMPT + enhanced_anchors + COST_REASONING_INSTRUCTIONS
