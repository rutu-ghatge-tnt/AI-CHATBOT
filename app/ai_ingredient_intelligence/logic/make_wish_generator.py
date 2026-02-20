"""
Make a Wish - Formula Generator
================================

This module implements the formula generation for Make a Wish feature.
It follows the Formulynx flow with parameter extraction, active ingredient
options, complete formula generation, business context, and supporting content.
"""

import os
import json
import re
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone, timedelta

# Import prompts
from app.ai_ingredient_intelligence.logic.make_wish_prompts import (
    get_ingredient_selection_system_prompt,
    get_ingredient_selection_system_prompt_async,
    USE_MONGODB_FOR_COSTS,
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

# Import cost calculation post-processor
from app.ai_ingredient_intelligence.logic.cost_calculation_postprocessor import post_process_cost_analysis

# Claude API setup
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    anthropic = None

claude_api_key = os.getenv("CLAUDE_API_KEY")
claude_model = "claude-opus-4-5-20251101"  # Hardcoded Opus model for all Make a Wish operations

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

1. Calculate detailed cost breakdown
2. Estimate packaging costs for ALL common sizes: 30ml, 50ml, 100ml, 30g, 50g, 100g
3. Estimate labelling costs for each size:
   - 30ml/30g: ₹3-5
   - 50ml/50g: ₹4-6
   - 100ml/100g: ₹5-7
4. Estimate carton box costs for each size:
   - 30ml/30g: ₹6-9
   - 50ml/50g: ₹6-9
   - 100ml/100g: ₹7-10
5. Calculate total product cost for ALL sizes including: raw materials + packaging + labelling + carton box
6. Calculate manufacturing overhead (20% of subtotal: raw materials + packaging + labelling + carton box) for ALL sizes
7. Provide pricing recommendations (D2C 5x, retail 6x, premium 8x) for ALL sizes
8. Suggest cost optimization opportunities
9. Compare with competitor products if applicable

CRITICAL REQUIREMENTS:
- MUST include data for ALL sizes: 30ml, 50ml, 100ml, 30g, 50g, 100g
- This allows frontend users to switch between sizes without regenerating
- Include packaging_cost, labelling_cost, and carton_box_cost separately in packaging_estimate
- Manufacturing overhead is 20% of (raw material + packaging + labelling + carton box costs)
- D2C markup is 5x (changed from 4x)
- Calculate formula_cost for each size: (size/100) × formula_cost_per_100g

Return the complete cost analysis as JSON following the specified format with ALL sizes included.

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
    Call Claude Opus API for Make a Wish pipeline with prompt caching support.
    
    Uses claude-opus-4-5-20251101 for all Make a Wish operations including:
    - Wish parsing
    - Formula generation
    - Ingredient selection
    - Compliance checking
    
    Args:
        system_prompt: The system prompt (will be cached)
        user_prompt: The user prompt (dynamic content)
        prompt_type: Type of prompt for cache tracking (e.g., "parse_wish", "formula_generation")
        max_retries: Maximum number of retry attempts
    """
    
    if not claude_client:
        raise RuntimeError("Claude client not initialized. Check CLAUDE_API_KEY environment variable.")
    
    if not claude_model:
        raise RuntimeError("Claude model not configured. Check CLAUDE_MODEL environment variable.")
    
    # Format system prompt with cache_control (GA approach - SDK 0.34.0+)
    from app.ai_ingredient_intelligence.logic.prompt_cache_manager import format_system_prompt_with_cache
    formatted_system = format_system_prompt_with_cache(
        system_prompt=system_prompt,
        prompt_type=prompt_type,
        claude_client=claude_client,
        ttl="1h"  # 1 hour ephemeral cache
    )
    
    if isinstance(formatted_system, list):
        print(f"💾 Using prompt caching (GA) for {prompt_type} - system prompt formatted as content blocks")
    else:
        print(f"📝 Using plain system prompt for {prompt_type} (caching disabled or failed)")
    
    # Prepare API call parameters with properly formatted system prompt
    # Using claude-opus-4-5-20251101 for all Make a Wish operations
    api_params = {
        "model": claude_model,  # claude-opus-4-5-20251101
        "max_tokens": 16384,
        "temperature": 0.3,
        "system": formatted_system,  # Can be string or list of content blocks with cache_control
        "messages": [
            {"role": "user", "content": user_prompt}
        ]
    }
    
    timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
    print(f"🌐 [CLAUDE] [{timestamp}] Starting Claude API call (attempt {1}/{max_retries})...")
    print(f"🌐 [CLAUDE] [{timestamp}] Model: {claude_model}, Prompt type: {prompt_type}")
    
    for attempt in range(max_retries):
        try:
            # Call Claude API with caching support
            # Run in thread pool to prevent blocking the event loop
            # This allows other API requests (like wish-history) to be processed concurrently
            timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
            print(f"🌐 [CLAUDE] [{timestamp}] Executing API call in thread pool (attempt {attempt + 1})...")
            print(f"⏳ [CLAUDE] [{timestamp}] This may take 30-120 seconds for complex formulas...")
            
            loop = asyncio.get_event_loop()
            # Add timeout of 180 seconds (3 minutes) to prevent hanging forever
            # Also add a background task to log progress every 30 seconds
            async def log_progress():
                elapsed = 0
                while elapsed < 180:
                    await asyncio.sleep(30)  # Log every 30 seconds
                    elapsed += 30
                    timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
                    print(f"⏳ [CLAUDE] [{timestamp}] Still waiting for Claude API response... ({elapsed}s elapsed)")
            
            progress_task = asyncio.create_task(log_progress())
            
            try:
                response = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: claude_client.messages.create(**api_params)
                    ),
                    timeout=180.0  # 3 minute timeout
                )
                progress_task.cancel()  # Stop progress logging
                timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
                
                # Log response metadata
                if hasattr(response, 'usage'):
                    usage = response.usage
                    print(f"📊 [CLAUDE] [{timestamp}] Token usage - Input: {usage.input_tokens}, Output: {usage.output_tokens}, Total: {usage.input_tokens + usage.output_tokens}")
                
                # Log cache status if available
                if hasattr(response, 'cache_creation_input_tokens'):
                    print(f"💾 [CLAUDE] [{timestamp}] Cache creation tokens: {response.cache_creation_input_tokens}")
                if hasattr(response, 'cache_read_input_tokens'):
                    print(f"💾 [CLAUDE] [{timestamp}] Cache read tokens: {response.cache_read_input_tokens}")
                
                print(f"✅ [CLAUDE] [{timestamp}] Claude API call completed successfully!")
            except asyncio.TimeoutError:
                progress_task.cancel()  # Stop progress logging
                timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
                print(f"⏰ [CLAUDE] [{timestamp}] Claude API call timed out after 180 seconds!")
                if attempt < max_retries - 1:
                    print(f"🔄 [CLAUDE] [{timestamp}] Retrying... (attempt {attempt + 2}/{max_retries})")
                    await asyncio.sleep(2)
                    continue
                else:
                    raise Exception("Claude API call timed out after all retry attempts")
            except Exception as e:
                progress_task.cancel()  # Stop progress logging on any error
                raise
            
            if not response.content or len(response.content) == 0:
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                raise ValueError("Empty response from Claude API")
            
            content = response.content[0].text.strip()
            
            if not content:
                if attempt < max_retries - 1:
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
                timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
                print(f"🔍 [CLAUDE] [{timestamp}] AI Response Content preview: {content[:300]}...")
                print(f"🔍 [CLAUDE] [{timestamp}] Content length: {len(content)} chars")
                
                # Check if content starts with a JSON object
                if not content.startswith('{'):
                    # Try to find the first { character
                    first_brace = content.find('{')
                    if first_brace > 0:
                        print(f"⚠️ [CLAUDE] [{timestamp}] Content doesn't start with {{, found at position {first_brace}, trimming...")
                        content = content[first_brace:]
                    elif content.startswith('"') or content.startswith("'"):
                        # Content might be just a JSON string, wrap it
                        print(f"⚠️ [CLAUDE] [{timestamp}] Content appears to be a JSON string, wrapping in object...")
                        content = '{' + content + '}'
                
                result = json.loads(content)
                timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
                print(f"✅ [CLAUDE] [{timestamp}] JSON parsed successfully")
                return result
            except json.JSONDecodeError as e:
                # Debug: Log the JSON error
                timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
                print(f"❌ [CLAUDE] [{timestamp}] JSON Decode Error: {str(e)}")
                print(f"❌ [CLAUDE] [{timestamp}] Error position: {e.pos if hasattr(e, 'pos') else 'unknown'}")
                print(f"❌ [CLAUDE] [{timestamp}] Content that failed (first 1000 chars): {content[:1000]}")
                
                # Try to extract JSON from text - improved regex
                # Look for JSON that starts with a typical JSON structure
                json_patterns = [
                    r'\{.*?"formula_name".*?\}',        # JSON with formula_name (for parse-wish)
                    r'\{.*?"category".*?\}',            # JSON with category (for parse-wish)
                    r'\{.*?"product_type".*?\}',        # JSON with product_type (for parse-wish)
                    r'\{.*?"ingredients".*?\}',         # JSON with ingredients
                    r'\{.*?"analysis_date".*?\}',        # JSON with analysis_date
                    r'\{.*?"target_markets".*?\}',       # JSON with target_markets
                    r'\{.*?"critical_note".*?\}',        # JSON with critical_note
                    r'\{[^{}]*"[^"]+"\s*:\s*[^{}]*\}',  # Simple JSON objects
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
                            timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
                            print(f"✅ [CLAUDE] [{timestamp}] Extracted JSON using pattern: {pattern[:50]}...")
                            return result
                        except json.JSONDecodeError as pattern_error:
                            timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
                            print(f"⚠️ [CLAUDE] [{timestamp}] Pattern {pattern[:50]}... failed: {str(pattern_error)}")
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
                        timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
                        print(f"✅ [CLAUDE] [{timestamp}] Extracted JSON using line-by-line method")
                        return result
                    except json.JSONDecodeError:
                        pass
                
                if attempt < max_retries - 1:
                    timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
                    print(f"🔄 [CLAUDE] [{timestamp}] Retrying JSON parsing (attempt {attempt + 2}/{max_retries})...")
                    await asyncio.sleep(1)
                    continue
                else:
                    # Provide more detailed error message
                    error_msg = f"Failed to parse JSON from Claude response after {max_retries} attempts."
                    error_msg += f"\nJSON Error: {str(e)}"
                    error_msg += f"\nContent preview (first 1000 chars): {content[:1000]}"
                    if hasattr(e, 'pos') and e.pos:
                        error_msg += f"\nError at position: {e.pos}"
                        if e.pos < len(content):
                            error_msg += f"\nContext around error: ...{content[max(0, e.pos-50):e.pos+50]}..."
                    raise ValueError(error_msg)
        
        except Exception as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                continue
            else:
                print(f"Error calling Claude API: {e}")
                raise Exception(f"Claude API error after {max_retries} attempts: {str(e)}")
    
    raise Exception("All retry attempts failed")


# ============================================================================
# COMPLETE PIPELINE FUNCTION
# ============================================================================

# ============================================================================
# SYSTEM PROMPT
# ============================================================================

SYSTEM_PROMPT = """You are Formulynx's AI Formulation Engine. Your job is to:

1. Understand the user's product wish from natural language
2. Extract structured parameters
3. Present relevant ACTIVE INGREDIENT OPTIONS for their concern (BEFORE generating formula)
4. Generate a complete, professional formula
5. Output in a structured format for the UI to render

You are operating in a simplified mode - this means:
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
# FORMULA GENERATION FUNCTION
# ============================================================================

async def generate_formula_from_wish(wish_data: dict) -> dict:
    """
    Generate formula from user wish data.
    
    This follows the Formulynx Make a Wish flow:
    1. Parameter Extraction
    2. Active Ingredient Options Presentation
    3. Complete Formula Generation
    4. Business Context
    5. Supporting Content
    
    Args:
        wish_data: Dictionary containing user requirements
        
    Returns:
        Complete formula with all analysis
    """
    timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
    print(f"🚀 [FORMULA_GEN] [{timestamp}] Starting Make a Wish pipeline...")
    print(f"📋 [FORMULA_GEN] [{timestamp}] Wish data: category={wish_data.get('category')}, productType={wish_data.get('productType')}")
    
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
    
    # Generate complete formula response
    timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
    print(f"📋 [FORMULA_GEN] [{timestamp}] Generating complete formula...")
    from app.ai_ingredient_intelligence.logic.make_wish_prompts import generate_basic_mode_prompt
    user_prompt = generate_basic_mode_prompt(wish_data)
    timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
    print(f"📝 [FORMULA_GEN] [{timestamp}] Prompt generated, calling Claude AI...")
    
    try:
        timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
        print(f"🤖 [FORMULA_GEN] [{timestamp}] Calling call_ai_with_claude...")
        result = await call_ai_with_claude(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            prompt_type="formula_generation"
        )
        
        timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
        print(f"✅ [FORMULA_GEN] [{timestamp}] Formula generated successfully!")
        print(f"🎉 [FORMULA_GEN] [{timestamp}] Make a Wish pipeline complete!")
        return result
        
    except Exception as e:
        print(f"❌ Error in formula generation: {e}")
        import traceback
        traceback.print_exc()
        raise

