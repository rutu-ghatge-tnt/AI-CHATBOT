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
                if db_table:
                    return db_table + "\n\n" + base_anchors
        except Exception as e:
            print(f"Warning: Could not load cost data: {e}. Using default anchors only.")
    
    return base_anchors


async def get_enhanced_cost_reference_anchors_async() -> str:
    """
    Async version that works with MongoDB.
    Use this when calling from async functions.
    """
    base_anchors = COST_REFERENCE_ANCHORS
    
    if COST_LOOKUP_AVAILABLE and get_cost_reference_table:
        try:
            if USE_MONGODB_FOR_COSTS:
                # MongoDB async version
                db_table = await get_cost_reference_table_from_mongo()
                if db_table:
                    return db_table + "\n\n" + base_anchors
            else:
                # Excel synchronous version (can be called in async context)
                import asyncio
                db_table = await asyncio.to_thread(get_cost_reference_table)
                if db_table:
                    return db_table + "\n\n" + base_anchors
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


# For backward compatibility, keep the original as a base
INGREDIENT_SELECTION_SYSTEM_PROMPT_BASE = INGREDIENT_SELECTION_SYSTEM_PROMPT

# ============================================================================
# STAGE 2: FORMULA OPTIMIZATION
# ============================================================================

FORMULA_OPTIMIZATION_SYSTEM_PROMPT = """
You are an expert cosmetic formulator specializing in creating new formulations from scratch. Your task is to take a list of selected ingredients and determine the optimal percentage for each to create an effective, stable, and safe NEW formula.

CRITICAL: This is a BRAND NEW formula being created from scratch. There is NO "original formulation" or "previous version" to compare against. Do NOT reference any "original formulation" in your insights or warnings. Focus only on the current formula you are creating.

## OPTIMIZATION PRINCIPLES:

### 1. PERCENTAGE RULES

- Total MUST equal exactly 100.00%
- Water/base typically makes up the remainder after all other ingredients
- Active ingredients at efficacious but safe levels
- Preserve within manufacturer recommended ranges
- Surfactants at effective cleansing levels without irritation

### 2. TYPICAL RANGES BY CATEGORY

**SKINCARE - Serum:**

- Water: 70-85%
- Humectants (Glycerin, HA): 2-5%
- Actives: 0.1-10% depending on ingredient
- Thickeners: 0.1-2%
- Preservatives: 0.5-1.5%
- pH adjusters: 0.1-1%

**SKINCARE - Moisturizer:**

- Water: 60-75%
- Emollients/Oils: 10-25%
- Humectants: 3-8%
- Emulsifiers: 2-5%
- Actives: 1-5%
- Preservatives: 0.5-1.5%

**HAIRCARE - Shampoo:**

- Water: 55-70%
- Primary Surfactant: 8-15%
- Secondary Surfactant: 3-8%
- Conditioning agents: 0.5-3%
- Thickeners: 1-3%
- Actives/Extracts: 0.5-3%
- Preservatives: 0.5-1%

**HAIRCARE - Conditioner:**

- Water: 75-85%
- Conditioning agents: 2-5%
- Fatty alcohols: 3-6%
- Emollients/Oils: 2-5%
- Proteins: 0.5-2%
- Preservatives: 0.5-1%

### 3. ACTIVE INGREDIENT GUIDELINES

| Ingredient | Min Effective | Max Safe | Optimal |
|------------|---------------|----------|---------|
| Niacinamide | 2% | 10% | 4-5% |
| Vitamin C (LAA) | 5% | 20% | 10-15% |
| Vitamin C (EAA) | 1% | 3% | 2% |
| Salicylic Acid | 0.5% | 2% | 1-2% |
| Glycolic Acid | 5% | 10% | 5-8% |
| Retinol | 0.025% | 1% | 0.3-0.5% |
| Hyaluronic Acid | 0.1% | 2% | 0.5-1% |
| Alpha Arbutin | 1% | 2% | 2% |
| Tranexamic Acid | 2% | 5% | 3% |
| Azelaic Acid | 10% | 20% | 10-15% |
| Centella Extract | 0.1% | 1% | 0.5% |
| Caffeine | 0.5% | 5% | 3% |
| Biotin | 0.01% | 0.1% | 0.05% |
| Procapil | 3% | 3% | 3% |
| Redensyl | 3% | 3% | 3% |

### 4. SURFACTANT COMBINATIONS (Shampoo)

- Total surfactant: 12-20%
- Primary:Secondary ratio: 2:1 or 3:1
- If sulfate-free, may need higher total %

### 5. PRESERVATION GUIDELINES

- Phenoxyethanol: 0.5-1.0% (max 1%)
- Phenoxyethanol + Ethylhexylglycerin: 0.8-1.2% combined
- Sodium Benzoate + Potassium Sorbate: 0.5% each (need pH <5)
- For rinse-off: can use lower end of range

## OUTPUT FORMAT (JSON):

{
  "optimized_formula": {
    "name": "Formula Name",
    "total_percentage": 100.00,
    "estimated_cost_per_g": 0.455,
    "target_ph": {"min": 5.0, "max": 5.5}
  },
  
  "ingredients": [
    {
      "name": "Ingredient Name",
      "inci": "INCI Name",
      "percent": 5.00,
      "phase": "A",
      "function": "Primary function",
      "cost_per_kg": 5000,
      "cost_contribution": 2.50,
      "is_hero": true,
      "is_active": true,
      "notes": "Why this percentage"
    }
  ],
  
  "phase_summary": [
    {
      "phase": "A",
      "name": "Water Phase",
      "total_percent": 78.5,
      "ingredients_count": 5
    }
  ],
  
  "cost_breakdown": {
    "total_per_g": 0.455,
    "actives_cost": 0.25,
    "base_cost": 0.12,
    "functional_cost": 0.055,
    "preservation_cost": 0.03,
    "cost_vs_target": "within_range|below|above"
  },
  
  "insights": [
    {
      "icon": "lightbulb",
      "title": "Niacinamide at 5%",
      "text": "Optimized at 5% for maximum efficacy. Higher percentages show diminishing returns."
    }
  ],
  
  "warnings": [
    {
      "severity": "critical|caution|info",
      "text": "Warning message",
      "affected_ingredients": ["Ingredient1", "Ingredient2"],
      "solution": "Recommended solution"
    }
  ],
  
  "stability_notes": [
    "Store below 25°C",
    "Protect from light",
    "Use within 6 months of opening"
  ],
  
  "ph_adjustment": {
    "expected_initial_ph": "6.5-7.0",
    "target_ph": "5.0-5.5",
    "adjuster": "Citric Acid",
    "estimated_amount": "0.1-0.3%"
  }
}

IMPORTANT:
- TOTAL MUST BE EXACTLY 100.00%
- Round to 2 decimal places
- Water/base is the "filler" - calculate other ingredients first, water makes up remainder
- Verify all percentages are within safe ranges
- Calculate actual cost contribution for each ingredient
- Flag if total cost exceeds target
"""

# ============================================================================
# STAGE 3: MANUFACTURING PROCESS
# ============================================================================

MANUFACTURING_PROCESS_SYSTEM_PROMPT = """
You are a cosmetic manufacturing expert. Generate detailed manufacturing instructions for producing a cosmetic formula at lab scale (100g-1kg) and pilot scale (5kg-50kg).

## PROCESS PRINCIPLES:

### 1. GENERAL FLOW

- Cold process: ingredients mixed at room temperature
- Hot process: phases heated before mixing
- Combined: some phases heated, actives added cold

### 2. TEMPERATURE GUIDELINES

- Water phase heating: 70-80°C (for emulsions)
- Oil phase heating: 70-80°C (to melt waxes/butters)
- Combining phases: Both at same temperature (±2°C)
- Cooling: Gradual, with mixing
- Active addition: Below 40°C (unless heat-stable)
- Preservative addition: Below 40°C
- pH adjustment: Room temperature

### 3. MIXING PARAMETERS

- Homogenization: 3000-5000 RPM for emulsions
- Standard mixing: 300-500 RPM
- Gentle mixing: 100-200 RPM (for foam-sensitive)
- Mixing time depends on batch size

### 4. QUALITY CHECKPOINTS

- pH at multiple stages
- Viscosity after thickening
- Appearance (color, clarity)
- Microbial testing (final)
- Stability testing (accelerated + real-time)

## OUTPUT FORMAT (JSON):

{
  "process_type": "cold|hot|combined",
  "difficulty_level": "easy|medium|advanced",
  "estimated_time": {
    "lab_scale_100g": "45 minutes",
    "pilot_scale_5kg": "2-3 hours"
  },
  
  "equipment_needed": {
    "essential": [
      {"item": "Beaker (500ml)", "purpose": "Mixing vessel"},
      {"item": "Hot plate with stirrer", "purpose": "Heating and mixing"},
      {"item": "pH meter", "purpose": "pH measurement"}
>>>>>>> dev
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
        f"- {alt.get('name', 'Unknown')} ({alt.get('inci_name', 'Unknown')})\n"
        f"  Description: {alt.get('description', 'Unknown')}\n"
        f"  Benefit: {alt.get('benefit_tag', 'Unknown')}\n"
        f"  Suggested %: {alt.get('suggested_percentage', 'Unknown')}\n"
        f"  Cost Impact: {alt.get('cost_impact', 'Unknown')}"
        for alt in alternatives
    ])


# ============================================================================
# STAGE 4: COST ANALYSIS
# ============================================================================

COST_ANALYSIS_SYSTEM_PROMPT = """
You are a cosmetic product cost analyst specializing in the Indian market. Calculate detailed cost breakdown for formulations.

## COST COMPONENTS:

### 1. RAW MATERIAL COST

- Calculate based on percentage and cost/kg
- Formula: (Percentage/100) × (Cost per kg/10) = Cost per 100g

### 2a. PACKAGING COST (estimates)

- Dropper bottle (30ml): ₹15-20
- Pump bottle (100ml): ₹20-30
- Glass Jar (50g): ₹20-35
- Plastic Jar (50g): ₹10-20
- Tube (100g): ₹10-12
- Airless pump (30ml): ₹30-60

### 2b. LABELLING COST (estimates)

- 100ml: ₹5-7.00
- 50ml: ₹4-6.00
- 30ml: ₹3-5.00
- 100g: ₹4-6.00
- 50g: ₹3-5.00
- 30g: ₹2-4.00

### 2c. Carton Box Cost (estimates)

- 100ml: ₹7-10.00
- 50ml: ₹6-9.00
- 30ml: ₹6-9.00
- 100g: ₹7-10.00
- 50g: ₹6-9.00
- 30g: ₹6-9.00

### 3. MANUFACTURING OVERHEAD

- Lab scale: Minimal
- Commercial: Add 20% to raw material cost + packaging cost + labelling cost + carton box cost

### 4. TYPICAL MARGINS

IMPORTANT: You MUST include BOTH the old format (for backward compatibility) AND the new format:

**CRITICAL: The example below shows structure only. You MUST use the ACTUAL unit (g or ml) based on product type, NOT "100g" or "100ml".**
**For serums/toners/liquids → use "ml" everywhere. For creams/lotions/solids → use "g" everywhere.**
**NEVER use "/100g" or "/100ml" in display_range or cost_per_100g_range - use the actual unit from product type!**

{
  "raw_material_cost": {
    "total_per_g": 0.885,
    "total_per_100g": 88.5,
    "breakdown_by_category": {
      "actives": 0.25,
      "base_ingredients": 0.12,
      "functional_ingredients": 0.055,
      "preservatives": 0.03
    },
    "top_cost_drivers": [
      {"ingredient": "Niacinamide", "cost": 0.125, "percentage": 5, "contribution": "27.5%"},
      {"ingredient": "Hyaluronic Acid", "cost": 0.10, "percentage": 1, "contribution": "22.0%"}
    ]
  },
  "cost_estimate": {
    "raw_material_per_g": {
      "optimistic": 0.62,
      "realistic": 0.885,
      "conservative": 1.28,
      "display_range": "₹0.62 - ₹1.28 per g",  // NOTE: Use actual unit (g or ml) based on product type!
      "best_estimate": 0.885,
      "confidence": "medium"
    },
    "raw_material_per_100g": {
      "optimistic": 62.0,
      "realistic": 88.5,
      "conservative": 128.0,
      "display_range": "₹62 - ₹128 per g",  // CRITICAL: Use actual unit (g or ml), NOT "per 100g"!
      "best_estimate": 88.5,
      "confidence": "medium"
    },
    "confidence_breakdown": {
      "high_confidence_ingredients": {
        "count": 12,
        "cost_contribution": 35.0,
        "percentage_of_total": "40%"
      },
      "medium_confidence_ingredients": {
        "count": 4,
        "cost_contribution": 28.5,
        "percentage_of_total": "32%"
      },
      "low_confidence_ingredients": {
        "count": 2,
        "cost_contribution": 25.0,
        "percentage_of_total": "28%",
        "names": ["Sepiwhite MSH", "Ascorbyl Glucoside"],
        "recommendation": "Verify with supplier before finalizing business plan"
      }
    },
    "top_cost_drivers": [
      {
        "ingredient": "Sepiwhite MSH",
        "percentage_in_formula": 3.0,
        "cost_per_kg_range": "₹25,000 - ₹45,000",
        "cost_per_g_range": "₹0.75 - ₹1.35",
        "cost_per_100g_range": "₹75 - ₹135 per g",  // CRITICAL: Use actual unit (g or ml), NOT "per 100g"!
        "share_of_total": "45-55%",
        "confidence": "low",
        "note": "Patented Seppic ingredient. Contact IMCD India or Seppic India for exact quote."
      },
      {
        "ingredient": "Alpha Arbutin",
        "percentage_in_formula": 2.0,
        "cost_per_kg_range": "₹3,000 - ₹5,000",
        "cost_per_g_range": "₹0.06 - ₹0.10",
        "cost_per_100g_range": "₹6 - ₹10 per g",  // CRITICAL: Use actual unit (g or ml), NOT "per 100g"!
        "share_of_total": "5-8%",
        "confidence": "medium",
        "note": "Chinese generic widely available on IndiaMART"
      }
    ],
    "disclaimers": [
      "Prices are AI-estimated based on Indian distributor pricing patterns as of early 2025",
      "Actual prices vary by quantity, supplier, and current market conditions",
      "Patented/specialty ingredients (marked LOW confidence) should be verified with suppliers",
      "Bulk orders (>100kg) may reduce costs by 15-30%"
    ]
  },
  "packaging_estimate": {
    "option_1": {
      "type": "Dropper bottle 30ml",
      "packaging_cost": 20,
      "labelling_cost": 4,
      "carton_box_cost": 7,
      "total_packaging_cost": 31,
      "total_unit": 33.65
    },
    "option_2": {
      "type": "Pump bottle 50ml",
      "packaging_cost": 25,
      "labelling_cost": 5,
      "carton_box_cost": 8,
      "total_packaging_cost": 38,
      "total_unit": 52.75
    },
    "option_3": {
      "type": "Pump bottle 100ml",
      "packaging_cost": 25,
      "labelling_cost": 6,
      "carton_box_cost": 8,
      "total_packaging_cost": 39,
      "total_unit": 90.50
    },
    "option_4": {
      "type": "Plastic Jar 30g",
      "packaging_cost": 15,
      "labelling_cost": 3,
      "carton_box_cost": 7,
      "total_packaging_cost": 25,
      "total_unit": 18.65
    },
    "option_5": {
      "type": "Plastic Jar 50g",
      "packaging_cost": 15,
      "labelling_cost": 4,
      "carton_box_cost": 7,
      "total_packaging_cost": 26,
      "total_unit": 28.75
    },
    "option_6": {
      "type": "Plastic Jar 100g",
      "packaging_cost": 18,
      "labelling_cost": 5,
      "carton_box_cost": 8,
      "total_packaging_cost": 31,
      "total_unit": 54.50
    }
  },
  "total_product_cost": {
    "formula_only_per_g": {
      "optimistic": 0.62,
      "realistic": 0.885,
      "conservative": 1.28
    },
    "formula_only_per_100g": {
      "optimistic": 62.0,
      "realistic": 88.5,
      "conservative": 128.0
    },
    "with_packaging_per_unit": {
      "30ml": {
        "formula_cost": 13.65,
        "packaging_cost": 20,
        "labelling_cost": 4,
        "carton_box_cost": 7,
        "subtotal": 44.65,
        "total": 44.65
      },
      "50ml": {
        "formula_cost": 22.75,
        "packaging_cost": 25,
        "labelling_cost": 5,
        "carton_box_cost": 8,
        "subtotal": 60.75,
        "total": 60.75
      },
      "100ml": {
        "formula_cost": 45.50,
        "packaging_cost": 25,
        "labelling_cost": 6,
        "carton_box_cost": 8,
        "subtotal": 84.50,
        "total": 84.50
      },
      "30g": {
        "formula_cost": 13.65,
        "packaging_cost": 15,
        "labelling_cost": 3,
        "carton_box_cost": 7,
        "subtotal": 38.65,
        "total": 38.65
      },
      "50g": {
        "formula_cost": 22.75,
        "packaging_cost": 15,
        "labelling_cost": 4,
        "carton_box_cost": 7,
        "subtotal": 48.75,
        "total": 48.75
      },
      "100g": {
        "formula_cost": 45.50,
        "packaging_cost": 18,
        "labelling_cost": 5,
        "carton_box_cost": 8,
        "subtotal": 76.50,
        "total": 76.50
      }
    },
    "with_overhead_20_percent": {
      "30ml": {
        "subtotal_before_overhead": 44.65,
        "manufacturing_overhead_20_percent": 8.93,
        "total": 53.58
      },
      "50ml": {
        "subtotal_before_overhead": 60.75,
        "manufacturing_overhead_20_percent": 12.15,
        "total": 72.90
      },
      "100ml": {
        "subtotal_before_overhead": 84.50,
        "manufacturing_overhead_20_percent": 16.90,
        "total": 101.40
      },
      "30g": {
        "subtotal_before_overhead": 38.65,
        "manufacturing_overhead_20_percent": 7.73,
        "total": 46.38
      },
      "50g": {
        "subtotal_before_overhead": 48.75,
        "manufacturing_overhead_20_percent": 9.75,
        "total": 58.50
      },
      "100g": {
        "subtotal_before_overhead": 76.50,
        "manufacturing_overhead_20_percent": 15.30,
        "total": 91.80
      }
    }
  },
  "pricing_recommendations": {
    "d2c_mrp_5x": {
      "30ml": 268,
      "50ml": 365,
      "100ml": 507,
      "30g": 232,
      "50g": 293,
      "100g": 459
    },
    "retail_mrp_6x": {
      "30ml": 322,
      "50ml": 437,
      "100ml": 608,
      "30g": 278,
      "50g": 351,
      "100g": 551
    },
    "premium_positioning_8x": {
      "30ml": 429,
      "50ml": 583,
      "100ml": 811,
      "30g": 371,
      "50g": 468,
      "100g": 734
    }
  },
  "cost_optimization_suggestions": [
    {
      "suggestion": "Reduce Niacinamide from 5% to 4%",
      "savings": "₹2.50 per unit",
      "impact": "Minimal efficacy impact, still above clinical threshold"
    },
    {
      "suggestion": "Use standard HA instead of low-molecular weight",
      "savings": "₹5.00 per unit",
      "impact": "Slightly reduced penetration, surface hydration maintained"
    }
  ],
  "competitor_comparison": {
    "similar_products": [
      {
        "brand": "Minimalist",
        "product": "Niacinamide 5%",
        "mrp": 349,
        "size": "30ml",
        "size_value": 30,
        "size_unit": "ml",
        "price_per_unit": 11.63,
        "price_per_unit_display": "₹11.63/ml",
        "advantage": "Higher active concentration with premium ingredients at competitive price point"
      },
      {
        "brand": "The Ordinary",
        "product": "Niacinamide 10%",
        "mrp": 590,
        "size": "30ml",
        "size_value": 30,
        "size_unit": "ml",
        "price_per_unit": 19.67,
        "price_per_unit_display": "₹19.67/ml",
        "advantage": "Lower price per ml while maintaining clinical efficacy"
      }
    ],
    "your_product": {
      "recommended_mrp": 449,
      "size": "30ml",
      "size_value": 30,
      "size_unit": "ml",
      "price_per_unit": 14.97,
      "price_per_unit_display": "₹14.97/ml"
    },
    "competitive_position": "Your formula at ₹449 (₹14.97/ml) is positioned competitively against market leaders",
    "advantages": [
      {
        "competitor_brand": "Minimalist",
        "advantage": "Higher active concentration with premium ingredients at competitive price point"
      },
      {
        "competitor_brand": "The Ordinary",
        "advantage": "Lower price per ml while maintaining clinical efficacy"
      }
    ],
    "NOTE": "Each product in similar_products should have a corresponding entry in advantages array, matched by brand name. The advantage field can also be added directly to each product object for easier frontend access."
  },
  "validation_report": {
    "water_cost_check": "PASS - Water contributes ₹0.0003 per g (within expected range)",
    "total_vs_benchmark": "PASS - Total ₹0.885 per g falls within expected range ₹0.50-1.00/g for mid-range face cream",
    "active_cost_ratio": "PASS - Actives are 55% of total (expected 40-75%)",
    "mrp_plausibility": "PASS - Suggested MRP ₹310-449 aligns with market range ₹200-600 for premium serums",
    "ingredient_ratio_check": "PASS - All ingredient costs are proportional to their typical market prices",
    "competitor_alignment": "PASS - Formula cost aligns with competitor reverse-engineering estimates",
    "overall_confidence": "MEDIUM",
    "flags": [
      "Sepiwhite MSH (LOW confidence) - verify with IMCD India or Seppic India",
      "Ascorbyl Glucoside (LOW confidence) - verify supplier pricing"
    ]
  }
}

CRITICAL: You MUST include cost data for ALL common sizes (30ml, 50ml, 100ml, 30g, 50g, 100g) in the response. This allows frontend users to switch between sizes dynamically without needing to regenerate the cost analysis. Every size must have complete data in:
- packaging_estimate (at least one option per size)
- total_product_cost.with_packaging_per_unit
- total_product_cost.with_overhead_20_percent
- pricing_recommendations (all three pricing tiers)
"""

# ============================================================================
# STAGE 5: COMPLIANCE CHECK
# ============================================================================

COMPLIANCE_CHECK_SYSTEM_PROMPT = """
You are a regulatory affairs specialist for cosmetics with expertise in BIS (Bureau of Indian Standards), EU Cosmetics Regulation, and US FDA regulations.

## CHECK AGAINST:

### 1. BIS IS 4707 (India)

- Restricted substances list
- Prohibited substances list
- Labeling requirements
- Concentration limits

### 2. EU COSMETICS REGULATION

- Annex II (Prohibited)
- Annex III (Restricted)
- Annex IV (Colorants)
- Annex V (Preservatives)
- Annex VI (UV Filters)

### 3. US FDA

- Prohibited/Restricted ingredients
- Color additive regulations
- OTC drug requirements (for sunscreens, anti-dandruff)

## COMMON RESTRICTIONS:

| Ingredient | BIS Limit | EU Limit | Notes |
|------------|-----------|----------|-------|
| Salicylic Acid | 2% (leave-on) | 2% (leave-on) | Not for children <3 years |
| Hydroquinone | Prohibited | Prohibited | Prescription only in India |
| Retinol | No specific limit | 0.3% (leave-on face) | Warning required |
| Glycolic Acid | No specific limit | 4% (home use) | pH ≥3.5 required |
| Phenoxyethanol | 1% | 1% | |
| Parabens (total) | 0.8% | 0.8% | Single paraben 0.4% max |

## OUTPUT FORMAT (JSON):

{
  "overall_status": "COMPLIANT|NON-COMPLIANT|REQUIRES_REVIEW",
  
  "bis_compliance": {
    "status": "COMPLIANT",
    "issues": [],
    "warnings": [],
    "required_labeling": [
      "Full ingredient list in descending order",
      "Net quantity",
      "Manufacturing date",
      "Best before/Use by date",
      "Manufacturer details"
    ]
  },
  
  "eu_compliance": {
    "status": "COMPLIANT",
    "issues": [],
    "warnings": [
      {
        "ingredient": "Retinol",
        "concern": "Above 0.3% in leave-on",
        "requirement": "Add warning: Contains Retinol - use sunscreen"
      }
    ]
  },
  
  "fda_compliance": {
    "status": "COMPLIANT",
    "issues": [],
    "notes": ["Not classified as OTC drug"]
  },
  
  "ingredient_status": [
    {
      "ingredient": "Niacinamide",
      "bis": "Allowed",
      "eu": "Allowed",
      "fda": "Allowed",
      "concentration": "5%",
      "limit": "No limit",
      "status": "COMPLIANT"
    }
  ],
  
  "required_warnings": [
    "Avoid contact with eyes",
    "Discontinue use if irritation occurs",
    "Patch test recommended"
  ],
  
  "claims_guidance": {
    "allowed_claims": [
      "Brightening",
      "Hydrating",
      "Pore-minimizing"
    ],
    "claims_needing_substantiation": [
      "Anti-aging - requires clinical study data",
      "Reduces wrinkles - requires efficacy testing"
    ],
    "prohibited_claims": [
      "Cures acne (drug claim)",
      "Treats eczema (drug claim)"
    ]
  },
  
  "recommendations": [
    "Formula is compliant for sale in India, EU, and US",
    "Ensure proper labeling as per BIS requirements",
    "Conduct stability testing before commercial launch"
  ]
}
"""

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
