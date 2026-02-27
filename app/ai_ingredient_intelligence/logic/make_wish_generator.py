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

# Import prompts (only what's used by generate_formula_from_wish / call_ai_with_claude)
from app.ai_ingredient_intelligence.logic.make_wish_prompts import (
    get_ingredient_selection_system_prompt,
    get_ingredient_selection_system_prompt_async,
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
# FORMULA PROMPT GENERATION
# ============================================================================

def generate_formula_prompt(wish_data: dict) -> str:
    """Generate the complete formula prompt following Formulynx flow."""
    
    # Extract data from wish
    category = wish_data.get('category', 'skincare')
    product_type = wish_data.get('productType', 'serum')
    benefits = wish_data.get('benefits', [])
    exclusions = wish_data.get('exclusions', [])
    hero_ingredients = wish_data.get('heroIngredients', [])
    texture = wish_data.get('texture', 'lightweight')
    cost_min = wish_data.get('costMin', 30)
    cost_max = wish_data.get('costMax', 60)
    complexity = wish_data.get('complexity', 'classic')
    max_ingredients = wish_data.get('maxIngredients', 14)
    active_slots = wish_data.get('activeSlots', 3)
    include_sensorials = wish_data.get('includeSensorials', True)
    complexity_description = wish_data.get('complexityDescription', '')
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
    
    # Build complexity constraints section
    complexity_section = f"""
## FORMULA COMPLEXITY CONSTRAINTS (CRITICAL - MUST FOLLOW)

Complexity Level: {complexity.title()} ({complexity_description})

**MANDATORY CONSTRAINTS:**
- Maximum Total Ingredients: {max_ingredients} (including base ingredients, actives, preservatives, etc.)
- Maximum Hero Actives: {active_slots} (primary active ingredients that deliver main benefits)
- Include Sensorials: {'Yes' if include_sensorials else 'No'} (texture enhancers, sensory modifiers, botanical extracts)

**INGREDIENT SELECTION RULES:**
- For {complexity} complexity, select ingredients that align with the {complexity_description} philosophy
- Do NOT exceed {max_ingredients} total ingredients in the final formula
- Focus on {active_slots} hero actives that directly address the primary concerns
- {'Include texture enhancers and sensorial ingredients for a luxurious experience' if include_sensorials else 'Keep formula minimal - only essential functional ingredients, no sensorial additives'}
- Base ingredients (water, humectants, preservatives, pH adjusters) are required and count toward the total

**FORMULA GENERATION GUIDANCE:**
- Minimalist ({max_ingredients if complexity == 'minimalist' else '8'} max): Clean label, essential actives only, minimal base ingredients
- Classic ({max_ingredients if complexity == 'classic' else '14'} max): Balanced formula with proven actives, standard base ingredients
- Luxe ({max_ingredients if complexity == 'luxe' else '22'} max): Multi-active powerhouse, premium base ingredients, sensorial enhancements

IMPORTANT: The final formula MUST have {max_ingredients} or fewer total ingredients. Count every ingredient including water, preservatives, and pH adjusters.
"""
    
    prompt = f"""# FORMULYNX FORMULA GENERATION PROMPT

## INPUT
User wish: "{natural_language_input}"
Category: {category}
Product Type: {product_type}
Benefits: {', '.join(benefits) if benefits else 'General'}
Price Segment: {price_segment} (Cost target: ₹{cost_min}-₹{cost_max}/100g)
Complexity Level: {complexity.title()}
Exclusions: {', '.join(exclusions) if exclusions else 'None'}
Hero Ingredients: {', '.join(hero_ingredients) if hero_ingredients else 'None specified'}
Texture: {texture}
Claims: {', '.join(claims) if claims else 'None'}
Target Audience: {', '.join(target_audience) if target_audience else 'General'}
Additional Notes: {additional_notes if additional_notes else 'None'}
{complexity_section}

## PROCESS

### Step 1: Extract Parameters
Parse the input to identify:
- Category (Skincare/Haircare/Lipcare/Bodycare/etc.)
- Product Type (Cream/Serum/Shampoo/Balm/etc.)
- Primary Concern (Dark Circles/Acne/Hair Loss/etc.)
- Secondary Concerns related to the primary concern
- Price Segment (Mass/Masstige/Premium/Luxury)
- Any specific requirements (Lightweight/SPF50/Rich Lather/Paraben Free/Safe for kids/etc.)

### Step 2: Present Active Options
For the identified concerns, present:
- 3 to 4 active ingredient options per concern (but respect the {active_slots} hero active limit for {complexity} complexity)
- Include: name, concentration, clinical efficacy data availability (Score 0 for no data available related to the primary concern and 100 for a clinically well studied ingredient), cost impact, and justification for its inclusion
- Highlight recommended options that fit the complexity level
- Explain WHY certain combinations work - Highlight possible incompatibilities
- Ensure recommendations align with {complexity} complexity constraints

### Step 3: Generate Formula
Based on selections (or recommendations), generate:
- Complete formula with all ingredients (MUST NOT exceed {max_ingredients} total ingredients)
- Grouped by benefit (not by phase) for user view
- Technical formula with phases for manufacturer
- Total cost per 100gm
- Recommended pH based on the ingredient stability and efficacy
- Verify ingredient count: Total ingredients must be ≤ {max_ingredients}, Hero actives must be ≤ {active_slots}

### Step 4: Generate Business Context
- Packaging options most suitable for the product type
- Profit calculations at different MRPs
- Market comparison with competitors (MUST include "advantage" field for each competitor showing comprehensive advantage: price + ingredients + benefits + overall value, but do not claim superiority)
- Cost factors that affect real pricing

### Step 5: Generate Supporting Content
- Key features (3 main benefit cards)
- Q&A cards (4-5 questions users would ask)
- Category trends (MUST include at least 3 trends, never empty)
- Related trends (MUST include at least 2-3 related trends based on category/benefits, never empty)
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
            "clinicalEfficacyScore": 85,
            "costImpact": "High",
            "justification": "Explanation of why this works and justification for inclusion",
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
        {{ 
          "brand": "Competitor", 
          "price": 549, 
          "size": "30g", 
          "pricePerGram": 18.30,
          "advantage": "Your advantage description (e.g., ₹X.XX/g cheaper or Better cost efficiency)",
          "yourAdvantage": "Your advantage description"
        }}
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
    "relatedTrends": [
      {{
        "trend": "Related trend name",
        "growth": "+38%",
        "note": "Related market insight",
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
3. No individual ingredient costs shown - only total formula cost per 100gm
4. Always explain WHY ingredients work, especially for premium actives
5. Compare to known brands at every opportunity but do not claim superiority
6. Segment-appropriate actives (don't suggest luxury peptides for mass market)
7. Include myth busters where relevant
8. Build confidence throughout

## COST CALCULATION RULES (CRITICAL - MUST FOLLOW):
For cost calculations, prefer to use rates of ingredients from the database. If rate is unknown, use the following fixed rates based on ingredient type:

1. **Indian origin extract (non-hero)**: ₹5,000/kg
2. **Imported extract (hero ingredient)**: ₹15,000/kg
3. **Indian origin extract (hero ingredient)**: ₹10,000/kg
4. **Peptide (hero ingredient)**: ₹30,000/kg
5. **Plant essence (hero ingredient)**: ₹10,000/kg
6. **Biotech origin (hero ingredient)**: ₹20,000/kg
7. **Chemical (hero ingredient)**: ₹15,000/kg

**Priority order:**
1. First: Check database MongoDB for exact cost
2. Second: Use reference anchors table if ingredient matches
3. Third: Apply fixed rates above based on ingredient classification
4. Always calculate total cost per 100gm for the final formula

**CRITICAL: Water/Aqua Cost Calculation**
- Water (Aqua) cost from database: ₹1/kg (or ₹1.35/kg with 35% markup)
- Formula: (Percentage/100) × (Cost per kg/10) = Cost per 100g
- Example: Water at 70% with ₹1.35/kg = (70/100) × (1.35/10) = ₹0.0945 per 100g
- Water should contribute LESS than ₹0.10 per 100g - if you see water costing ₹100+ per 100g, you have made a calculation error!
- NEVER use water cost as ₹428/kg or any value above ₹5/kg - water is essentially free (₹1-2/kg max)

## CRITICAL REQUIREMENTS (MUST FOLLOW):
1. **categoryTrends**: MUST include at least 3 trends. Never return empty array. Include trends relevant to the product category and benefits.
2. **relatedTrends**: MUST include at least 2-3 related trends. Never return empty array. Base on category, benefits, and market insights.
3. **marketComparison advantage**: For each competitor in marketComparison, MUST calculate and include "advantage" field showing:
   - Advantage should be comprehensive, not just price:
     * Price: "₹X.XX/g cheaper" (if significantly cheaper) - ALL PRICES IN GRAMS (g) ONLY
     * Ingredients: "Premium actives (Niacinamide, Licorice)" or "More active ingredients"
     * Benefits: "Multi-benefit: Brightening + Healing" or "Targets 3 concerns"
     * Value: "Better value proposition" or "Premium formulation"
     * Combine multiple advantages: "₹X.XX/g cheaper + Premium actives" or "Multi-benefit + Better value"
   - If similar: "Similar pricing"
   - Always provide a meaningful advantage description, never leave blank
4. **Error handling**: If any calculation fails, provide fallback text like "Cost analysis pending" or "Better cost efficiency" - never leave blank

Generate the complete response now.
"""
    
    return prompt


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
    
    # Generate complete formula response
    print("📋 Generating complete formula...")
    user_prompt = generate_formula_prompt(wish_data)
    
    try:
        result = await call_ai_with_claude(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            prompt_type="formula_generation"
        )
        
        print("✅ Formula generated")
        
        # ========================================================================
        # VALIDATION AND FIXES: Ensure required fields are never empty
        # ========================================================================
        
        # Ensure formula structure exists
        if not isinstance(result, dict):
            print("⚠️ Warning: result is not a dict, converting...")
            result = {"formula": result} if result else {}
        
        formula_data = result.get("formula", {})
        if not formula_data:
            formula_data = result
            result["formula"] = formula_data
        
        # 1. Ensure categoryTrends is never empty
        category_trends = formula_data.get("categoryTrends", [])
        if not category_trends or len(category_trends) == 0:
            print("⚠️ Warning: categoryTrends is empty, adding default trends")
            category_trends = [
                {
                    "trend": "Active Ingredient Focus",
                    "growth": "+35%",
                    "note": "Consumers prefer products with proven actives",
                    "status": "aligned"
                },
                {
                    "trend": "Value-Based Pricing",
                    "growth": "+28%",
                    "note": "Price-conscious consumers seek quality at affordable prices",
                    "status": "aligned"
                },
                {
                    "trend": "Clean Beauty",
                    "growth": "+42%",
                    "note": "Growing demand for clean, safe formulations",
                    "status": "aligned"
                }
            ]
            formula_data["categoryTrends"] = category_trends
        
        # 2. Ensure relatedTrends exists and is never empty
        related_trends = formula_data.get("relatedTrends", [])
        if not related_trends or len(related_trends) == 0:
            print("⚠️ Warning: relatedTrends is empty, adding default related trends")
            # Generate related trends based on category and benefits
            category = wish_data.get('category', 'skincare')
            benefits = wish_data.get('benefits', [])
            benefits_str = ' '.join(benefits).lower() if benefits else ''
            
            related_trends = []
            if 'brightening' in benefits_str or 'pigmentation' in benefits_str:
                related_trends.append({
                    "trend": "Hyperpigmentation Solutions",
                    "growth": "+38%",
                    "note": "Growing concern about uneven skin tone",
                    "status": "aligned"
                })
            if 'anti-aging' in benefits_str or 'wrinkle' in benefits_str or 'aging' in benefits_str:
                related_trends.append({
                    "trend": "Preventive Skincare",
                    "growth": "+31%",
                    "note": "Younger consumers investing in anti-aging early",
                    "status": "aligned"
                })
            if category == 'haircare':
                related_trends.append({
                    "trend": "Scalp Health Focus",
                    "growth": "+45%",
                    "note": "Consumers prioritizing scalp care",
                    "status": "aligned"
                })
            
            # Always add at least 2-3 related trends
            if len(related_trends) < 2:
                related_trends.extend([
                    {
                        "trend": "Personalized Formulations",
                        "growth": "+33%",
                        "note": "Custom solutions for specific concerns",
                        "status": "aligned"
                    },
                    {
                        "trend": "Sustainable Packaging",
                        "growth": "+27%",
                        "note": "Eco-conscious consumer preferences",
                        "status": "aligned"
                    }
                ])
            
            formula_data["relatedTrends"] = related_trends[:5]  # Limit to 5
        
        # 3. Fix "Your advantage" in marketComparison - comprehensive analysis (price + ingredients + benefits)
        business_numbers = formula_data.get("businessNumbers", {})
        market_comparison = business_numbers.get("marketComparison", [])
        if market_comparison:
            # Extract user's formula strengths
            technical_formula = formula_data.get("technicalFormula", {})
            user_cost_per_100g = technical_formula.get("totalCostPer100g", 0)
            
            # Get product type and unit for proper calculation
            product_type = wish_data.get('productType', 'serum')
            unit = get_unit_for_product_type(product_type)
            # Convert cost per 100g to cost per gram (ALL in grams)
            user_cost_per_unit = user_cost_per_100g / 100 if user_cost_per_100g > 0 else 0
            
            # Get hero ingredients and benefits from formula
            active_options = result.get("activeOptions", {})
            recommended_formula = active_options.get("recommendedFormula", {})
            hero_actives = recommended_formula.get("heroActives", [])
            hero_ingredient_names = [ing.get("name", "") for ing in hero_actives if ing.get("name")]
            
            # Get key features/benefits
            key_features = formula_data.get("keyFeatures", [])
            feature_benefits = [f.get("title", "") for f in key_features if f.get("title")]
            
            # Get extracted parameters for primary concerns/benefits
            extracted_params = result.get("extractedParameters", {})
            primary_concern = extracted_params.get("primaryConcern", "")
            secondary_concerns = extracted_params.get("secondaryConcerns", [])
            all_concerns = [primary_concern] + (secondary_concerns if secondary_concerns else [])
            
            # Calculate advantage for each competitor
            for competitor in market_comparison:
                if not isinstance(competitor, dict):
                    continue
                
                competitor_price = competitor.get("price", 0) or competitor.get("mrp", 0)
                competitor_size_raw = str(competitor.get("size", "0")).strip()
                competitor_note = competitor.get("note", "").lower()
                
                # ALL SIZES ARE IN GRAMS (g) - convert ml to g if needed (1ml ≈ 1g for cosmetics)
                # Extract numeric size - treat everything as grams
                competitor_size_str = competitor_size_raw.replace("g", "").replace("ml", "").replace("G", "").replace("ML", "").replace("mL", "").strip()
                try:
                    competitor_size = float(competitor_size_str) if competitor_size_str else 0
                    # If original had "ml", it's already approximately grams (1ml ≈ 1g for cosmetics)
                except:
                    competitor_size = 0
                
                competitor_price_per_unit = competitor.get("pricePerGram", 0)
                
                # Calculate price per gram (ALL in grams)
                unit = "/g"  # Always grams
                if competitor_size > 0 and competitor_price > 0:
                    competitor_price_per_unit = competitor_price / competitor_size
                    competitor["pricePerGram"] = competitor_price_per_unit  # Keep field name for compatibility (but it's per gram)
                
                # Build comprehensive advantage statement
                advantage_parts = []
                
                # 1. Price advantage (if significant)
                if user_cost_per_unit > 0 and competitor_price_per_unit > 0:
                    cost_difference = competitor_price_per_unit - user_cost_per_unit
                    
                    if cost_difference > 0.05:  # User is cheaper
                        advantage_parts.append(f"₹{cost_difference:.2f}{unit} cheaper")
                    elif cost_difference < -0.05:  # User is more expensive
                        # Only mention if significantly more expensive, otherwise focus on value
                        if abs(cost_difference) > user_cost_per_unit * 0.3:  # 30% more expensive
                            advantage_parts.append(f"₹{abs(cost_difference):.2f}{unit} more expensive")
                
                # 2. Ingredient advantage
                if hero_ingredient_names:
                    # Check if competitor note mentions basic/simple ingredients
                    if any(word in competitor_note for word in ["basic", "simple", "only", "just"]):
                        advantage_parts.append(f"Premium actives ({', '.join(hero_ingredient_names[:3])})")
                    elif len(hero_ingredient_names) >= 3:
                        advantage_parts.append(f"More active ingredients ({len(hero_actives)} vs typical 1-2)")
                
                # 3. Benefit/Feature advantage
                if feature_benefits:
                    # Highlight unique benefits
                    unique_benefits = []
                    for benefit in feature_benefits[:2]:  # Top 2 benefits
                        if benefit and len(benefit) < 40:  # Keep it concise
                            unique_benefits.append(benefit)
                    if unique_benefits:
                        advantage_parts.append(f"Multi-benefit: {', '.join(unique_benefits)}")
                
                # 4. Concern targeting advantage
                if all_concerns and len(all_concerns) > 1:
                    # If formula targets multiple concerns vs competitor's basic positioning
                    if "basic" in competitor_note or "only" in competitor_note:
                        advantage_parts.append(f"Targets {len(all_concerns)} concerns")
                
                # 5. Value positioning
                if not advantage_parts:  # Fallback if no specific advantages found
                    if user_cost_per_unit > 0:
                        # Compare value proposition
                        if competitor_price_per_unit > 0:
                            value_ratio = competitor_price_per_unit / user_cost_per_unit if user_cost_per_unit > 0 else 1
                            if value_ratio > 2:
                                advantage_parts.append("Better value proposition")
                            elif value_ratio < 0.5:
                                advantage_parts.append("Premium ingredients")
                            else:
                                advantage_parts.append("Competitive value")
                        else:
                            advantage_parts.append("Better cost efficiency")
                    else:
                        advantage_parts.append("Premium formulation")
                
                # Combine advantages into final statement
                if len(advantage_parts) == 1:
                    advantage = advantage_parts[0]
                elif len(advantage_parts) == 2:
                    advantage = f"{advantage_parts[0]} + {advantage_parts[1]}"
                elif len(advantage_parts) >= 3:
                    # Prioritize: price first, then ingredients, then benefits
                    price_adv = [a for a in advantage_parts if "₹" in a or "cheaper" in a.lower() or "expensive" in a.lower()]
                    other_adv = [a for a in advantage_parts if a not in price_adv]
                    if price_adv:
                        advantage = f"{price_adv[0]} + {other_adv[0] if other_adv else 'better value'}"
                    else:
                        advantage = f"{advantage_parts[0]} + {advantage_parts[1]}"
                else:
                    advantage = "Better overall value"
                
                competitor["advantage"] = advantage
                competitor["yourAdvantage"] = advantage  # Also add for frontend compatibility
        
        # Update the result with fixed data
        result["formula"] = formula_data
        
        # ========================================================================
        # APPLY NEW COST CALCULATION RULES (Post-processing)
        # ========================================================================
        print("💰 Applying new cost calculation rules (20% formula margin, wastage, manufacturer margin)...")
        
        # Extract cost from technical formula
        technical_formula = formula_data.get("technicalFormula", {})
        base_cost_per_100g = technical_formula.get("totalCostPer100g", 0)
        
        # VALIDATION: Check for obvious calculation errors
        # Water should never contribute more than ₹0.10 per 100g
        # If total cost is suspiciously high (>₹500/100g for basic products), log warning
        if base_cost_per_100g > 500:
            print(f"⚠️ WARNING: Total cost per 100g is ₹{base_cost_per_100g} - this seems unusually high!")
            print(f"   Expected range: ₹30-150/100g for most products")
            print(f"   This may indicate a calculation error (e.g., water cost miscalculation)")
            print(f"   Continuing with post-processing, but please verify the cost calculation")
        
        if base_cost_per_100g > 0:
            # Create cost_analysis structure for post-processor
            cost_analysis = {
                "raw_material_cost": {
                    "total_per_100g": base_cost_per_100g
                }
            }
            
            # Apply post-processor
            product_type = wish_data.get('productType', 'serum')
            cost_analysis = post_process_cost_analysis(cost_analysis, product_type)
            
            # Add packaging options to businessNumbers
            if "packaging_options" in cost_analysis:
                if "businessNumbers" not in formula_data:
                    formula_data["businessNumbers"] = {}
                formula_data["businessNumbers"]["packagingOptions"] = cost_analysis["packaging_options"]
                formula_data["businessNumbers"]["packagingBySize"] = cost_analysis.get("packaging_by_size", {})
                formula_data["businessNumbers"]["costCalculationSummary"] = cost_analysis.get("cost_calculation_summary", {})
            
            # Update technical formula with adjusted cost
            technical_formula["totalCostPer100g"] = cost_analysis["raw_material_cost"].get("adjusted_per_100g", base_cost_per_100g)
            technical_formula["baseCostPer100g"] = base_cost_per_100g
            technical_formula["costMarginPercent"] = 20.0
            formula_data["technicalFormula"] = technical_formula
            
            print(f"   ✅ Cost post-processing complete: Base ₹{base_cost_per_100g}/100g → Adjusted ₹{cost_analysis['raw_material_cost'].get('adjusted_per_100g', base_cost_per_100g)}/100g")
        else:
            print("   ⚠️ Warning: No cost data found in technical formula, skipping post-processing")
        
        # ========================================================================
        # ENSURE RECOMMENDED PACKAGING OPTION IS PRESENT
        # ========================================================================
        print("📦 Ensuring recommended packaging option is present...")
        
        # Check if packagingOptions exists in formula
        packaging_options = formula_data.get("packagingOptions", {})
        
        # Check if packagingOptions is missing or incomplete
        needs_generation = (
            not packaging_options or 
            not packaging_options.get("recommendation") or
            not packaging_options.get("recommendedSizes") or
            not packaging_options.get("recommendedTypes")
        )
        
        # If packagingOptions is missing or incomplete, generate it
        if needs_generation:
            # Get product type and category
            product_type = wish_data.get('productType', 'serum')
            unit = get_unit_for_product_type(product_type)
            category = "liquid" if unit == "ml" else "solid"
            
            # Get packaging options from post-processor or packaging data
            packaging_by_size = formula_data.get("businessNumbers", {}).get("packagingBySize", {})
            
            # Determine recommended sizes based on product type
            if category == "liquid":
                recommended_sizes = ["30g", "50g", "100g"]
                # For serums, prefer 30g; for toners/cleansers, prefer 50g-100g
                if "serum" in product_type.lower() or "essence" in product_type.lower():
                    primary_size = "30g"
                elif "toner" in product_type.lower() or "cleanser" in product_type.lower():
                    primary_size = "50g"
                else:
                    primary_size = "50g"
            else:  # solid
                recommended_sizes = ["30g", "50g", "100g"]
                # For creams, prefer 50g; for eye creams, prefer 30g
                if "eye" in product_type.lower():
                    primary_size = "30g"
                elif "cream" in product_type.lower() or "lotion" in product_type.lower():
                    primary_size = "50g"
                else:
                    primary_size = "50g"
            
            # Determine recommended types based on product type
            if category == "liquid":
                if "serum" in product_type.lower():
                    recommended_types = [
                        {"type": "dropper_bottle", "description": "Precise application, prevents contamination", "note": "Best for serums"},
                        {"type": "airless_pump", "description": "Preserves active ingredients, hygienic", "note": "Premium option"}
                    ]
                    primary_type = "dropper_bottle"
                elif "toner" in product_type.lower():
                    recommended_types = [
                        {"type": "pump_bottle", "description": "Easy to use, controlled dispensing", "note": "Standard for toners"},
                        {"type": "spray_bottle", "description": "Convenient application", "note": "Alternative option"}
                    ]
                    primary_type = "pump_bottle"
                else:
                    recommended_types = [
                        {"type": "pump_bottle", "description": "Standard packaging", "note": "Versatile option"},
                        {"type": "dropper_bottle", "description": "Precise dispensing", "note": "For concentrated products"}
                    ]
                    primary_type = "pump_bottle"
            else:  # solid
                if "eye" in product_type.lower():
                    recommended_types = [
                        {"type": "jar", "description": "Small size, easy to apply", "note": "Standard for eye creams"},
                        {"type": "airless_jar", "description": "Preserves ingredients, hygienic", "note": "Premium option"}
                    ]
                    primary_type = "jar"
                elif "cream" in product_type.lower() or "lotion" in product_type.lower():
                    recommended_types = [
                        {"type": "jar", "description": "Classic feel, easy to use", "note": "Use spatula for hygiene"},
                        {"type": "tube", "description": "Hygienic, portable", "note": "Good for travel"},
                        {"type": "airless_jar", "description": "Preserves active ingredients", "note": "Premium option"}
                    ]
                    primary_type = "jar"
                else:
                    recommended_types = [
                        {"type": "jar", "description": "Standard packaging", "note": "Versatile option"},
                        {"type": "tube", "description": "Hygienic dispensing", "note": "Alternative option"}
                    ]
                    primary_type = "jar"
            
            # Build recommended sizes list
            recommended_sizes_list = []
            for size in recommended_sizes:
                if size in packaging_by_size:
                    # Mark primary size as popular
                    recommended_sizes_list.append({
                        "size": size,
                        "description": f"Standard {size} size",
                        "popular": size == primary_size
                    })
            
            # If no sizes found, add default
            if not recommended_sizes_list:
                recommended_sizes_list = [
                    {"size": primary_size, "description": f"Standard {primary_size} size", "popular": True}
                ]
            
            # Generate recommendation text
            recommendation_text = f"For {product_type}, we recommend {primary_size} {primary_type} packaging. "
            if category == "liquid":
                if "serum" in product_type.lower():
                    recommendation_text += "Dropper bottles provide precise application and prevent contamination, ideal for concentrated serums."
                else:
                    recommendation_text += "Pump bottles offer easy dispensing and controlled usage."
            else:
                if "eye" in product_type.lower():
                    recommendation_text += "Small jars are perfect for eye creams, allowing precise application around the delicate eye area."
                else:
                    recommendation_text += "Jars provide a premium feel and easy access, while tubes offer better hygiene and portability."
            
            # Set packagingOptions in formula (merge with existing if present)
            if packaging_options:
                # Merge with existing data, but prioritize our generated data
                formula_data["packagingOptions"] = {
                    **packaging_options,  # Keep existing fields
                    "recommendedSizes": recommended_sizes_list,
                    "recommendedTypes": recommended_types,
                    "recommendation": recommendation_text
                }
            else:
                # Create new packagingOptions
                formula_data["packagingOptions"] = {
                    "recommendedSizes": recommended_sizes_list,
                    "recommendedTypes": recommended_types,
                    "recommendation": recommendation_text
                }
            
            print(f"   ✅ Generated recommended packaging option: {primary_size} {primary_type}")
        else:
            print("   ✅ Recommended packaging option already present and complete")
        
        # Update the result with cost-processed data
        result["formula"] = formula_data
        
        print("🎉 Make a Wish pipeline complete!")
        return result
        
    except Exception as e:
        print(f"❌ Error in formula generation: {e}")
        import traceback
        traceback.print_exc()
        raise

