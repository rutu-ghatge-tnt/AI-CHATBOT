"""
Make a Wish - Formula Generator
================================

This module implements the complete 5-stage AI pipeline for generating
cosmetic formulations from user wishes.

STAGES:
1. Ingredient Selection
2. Formula Optimization
3. Manufacturing Process
4. Cost Analysis
5. Compliance Check
"""

import os
import json
import re
from typing import Dict, List, Optional, Any
from datetime import datetime

# Import prompts
from app.ai_ingredient_intelligence.logic.make_wish_prompts import (
    INGREDIENT_SELECTION_SYSTEM_PROMPT,
    FORMULA_OPTIMIZATION_SYSTEM_PROMPT,
    MANUFACTURING_PROCESS_SYSTEM_PROMPT,
    COST_ANALYSIS_SYSTEM_PROMPT,
    COMPLIANCE_CHECK_SYSTEM_PROMPT
)

# Import cache manager
from app.ai_ingredient_intelligence.logic.prompt_cache_manager import get_cache_manager

# Import rules engine
from app.ai_ingredient_intelligence.logic.make_wish_rules_engine import (
    get_rules_engine,
    ValidationSeverity
)

# Import unit helper
from app.ai_ingredient_intelligence.logic.formula_generator import get_unit_for_product_type

# Claude API setup
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    anthropic = None

claude_api_key = os.getenv("CLAUDE_API_KEY")
claude_model = "claude-opus-4-5-20251101"  # Hardcoded for Make a Wish

if not claude_api_key:
    raise RuntimeError("CLAUDE_API_KEY is required for Make a Wish feature")

if ANTHROPIC_AVAILABLE and claude_api_key:
    try:
        claude_client = anthropic.Anthropic(api_key=claude_api_key)
        print(f"Claude client initialized for Make a Wish with model: {claude_model}")
    except Exception as e:
        print(f"Warning: Could not initialize Claude client: {e}")
        claude_client = None
else:
    claude_client = None
    if not ANTHROPIC_AVAILABLE:
        raise RuntimeError("anthropic package is required. Install it with: pip install anthropic")


# ============================================================================
# PROMPT GENERATION FUNCTIONS
# ============================================================================

def generate_ingredient_selection_prompt(wish_data: dict) -> str:
    """Generate the user prompt for ingredient selection."""
    
    # Extract data from wish
    category = wish_data.get('category', 'skincare')  # skincare or haircare
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
    
    # Format benefits
    benefits_text = "\n".join([f"  • {b}" for b in benefits]) if benefits else "  • General skincare/haircare"
    
    # Format exclusions with specifics
    exclusion_mapping = {
        'silicone-free': 'ALL silicones (Dimethicone, Cyclomethicone, Cyclopentasiloxane, Amodimethicone, etc.)',
        'sulfate-free': 'ALL sulfates (SLS, SLES, ALS, Sodium Coco Sulfate, etc.)',
        'paraben-free': 'ALL parabens (Methylparaben, Propylparaben, Butylparaben, etc.)',
        'fragrance-free': 'Parfum/Fragrance AND synthetic fragrances',
        'alcohol-free': 'Drying alcohols (Alcohol Denat, SD Alcohol, Isopropyl Alcohol) - fatty alcohols OK',
        'mineral-oil-free': 'Mineral Oil, Paraffinum Liquidum, Petrolatum',
        'essential-oil-free': 'ALL essential oils',
        'vegan': 'ALL animal-derived ingredients (Lanolin, Carmine, Collagen, Keratin from animals, etc.)',
        'gluten-free': 'Wheat, Barley, Oat derivatives unless certified gluten-free'
    }
    
    exclusions_detailed = []
    for exc in exclusions:
        exc_lower = exc.lower().replace(' ', '-').replace('_', '-')
        if exc_lower in exclusion_mapping:
            exclusions_detailed.append(f"  • {exc}: {exclusion_mapping[exc_lower]}")
        else:
            exclusions_detailed.append(f"  • {exc}")
    
    exclusions_text = "\n".join(exclusions_detailed) if exclusions_detailed else "  • None specified"
    
    # Format hero ingredients
    hero_text = "\n".join([f"  • {h}" for h in hero_ingredients]) if hero_ingredients else "  • None specified (select best options)"
    
    # Format claims
    claims_text = "\n".join([f"  • {c}" for c in claims]) if claims else "  • No specific claims required"
    
    # Format target audience
    audience_text = ", ".join(target_audience) if target_audience else "General consumer"
    
    # Build the prompt
    prompt = f"""
## FORMULA REQUEST

### CATEGORY & PRODUCT TYPE

- Category: {category.upper()}
- Product Type: {product_type}
- Desired Texture: {texture}

### TARGET BENEFITS (in priority order)

{benefits_text}

### STRICT EXCLUSIONS - DO NOT INCLUDE ANY OF THESE

{exclusions_text}

### HERO INGREDIENTS TO PRIORITIZE

{hero_text}

### COST TARGET

- Target formula cost: ₹{cost_min} - ₹{cost_max} per unit
- This is the RAW MATERIAL cost, not retail price
- Optimize ingredient selection to meet this target

### PRODUCT CLAIMS TO SUPPORT

{claims_text}

### TARGET AUDIENCE

{audience_text}

### TEXTURE & SENSORY REQUIREMENTS

- Desired texture: {texture}
- Consider Indian climate (hot, humid) for stability and feel

"""
    
    # Add category-specific requirements
    if category == 'haircare':
        prompt += f"""
### HAIRCARE-SPECIFIC REQUIREMENTS

- Product: {product_type}
- Consider:
  • Scalp health and compatibility
  • Hair fiber protection
  • Rinse-off vs leave-on requirements
  • Hard water compatibility (common in India)
  • Heat/humidity resistance

"""
        
        if product_type in ['shampoo']:
            prompt += """
- SHAMPOO SPECIFIC:
  • Use gentle surfactant system (preferably sulfate-free if specified)
  • Include conditioning agents for post-wash feel
  • pH range: 4.5-6.0
  • Consider foam quality and stability

"""
        elif product_type in ['conditioner', 'hair-mask']:
            prompt += """
- CONDITIONER/MASK SPECIFIC:
  • Focus on conditioning quaternaries (BTMS, Cetrimonium Chloride)
  • Include slip agents for detangling
  • Consider protein content for repair
  • pH range: 4.0-5.0

"""
        elif product_type in ['hair-serum', 'hair-oil']:
            prompt += """
- SERUM/OIL SPECIFIC:
  • Consider silicone alternatives if silicone-free
  • Include heat protection if applicable
  • Focus on shine and frizz control
  • Lightweight, non-greasy feel

"""
        elif product_type in ['scalp-treatment']:
            prompt += """
- SCALP TREATMENT SPECIFIC:
  • Focus on scalp-soothing ingredients
  • Include anti-microbial agents if for dandruff
  • Consider penetration enhancers for actives
  • Non-comedogenic for scalp

"""
    
    else:  # skincare
        prompt += f"""
### SKINCARE-SPECIFIC REQUIREMENTS

- Product: {product_type}
- Consider:
  • Skin type compatibility
  • Non-comedogenic if for face
  • Photostability if includes actives
  • Layering compatibility in skincare routine

"""
        
        if product_type in ['serum']:
            prompt += """
- SERUM SPECIFIC:
  • High concentration of actives
  • Lightweight, fast-absorbing
  • Can be water-based, oil-based, or bi-phase
  • pH dependent on actives used

"""
        elif product_type in ['moisturizer', 'cream']:
            prompt += """
- MOISTURIZER SPECIFIC:
  • Balance of humectants, emollients, occlusives
  • Appropriate for specified skin type
  • Consider AM/PM usage
  • Include barrier-supporting ingredients

"""
        elif product_type in ['cleanser']:
            prompt += """
- CLEANSER SPECIFIC:
  • Gentle surfactant system
  • pH 4.5-6.5 (skin-compatible)
  • Consider double-cleansing if oil-based
  • Non-stripping, maintains barrier

"""
        elif product_type in ['sunscreen']:
            prompt += """
- SUNSCREEN SPECIFIC:
  • UV filters must provide broad spectrum protection
  • Consider photostability of filters
  • Water resistance if specified
  • Check BIS compliance for UV filter limits

"""
    
    # Add additional notes if provided
    if additional_notes:
        prompt += f"""
### ADDITIONAL REQUIREMENTS FROM USER

{additional_notes}

"""
    
    prompt += """
### YOUR TASK

1. Select 8-15 ingredients that best deliver the requested benefits
2. STRICTLY exclude all ingredients matching the exclusion criteria
3. Prioritize hero ingredients if specified
4. Organize ingredients into appropriate phases
5. Optimize for the target cost range
6. Provide insights explaining key ingredient choices
7. Flag any warnings or considerations

Return the complete ingredient selection as JSON following the specified format.

"""
    
    return prompt


def generate_optimization_prompt(wish_data: dict, selected_ingredients: list) -> str:
    """Generate the optimization prompt."""
    
    product_type = wish_data.get('productType', 'serum')
    category = wish_data.get('category', 'skincare')
    benefits = wish_data.get('benefits', [])
    texture = wish_data.get('texture', 'lightweight')
    cost_min = wish_data.get('costMin', 30)
    cost_max = wish_data.get('costMax', 60)
    
    # Format ingredients
    ingredients_text = "\n".join([
        f"  • {ing.get('ingredient_name', ing.get('name', 'Unknown'))} (INCI: {ing.get('inci_name', ing.get('inci', 'Unknown'))})\n"
        f"    - Function: {ing.get('functional_category', ing.get('function', 'Unknown'))}\n"
        f"    - Usage Range: {ing.get('usage_range', {}).get('min', 0)}-{ing.get('usage_range', {}).get('max', 0)}%\n"
        f"    - Cost: ₹{ing.get('cost_per_kg_inr', ing.get('cost_per_kg', 0))}/kg\n"
        f"    - Phase: {ing.get('phase', 'Unknown')}\n"
        f"    - Hero: {'Yes' if ing.get('is_hero', False) else 'No'}"
        for ing in selected_ingredients
    ])
    
    return f"""
## OPTIMIZE FORMULA PERCENTAGES

### PRODUCT DETAILS

- Category: {category.upper()}
- Product Type: {product_type}
- Desired Texture: {texture}

### TARGET BENEFITS

{chr(10).join([f"  • {b}" for b in benefits])}

### COST TARGET

- Formula cost: ₹{cost_min} - ₹{cost_max} per unit
- Optimize percentages to achieve this cost

### SELECTED INGREDIENTS TO OPTIMIZE

{ingredients_text}

### OPTIMIZATION REQUIREMENTS

1. **Percentage Allocation**
   - Total MUST equal exactly 100.00%
   - Water/base makes up the remainder
   - Round all percentages to 2 decimal places

2. **Active Optimization**
   - Hero ingredients at optimal efficacious levels
   - Balance multiple actives for synergy
   - Avoid excessive concentrations that increase cost without benefit

3. **Texture Achievement**
   - "{texture}" texture requires appropriate thickener/emollient levels
   - Consider sensory properties

4. **Cost Optimization**
   - Calculate cost contribution of each ingredient
   - If over budget, suggest percentage adjustments
   - Prioritize actives in cost allocation

5. **Stability Considerations**
   - Ensure preservative at effective level
   - pH adjusters sufficient for target range
   - Consider ingredient interactions

Return the optimized formula as JSON with exact percentages totaling 100.00%.

"""


def generate_manufacturing_prompt(optimized_formula: dict) -> str:
    """Generate the manufacturing process prompt."""
    
    formula_name = optimized_formula.get('optimized_formula', {}).get('name', 'Formula')
    ingredients = optimized_formula.get('ingredients', [])
    phases = optimized_formula.get('phase_summary', [])
    
    # Format ingredients by phase
    phase_ingredients = {}
    for ing in ingredients:
        phase = ing.get('phase', 'A')
        if phase not in phase_ingredients:
            phase_ingredients[phase] = []
        phase_ingredients[phase].append(ing)
    
    phases_text = "\n".join([
        f"Phase {p.get('phase', 'Unknown')} ({p.get('name', 'Unknown')}): {p.get('total_percent', 0)}%"
        for p in phases
    ])
    
    ingredients_by_phase = "\n\n".join([
        f"**Phase {phase}:**\n" + "\n".join([
            f"  - {ing.get('name', 'Unknown')}: {ing.get('percent', 0)}% ({ing.get('function', 'Unknown')})"
            for ing in phase_ingredients.get(phase, [])
        ])
        for phase in sorted(phase_ingredients.keys())
    ])
    
    return f"""
## GENERATE MANUFACTURING PROCESS

### FORMULA INFORMATION

- Formula Name: {formula_name}
- Total Percentage: {optimized_formula.get('optimized_formula', {}).get('total_percentage', 100)}%
- Target pH: {optimized_formula.get('optimized_formula', {}).get('target_ph', {})}

### PHASE BREAKDOWN

{phases_text}

### INGREDIENTS BY PHASE

{ingredients_by_phase}

### YOUR TASK

Generate detailed manufacturing instructions including:

1. Process type (cold/hot/combined)
2. Step-by-step instructions for each phase
3. Temperature requirements
4. Mixing parameters
5. Quality checkpoints
6. Troubleshooting guide
7. Packaging recommendations
8. Safety precautions

Return the complete manufacturing process as JSON following the specified format.

"""


def generate_cost_prompt(optimized_formula: dict, wish_data: dict) -> str:
    """Generate the cost analysis prompt."""
    
    formula_name = optimized_formula.get('optimized_formula', {}).get('name', 'Formula')
    ingredients = optimized_formula.get('ingredients', [])
    cost_breakdown = optimized_formula.get('cost_breakdown', {})
    total_cost = cost_breakdown.get('total_per_100g', 0)
    
    cost_min = wish_data.get('costMin', 30)
    cost_max = wish_data.get('costMax', 60)
    product_type = wish_data.get('productType', 'serum')
    benefits = wish_data.get('benefits', [])
    hero_ingredients = wish_data.get('heroIngredients', [])
    
    # Determine unit based on product type
    unit = get_unit_for_product_type(product_type)
    
    # Format ingredients with costs
    ingredients_text = "\n".join([
        f"  • {ing.get('name', 'Unknown')}: {ing.get('percent', 0)}% @ ₹{ing.get('cost_per_kg', 0)}/kg = ₹{ing.get('cost_contribution', 0)} per {unit}"
        for ing in ingredients
    ])
    
    # Format benefits and hero ingredients for context
    benefits_text = ", ".join(benefits) if benefits else "General benefits"
    hero_text = ", ".join(hero_ingredients) if hero_ingredients else "None specified"
    
    # Determine common sizes based on unit
    if unit == "ml":
        common_sizes = "30ml, 50ml, 100ml"
        size_examples = "30ml, 50ml, 100ml"
    else:
        common_sizes = "30g, 50g, 100g"
        size_examples = "30g, 50g, 100g"
    
    return f"""
## ANALYZE FORMULA COSTS

### FORMULA INFORMATION

- Formula Name: {formula_name}
- Product Type: {product_type}
- **Unit: {unit}** (use {unit} for all cost calculations and displays)
- Current Formula Cost: ₹{total_cost} per {unit}
- Target Cost Range: ₹{cost_min} - ₹{cost_max} per {unit}
- Target Benefits: {benefits_text}
- Hero Ingredients: {hero_text}

### INGREDIENT COSTS

{ingredients_text}

### COST BREAKDOWN

- Actives: ₹{cost_breakdown.get('actives_cost', 0)} per {unit}
- Base Ingredients: ₹{cost_breakdown.get('base_cost', 0)} per {unit}
- Functional Ingredients: ₹{cost_breakdown.get('functional_cost', 0)} per {unit}
- Preservation: ₹{cost_breakdown.get('preservation_cost', 0)} per {unit}

### YOUR TASK

1. Calculate detailed cost breakdown using **{unit}** as the unit
2. Estimate packaging costs for common sizes ({common_sizes})
3. Calculate total product cost with packaging (use {unit} consistently)
4. Provide pricing recommendations (D2C, retail, premium) for sizes: {size_examples}
5. Suggest cost optimization opportunities (savings should be in ₹ per {unit})
6. **CRITICAL: Compare with competitor products and calculate advantages:**
   - Find 4-6 similar products in the Indian market
   - For each competitor, calculate price_per_unit (MRP / size)
   - **IMPORTANT**: Calculate price per {unit} (NOT per 100{unit} unless product size is exactly 100{unit})
   - Compare your recommended MRP (from pricing_recommendations) with competitor MRPs
   - For each competitor, provide a specific "advantage" description:
     * If your price is lower: "Lower price per {unit}"
     * If your price is higher but value is better: "Better value with [specific benefit]"
     * If you have superior ingredients: "Higher [ingredient] concentration" or "Premium [ingredient]"
     * If you have unique formulation: "Cleaner formula" or "No [exclusion]"
     * **CRITICAL: NEVER use dashes ("—" or "-") or leave empty. Always provide a meaningful, specific advantage text.**
     * **If no clear advantage exists, compare price, ingredients, or formulation quality and state the comparison clearly.**
   - **Use {unit} consistently in all cost displays and comparisons**

**REMEMBER: All costs, prices, and comparisons must use {unit} as the unit, not "unit" or "100g".**

Return the complete cost analysis as JSON following the specified format with competitor_comparison including advantages for each product.

"""


def generate_compliance_prompt(optimized_formula: dict) -> str:
    """Generate the compliance check prompt."""
    
    formula_name = optimized_formula.get('optimized_formula', {}).get('name', 'Formula')
    ingredients = optimized_formula.get('ingredients', [])
    
    # Format ingredients with concentrations
    ingredients_text = "\n".join([
        f"  • {ing.get('name', 'Unknown')} (INCI: {ing.get('inci', 'Unknown')}): {ing.get('percent', 0)}%"
        for ing in ingredients
    ])
    
    return f"""
## CHECK REGULATORY COMPLIANCE

### FORMULA INFORMATION

- Formula Name: {formula_name}
- Target Markets: India (BIS), EU, US

### INGREDIENTS WITH CONCENTRATIONS

{ingredients_text}

### YOUR TASK

1. Check compliance with BIS IS 4707 (India)
2. Check compliance with EU Cosmetics Regulation
3. Check compliance with US FDA regulations
4. Verify all ingredient concentrations are within limits
5. Identify any required warnings or labeling
6. Provide claims guidance (allowed, needs substantiation, prohibited)
7. List any compliance issues or concerns

Return the complete compliance analysis as JSON following the specified format.

"""


# ============================================================================
# AI CALL FUNCTION
# ============================================================================

async def call_ai_with_claude(
    system_prompt: str,
    user_prompt: str,
    prompt_type: str = "general",
    max_retries: int = 1,  # Reduced to 1 for speed
    cache_block_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Call Claude API for Make a Wish pipeline with prompt caching support.
    Uses Claude as per project preference.
    
    Args:
        system_prompt: The system prompt (will be cached)
        user_prompt: The user prompt (dynamic content)
        prompt_type: Type of prompt for cache tracking (e.g., "ingredient_selection")
        max_retries: Maximum number of retry attempts
    """
    
    if not claude_client:
        raise RuntimeError("Claude client not initialized. Check CLAUDE_API_KEY environment variable.")
    
    if not claude_model:
        raise RuntimeError("Claude model not configured. Check CLAUDE_MODEL environment variable.")
    
    # Get cache manager and check if we should use caching
    cache_manager = get_cache_manager(claude_client)
    cache_block_id = await cache_manager.get_or_create_cache(
        prompt_type=prompt_type,
        system_prompt=system_prompt,
        claude_client=claude_client
    )
    
    # Prepare API call parameters
    api_params = {
        "model": claude_model,
        "max_tokens": 16384,
        "temperature": 0.3,
        "system": system_prompt,
        "messages": [
            {"role": "user", "content": user_prompt}
        ]
    }
    
    # Use cache_control if caching is enabled
    # Claude's ephemeral cache automatically caches system prompts when cache_control is used
    # This reduces costs by ~90% on system prompt tokens after the first call
    if cache_block_id:
        print(f"💾 Using cached system prompt for {prompt_type}")
    else:
        print(f"📝 Using uncached system prompt for {prompt_type} (first call)")
    
    for attempt in range(max_retries):
        try:
            # Call Claude API with caching support
            response = claude_client.messages.create(**api_params)
            
            if not response.content or len(response.content) == 0:
                if attempt < max_retries - 1:
                    import asyncio
                    await asyncio.sleep(1)
                    continue
                raise ValueError("Empty response from Claude API")
            
            content = response.content[0].text.strip()
            
            if not content:
                if attempt < max_retries - 1:
                    import asyncio
                    await asyncio.sleep(1)
                    continue
                raise ValueError("Empty text in Claude response")
            
            # Try to parse JSON
            try:
                # Remove markdown code blocks if present
                content = re.sub(r'```json\s*', '', content)
                content = re.sub(r'```\s*', '', content)
                content = content.strip()
                
                # Debug: Log the content
                print(f"🔍 AI Response Content: {content[:200]}...")
                
                result = json.loads(content)
                return result
            except json.JSONDecodeError as e:
                # Debug: Log the JSON error
                print(f"❌ JSON Decode Error: {str(e)}")
                print(f"❌ Content that failed: {content[:500]}...")
                
                # Try to extract JSON from text - improved regex
                # Look for JSON that starts with a typical JSON structure
                json_patterns = [
                    r'\{[^{}]*"[^"]+"\s*:\s*[^{}]*\}',  # Simple JSON objects
                    r'\{.*?"formula_name".*?\}',        # JSON with formula_name
                    r'\{.*?"analysis_date".*?\}',        # JSON with analysis_date
                    r'\{.*?"target_markets".*?\}',       # JSON with target_markets
                    r'\{.*?"critical_note".*?\}',        # JSON with critical_note
                ]
                
                for pattern in json_patterns:
                    json_match = re.search(pattern, content, re.DOTALL)
                    if json_match:
                        try:
                            json_str = json_match.group()
                            # Try to balance braces
                            open_count = json_str.count('{')
                            close_count = json_str.count('}')
                            if open_count > close_count:
                                # Add missing closing braces
                                json_str += '}' * (open_count - close_count)
                            
                            result = json.loads(json_str)
                            print(f"✅ Extracted JSON using pattern: {pattern}")
                            return result
                        except json.JSONDecodeError:
                            continue
                
                # Last resort - find the largest JSON-like structure
                lines = content.split('\n')
                json_lines = []
                in_json = False
                brace_count = 0
                
                for line in lines:
                    line = line.strip()
                    if line.startswith('{'):
                        in_json = True
                        brace_count = line.count('{') - line.count('}')
                        json_lines.append(line)
                    elif in_json:
                        brace_count += line.count('{') - line.count('}')
                        json_lines.append(line)
                        if brace_count <= 0:
                            break
                
                if json_lines:
                    try:
                        json_str = '\n'.join(json_lines)
                        result = json.loads(json_str)
                        print(f"✅ Extracted JSON using line-by-line method")
                        return result
                    except json.JSONDecodeError:
                        pass
                
                if attempt < max_retries - 1:
                    import asyncio
                    await asyncio.sleep(1)
                    continue
                else:
                    raise ValueError(f"Failed to parse JSON from Claude response. Content: {content[:500]}")
        
        except Exception as e:
            if attempt < max_retries - 1:
                import asyncio
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                continue
            else:
                print(f"Error calling Claude API: {e}")
                raise Exception(f"Claude API error after {max_retries} attempts: {str(e)}")
    
    raise Exception("All retry attempts failed")


# ============================================================================
# COMPLETE PIPELINE FUNCTION
# ============================================================================

async def generate_formula_from_wish(wish_data: dict) -> dict:
    """
    Complete pipeline for generating a formula from user wish.
    
    Args:
        wish_data: Dictionary containing user requirements
        
    Returns:
        Complete formula with all analysis
    """
    
    print("🚀 Starting Make a Wish pipeline...")
    
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
    
    # Stage 1: Ingredient Selection
    print("📋 Stage 1: Ingredient Selection...")
    selection_prompt = generate_ingredient_selection_prompt(wish_data)
    selected_ingredients = await call_ai_with_claude(
        system_prompt=INGREDIENT_SELECTION_SYSTEM_PROMPT,
        user_prompt=selection_prompt,
        prompt_type="ingredient_selection"
    )
    print(f"✅ Selected {len(selected_ingredients.get('ingredients', []))} ingredients")
    
    # Stage 2: Formula Optimization
    print("🔧 Stage 2: Formula Optimization...")
    optimization_prompt = generate_optimization_prompt(
        wish_data,
        selected_ingredients.get('ingredients', [])
    )
    optimized_formula = await call_ai_with_claude(
        system_prompt=FORMULA_OPTIMIZATION_SYSTEM_PROMPT,
        user_prompt=optimization_prompt,
        prompt_type="formula_optimization"
    )
    print(f"✅ Optimized formula: {optimized_formula.get('optimized_formula', {}).get('total_percentage', 0)}%")
    
    # Stages 3, 4, 5: Run in parallel for better performance
    # These stages are independent and can run concurrently
    print("🚀 Stages 3-5: Running Manufacturing, Cost Analysis, and Compliance in parallel...")
    
    import asyncio
    
    async def run_stage_3():
        print("🏭 Stage 3: Manufacturing Process...")
        manufacturing_prompt = generate_manufacturing_prompt(optimized_formula)
        result = await call_ai_with_claude(
            system_prompt=MANUFACTURING_PROCESS_SYSTEM_PROMPT,
            user_prompt=manufacturing_prompt,
            prompt_type="manufacturing_process"
        )
        print(f"✅ Generated {len(result.get('manufacturing_steps', []))} manufacturing steps")
        return result
    
    async def run_stage_4():
        print("💰 Stage 4: Cost Analysis...")
        cost_prompt = generate_cost_prompt(optimized_formula, wish_data)
        result = await call_ai_with_claude(
            system_prompt=COST_ANALYSIS_SYSTEM_PROMPT,
            user_prompt=cost_prompt,
            prompt_type="cost_analysis"
        )
        product_type = wish_data.get('productType', 'serum')
        unit = get_unit_for_product_type(product_type)
        print(f"✅ Cost analysis complete: ₹{result.get('raw_material_cost', {}).get('total_per_100g', 0)}/{unit}")
        return result
    
    async def run_stage_5():
        print("✅ Stage 5: Compliance Check...")
        compliance_prompt = generate_compliance_prompt(optimized_formula)
        result = await call_ai_with_claude(
            system_prompt=COMPLIANCE_CHECK_SYSTEM_PROMPT,
            user_prompt=compliance_prompt,
            prompt_type="compliance_check"
        )
        print(f"✅ Compliance: {result.get('overall_status', 'UNKNOWN')}")
        return result
    
    # Run stages 3, 4, and 5 in parallel
    manufacturing_process, cost_analysis, compliance = await asyncio.gather(
        run_stage_3(),
        run_stage_4(),
        run_stage_5()
    )
    
    # Combine all results
    result = {
        "wish_data": wish_data,
        "ingredient_selection": selected_ingredients,
        "optimized_formula": optimized_formula,
        "manufacturing": manufacturing_process,
        "cost_analysis": cost_analysis,
        "compliance": compliance,
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "formula_version": "1.0",
            "ai_model": claude_model or "claude-sonnet-4-5-20250929",
            "cache_stats": get_cache_manager().get_cache_stats()
        }
    }
    
    print("🎉 Make a Wish pipeline complete!")
    
    return result

