"""
Trend Synthesis Module
======================

Transforms raw MongoDB trend records into structured, actionable intelligence
using Claude API. This replaces expensive SerpAPI calls with intelligent synthesis.

Flow:
1. Receives parsed_data (from NLP) + matched_trends (from MongoDB)
2. Calls Claude API with trend synthesis prompt
3. Returns structured JSON ready for frontend rendering

Cost: ~₹4-7 per wish (vs ₹25-50 with SerpAPI) = 85% cost reduction
"""

import os
import json
from typing import Dict, Any, Optional, List
from datetime import datetime

# Claude API setup
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    anthropic = None

from app.config import CLAUDE_API_KEY, CLAUDE_MODEL

# Initialize Claude client
if ANTHROPIC_AVAILABLE and CLAUDE_API_KEY:
    try:
        claude_client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        print(f"✅ Trend Synthesis: Claude client initialized with model: {CLAUDE_MODEL}")
    except Exception as e:
        print(f"⚠️ Trend Synthesis: Could not initialize Claude client: {e}")
        claude_client = None
else:
    claude_client = None
    if not ANTHROPIC_AVAILABLE:
        print("⚠️ Trend Synthesis: anthropic package not available")


# ============================================================================
# SYSTEM PROMPT
# ============================================================================

TREND_SYNTHESIS_SYSTEM_PROMPT = """You are a cosmetic market intelligence analyst for Formulynx, a formulation intelligence platform serving India's beauty and personal care market.

You receive:
1. PARSED WISH DATA — the user's product intent (ingredients, benefits, product type, category)
2. MATCHED TREND RECORDS — pre-fetched Google Trends data from MongoDB, organized by query level (L1-L5)

Your job: Transform raw trend records into a structured, actionable intelligence report that helps the user decide whether to proceed with this formulation, how to position it, and what risks to watch.

═══════════════════════════════════════════════════════════════════════════════
CORE PRINCIPLES
═══════════════════════════════════════════════════════════════════════════════

1. SIGNIFICANCE FILTERING (CRITICAL)
   You MUST filter out noise. Not every matched record deserves screen space.
   Apply these thresholds before including ANY data point:

   KEYWORD/QUERY INCLUSION RULES:
   • Only include keywords with trend_score ≥ 20 (anything below is statistical noise)
   • Only show "Alternatives" (related queries) if they score ≥ 15 AND are genuinely relevant to the product type (not tangential matches)
   • Remove keyword results where the product_format does NOT match the wish (e.g., "Hair Oil" appearing for a face gel wish — exclude entirely)
   • Maximum 8 keyword entries in the Related Keywords section. Rank by relevance to the wish, not just score

   COMPETITIVE LANDSCAPE RULES:
   • Only include brands with trend_score ≥ 30
   • Maximum 6 brand entries — show top performers only
   • Only include brands whose product actually competes in the same category + format
   • If fewer than 3 brands qualify, note "Limited competitive data" instead of padding with irrelevant brands

   REGIONAL DATA RULES:
   • Only show top 5 regions by score
   • Flag as "Surprise market" ONLY if the region is NOT in India's top 8 beauty markets (Maharashtra, Karnataka, Delhi, Tamil Nadu, Telangana, Kerala, West Bengal, Gujarat) AND scores ≥ 50
   • If all regional scores are < 20, omit the regional section entirely and note "Insufficient regional data for this query"

   INGREDIENT-LEVEL TREND RULES:
   • Only create a per-ingredient deep-dive tab for ingredients that have ≥ 2 matched trend records
   • If an ingredient has only 1 record with score < 30, fold it into a summary line instead of a full tab
   • For the Interest Over Time chart: if > 60% of timeline values are 0, flag the data as "Sporadic/unreliable" and reduce confidence accordingly

   SEASONALITY RULES:
   • Only include seasonality section if timeline data spans ≥ 9 months
   • Calculate "Swing" as (peak_month_score - lowest_month_score). If swing < 15, report "No significant seasonal pattern" instead of showing a chart
   • If swing ≥ 15, identify OPTIMAL (1-2 months before peak), GOOD (secondary peak months), and AVOID (lowest months) windows

   SYNTHESIS SCORING:
   • Opportunity Score must be calculated from actual data, not estimated. Use the scoring rubric defined below.
   • If total data points < 5 across all matched records, set confidence = "Low" regardless of scores
   • Never assign "High" confidence unless ≥ 15 data points AND data spans ≥ 6 months

2. HONESTY OVER ENCOURAGEMENT
   Do NOT inflate opportunity signals. If the data suggests weak demand, say so clearly.
   Users pay for this intelligence — misleading optimism destroys trust.
   
   Specific honesty rules:
   • If trend_score < 30 for the hero ingredient in the user's wished format, explicitly state "Low consumer search interest"
   • If yoy_growth is negative, never classify trend_direction as "Rising"
   • If a single brand dominates (>60% of branded search), call out the barrier to entry explicitly
   • If rising_queries are empty or all have growth < 50%, do NOT claim the category is "growing rapidly"

3. INDIA-MARKET SPECIFICITY
   All insights must be grounded in Indian market context:
   • Price references in ₹
   • Regional insights reference Indian states/cities
   • Competitive landscape focuses on brands available in India
   • Seasonal patterns account for Indian weather (summer, monsoon, winter, wedding season, festivals)

4. ACTIONABILITY
   Every section must answer: "So what should the user DO with this information?"
   • Regional data → "Focus D2C marketing in X, Y states"
   • Competitive data → "Position against X at ₹Y price point" or "Differentiate via Z"
   • Timing data → "Launch by Month X to capture peak"
   • Risk data → Specific mitigation steps, not vague warnings

═══════════════════════════════════════════════════════════════════════════════
OPPORTUNITY SCORE RUBRIC (0-100)
═══════════════════════════════════════════════════════════════════════════════

Calculate each sub-score independently, then compute weighted total.

DEMAND SCORE (0-25):
  hero_score = hero ingredient's trend_score in wished format
  growth = yoy_growth of hero ingredient
  
  Base: (hero_score / 100) × 15
  Growth bonus: 
    if growth > 30%: +8
    if growth 10-30%: +5
    if growth 0-10%: +2
    if growth < 0: +0
  Timeline reliability penalty:
    if > 50% of timeline values are 0: halve the base score
    if data_points < 3: cap at 10
  
  Maximum: 25

COMPETITION SCORE (0-25):
  branded_queries_count = number of L3 brand records matched
  dominant_brand_share = highest brand's score / sum of all brand scores
  
  Low competition (0-3 brands, no dominant): 20-25
  Moderate (4-8 brands, no dominant >50%): 12-19
  High (8+ brands OR one dominant >50%): 5-11
  Very high (dominant >70% AND >8 brands): 0-4

TIMING SCORE (0-20):
  Based on seasonality and current position relative to peak:
  
  Approaching peak (1-3 months before): 16-20
  At peak: 10-15 (already competing at high noise)
  Post-peak (1-3 months after): 5-9
  No clear seasonal pattern: 10 (neutral)
  Declining trend (negative yoy): 0-5

FEASIBILITY SCORE (0-15):
  Based on ingredient availability and formulation complexity:
  
  Well-established ingredients with Indian supply chain: 12-15
  Established but premium/imported: 8-11
  Emerging with limited Indian supply: 4-7
  Novel with no established supply chain: 0-3
  
  Bonus: if rising_queries include consumer education queries (e.g., "what is X", "X benefits"): +0 (this means consumers don't know the ingredient yet — neutral to negative for feasibility)
  Penalty: if zero PAA/consumer questions in related queries: -2 (no organic consumer interest)

MARGIN SCORE (0-15):
  Based on competitive pricing landscape:
  
  If shopping_data available:
    Wide price spread (max/min ratio > 3x): 10-15 (room to position)
    Narrow price spread (ratio < 2x): 5-9 (compressed margins)
    Premium dominated (avg_price > ₹1000): 8-12 if user targets mass/masstige
    Mass dominated (avg_price < ₹300): 3-7 (race to bottom)
  
  If no shopping_data: assign 8 (neutral) with note "Pricing data unavailable"

OPPORTUNITY SCORE = Demand + Competition + Timing + Feasibility + Margin

TIER CLASSIFICATION:
  80-100: "Pursue" — Strong signals across all dimensions
  60-79:  "Consider" — Good opportunity with manageable risks  
  40-59:  "Monitor" — Mixed signals, needs further validation
  20-39:  "Caution" — Weak demand or high barriers
  0-19:   "Avoid" — Data does not support this product direction

CONFIDENCE LEVEL:
  High: ≥ 15 matched records, ≥ 6 months data, hero ingredient score ≥ 40
  Medium: 8-14 records, ≥ 3 months data
  Low: < 8 records OR < 3 months data OR > 50% timeline zeros

═══════════════════════════════════════════════════════════════════════════════
TREND CLASSIFICATION LOGIC
═══════════════════════════════════════════════════════════════════════════════

Based on the hero ingredient's primary trend record:

  "Explosive_growth": yoy_growth > 50% AND trend_score ≥ 40 AND ≥ 2 breakout queries
  "Strong_growth":    yoy_growth > 25% AND trend_score ≥ 30
  "Steady_growth":    yoy_growth 10-25% AND trend_score ≥ 20
  "Stable":           yoy_growth -10% to 10% AND trend_score ≥ 50
  "Mature_stable":    yoy_growth -10% to 10% AND trend_score ≥ 70 (well-established, saturated)
  "Early_stage":      trend_score < 30 AND yoy_growth > 0 (interest exists but low volume)
  "Declining":        yoy_growth < -10%
  "Sporadic":         > 60% of timeline values are 0 (not a real trend, just noise)

IMPORTANT: "Explosive_growth" with trend_score < 30 is misleading. A 200% increase from score 5 to 15 is not explosive — it is noise. Always cross-check growth % against absolute score.

═══════════════════════════════════════════════════════════════════════════════
OUTPUT FORMAT
═══════════════════════════════════════════════════════════════════════════════

Return a single JSON object with the structure defined below. 
Every field is required unless marked (CONDITIONAL).
Use null for fields where data is genuinely unavailable.
Do NOT invent data. If a section cannot be populated due to insufficient records, include the section with an appropriate empty state message."""


# ============================================================================
# USER PROMPT BUILDER
# ============================================================================

def build_trend_synthesis_user_prompt(
    parsed_data: Dict[str, Any],
    matched_trends: Dict[str, Any]
) -> str:
    """
    Build the user prompt for trend synthesis.
    
    Args:
        parsed_data: Parsed wish data from NLP stage
        matched_trends: MongoDB trend records organized by level (L1-L5)
        
    Returns:
        Formatted user prompt string
    """
    # Extract parsed wish data
    category = parsed_data.get("category", "unknown")
    product_type_obj = parsed_data.get("product_type", {})
    product_type = product_type_obj.get("id") or product_type_obj.get("name") if isinstance(product_type_obj, dict) else str(product_type_obj) if product_type_obj else "unknown"
    product_format = parsed_data.get("product_format") or product_type
    
    # Extract hero ingredients
    detected_ingredients = parsed_data.get("detected_ingredients", [])
    hero_ingredients = []
    if detected_ingredients:
        hero_ingredients = [ing.get("name", str(ing)) if isinstance(ing, dict) else str(ing) for ing in detected_ingredients]
    else:
        # Fallback to hero_ingredients if available
        hero_ingredients = parsed_data.get("hero_ingredients", [])
    
    # Extract benefits
    detected_benefits = parsed_data.get("detected_benefits", [])
    if not detected_benefits:
        detected_benefits = parsed_data.get("benefits", [])
    
    # Extract skin/hair types
    skin_hair_type = []
    if parsed_data.get("detected_skin_types"):
        skin_hair_type = parsed_data.get("detected_skin_types", [])
    elif parsed_data.get("detected_hair_concerns"):
        skin_hair_type = parsed_data.get("detected_hair_concerns", [])
    
    complexity = parsed_data.get("complexity", "classic")
    
    # Extract matched trends by level
    l1_trends = matched_trends.get("level_1_ingredient_trends", {}) or matched_trends.get("hero_ingredient_trends", {})
    l2_trends = matched_trends.get("level_2_competing_approaches", []) or matched_trends.get("competitive_landscape", [])
    l3_trends = matched_trends.get("level_3_brand_trends", []) or matched_trends.get("brand_intelligence", [])
    l4_trends = matched_trends.get("comparison_data", []) or matched_trends.get("head_to_head", [])
    l5_trends = matched_trends.get("derivative_trends", [])
    
    # Build prompt
    prompt = f"""Analyze the following trend data for a user's formulation wish and produce a structured intelligence report.

═══════════════════════════════════════════════════════════════════════════════
PARSED WISH DATA
═══════════════════════════════════════════════════════════════════════════════

Category: {category}
Product type: {product_type}
Product format: {product_format}
Hero ingredients: {json.dumps(hero_ingredients, indent=2)}
Detected benefits: {json.dumps(detected_benefits, indent=2)}
Detected skin/hair type: {json.dumps(skin_hair_type, indent=2)}
Complexity: {complexity}

═══════════════════════════════════════════════════════════════════════════════
MATCHED TREND RECORDS FROM MONGODB
═══════════════════════════════════════════════════════════════════════════════

--- L1: Hero Ingredient Trends ---
{json.dumps(l1_trends, indent=2, default=str)}

--- L2: Competitive Landscape ---
{json.dumps(l2_trends, indent=2, default=str)}

--- L3: Brand Intelligence ---
{json.dumps(l3_trends, indent=2, default=str)}

--- L4: Head-to-Head Comparisons ---
{json.dumps(l4_trends, indent=2, default=str)}

--- L5: Derivative Trends ---
{json.dumps(l5_trends, indent=2, default=str)}

═══════════════════════════════════════════════════════════════════════════════
INSTRUCTIONS
═══════════════════════════════════════════════════════════════════════════════

Apply SIGNIFICANCE FILTERING. Remove all records that fail thresholds.
Produce the JSON output per the required structure.
Ensure every insight is data-grounded, relevant, actionable, and honest.

Return ONLY valid JSON. No markdown, no explanation, no preamble.
"""
    
    return prompt


# ============================================================================
# VALIDATION FUNCTIONS
# ============================================================================

def validate_trend_synthesis(data: Dict[str, Any]) -> bool:
    """
    Validate the synthesized trend data structure.
    
    Args:
        data: The synthesized JSON response
    
    Returns:
        True if valid, raises ValueError if invalid
    """
    required_fields = [
        'related_keyword_trends',
        'competitive_landscape',
        'trend_by_ingredient',
        'insights_breakdown',
        'marketing_angles',
        'risks',
        'next_steps',
        'product_recommendations',
        'key_insights',
        'metadata'
    ]
    
    for field in required_fields:
        if field not in data:
            raise ValueError(f"Missing required field: {field}")
    
    # Validate opportunity scores are within bounds
    for ingredient in data.get('trend_by_ingredient', []):
        synthesis = ingredient.get('synthesis', {})
        if synthesis:
            opp_score = synthesis.get('opportunity_score', 0)
            if opp_score < 0 or opp_score > 100:
                raise ValueError(f"Invalid opportunity score: {opp_score} (must be 0-100)")
            
            # Validate sub-scores sum approximately equals opportunity score
            breakdown = synthesis.get('scores_breakdown', {})
            if breakdown:
                sub_total = (
                    breakdown.get('demand', {}).get('score', 0) +
                    breakdown.get('competition', {}).get('score', 0) +
                    breakdown.get('timing', {}).get('score', 0) +
                    breakdown.get('feasibility', {}).get('score', 0) +
                    breakdown.get('margin', {}).get('score', 0)
                )
                # Allow 2 point tolerance for rounding
                if abs(sub_total - opp_score) > 2:
                    print(f"⚠️ Warning: Score mismatch for {ingredient.get('ingredient_name')}: sum={sub_total}, reported={opp_score}")
    
    return True


# ============================================================================
# MAIN SYNTHESIS FUNCTION
# ============================================================================

async def synthesize_trends(
    parsed_data: Dict[str, Any],
    matched_trends: Dict[str, Any],
    use_cache: bool = True
) -> Dict[str, Any]:
    """
    Synthesize raw MongoDB trend records into structured intelligence.
    
    This is the main function called after matchTrendsForWish() returns.
    
    Args:
        parsed_data: Parsed wish data from NLP stage (contains category, product_type, 
                     detected_ingredients, detected_benefits, etc.)
        matched_trends: MongoDB trend records organized by level (L1-L5)
        use_cache: Whether to use prompt caching (default: True)
    
    Returns:
        Structured JSON ready for frontend rendering:
        {
            "related_keyword_trends": [...],
            "competitive_landscape": [...],
            "regional_insights": {...},
            "trend_by_ingredient": [...],
            "insights_breakdown": {...},
            "marketing_angles": [...],
            "risks": [...],
            "next_steps": [...],
            "product_recommendations": [...],
            "key_insights": [...],
            "metadata": {...}
        }
    
    Raises:
        RuntimeError: If Claude client is not available
        ValueError: If synthesis response is invalid
    """
    if not claude_client:
        raise RuntimeError("Claude client not initialized. Check CLAUDE_API_KEY environment variable.")
    
    if not CLAUDE_MODEL:
        raise RuntimeError("Claude model not configured. Check CLAUDE_MODEL environment variable.")
    
    print(f"[TREND SYNTHESIS] 🚀 Starting trend synthesis...")
    print(f"[TREND SYNTHESIS]   Parsed data keys: {list(parsed_data.keys())}")
    print(f"[TREND SYNTHESIS]   Matched trends keys: {list(matched_trends.keys())}")
    
    # Build prompts
    system_prompt = TREND_SYNTHESIS_SYSTEM_PROMPT
    user_prompt = build_trend_synthesis_user_prompt(parsed_data, matched_trends)
    
    print(f"[TREND SYNTHESIS]   System prompt length: {len(system_prompt)} chars")
    print(f"[TREND SYNTHESIS]   User prompt length: {len(user_prompt)} chars")
    
    # Get cache control if caching enabled
    cache_control = None
    if use_cache:
        try:
            from app.ai_ingredient_intelligence.logic.prompt_cache_manager import get_cache_control_for_prompt
            cache_control = get_cache_control_for_prompt(
                system_prompt=system_prompt,
                prompt_type="trend_synthesis",
                claude_client=claude_client,
                ttl="1h"
            )
        except Exception as e:
            print(f"[TREND SYNTHESIS] ⚠️ Could not get cache control: {e}")
    
    # Prepare API call (don't include cache_control - SDK version doesn't support it)
    api_params = {
        "model": CLAUDE_MODEL,
        "max_tokens": 4000,
        "temperature": 0.3,
        "system": system_prompt,
        "messages": [
                {"role": "user", "content": user_prompt}
            ]
    }
    
    # Note: cache_control is available but not used due to SDK compatibility
    if cache_control:
        print(f"[TREND SYNTHESIS] ⚠️ Cache control available but not using (SDK compatibility)")
    
    try:
        # Call Claude API
        print(f"[TREND SYNTHESIS] 📡 Calling Claude API...")
        response = claude_client.messages.create(**api_params_final)
        
        if not response.content or len(response.content) == 0:
            raise ValueError("Empty response from Claude API")
        
        content = response.content[0].text.strip()
        
        if not content:
            raise ValueError("Empty text in Claude response")
        
        # Extract JSON from response (handle markdown code blocks if present)
        json_content = content
        if "```json" in content:
            json_content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            json_content = content.split("```")[1].split("```")[0].strip()
        
        # Parse JSON with better error handling
        try:
            synthesized = json.loads(json_content)
        except json.JSONDecodeError as json_err:
            print(f"[TREND SYNTHESIS] ❌ JSON parse error: {json_err}")
            print(f"[TREND SYNTHESIS]   Error at position: {json_err.pos if hasattr(json_err, 'pos') else 'unknown'}")
            print(f"[TREND SYNTHESIS]   Response length: {len(json_content)} chars")
            
            # Try to extract the problematic section
            if hasattr(json_err, 'pos') and json_err.pos:
                error_pos = json_err.pos
                start = max(0, error_pos - 200)
                end = min(len(json_content), error_pos + 200)
                print(f"[TREND SYNTHESIS]   Problematic section: {json_content[start:end]}")
            
            # Try to fix common JSON issues
            try:
                # Try removing trailing commas
                json_content_fixed = json_content.replace(',\n}', '\n}').replace(',\n]', '\n]')
                synthesized = json.loads(json_content_fixed)
                print(f"[TREND SYNTHESIS] ✅ Fixed JSON by removing trailing commas")
            except:
                # Try to extract JSON from a larger context
                try:
                    # Find the first { and last } to extract valid JSON
                    first_brace = json_content.find('{')
                    last_brace = json_content.rfind('}')
                    if first_brace >= 0 and last_brace > first_brace:
                        json_content_fixed = json_content[first_brace:last_brace+1]
                        synthesized = json.loads(json_content_fixed)
                        print(f"[TREND SYNTHESIS] ✅ Fixed JSON by extracting from braces")
                    else:
                        raise ValueError(f"Invalid JSON in Claude response: {str(json_err)}")
                except Exception as fix_err:
                    print(f"[TREND SYNTHESIS] ❌ Could not fix JSON: {fix_err}")
                    # Save problematic response for debugging
                    import os
                    debug_dir = "debug_responses"
                    os.makedirs(debug_dir, exist_ok=True)
                    debug_file = os.path.join(debug_dir, f"trend_synthesis_error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
                    with open(debug_file, 'w', encoding='utf-8') as f:
                        f.write(f"Error: {json_err}\n\n")
                        f.write(f"Full response:\n{content}\n\n")
                        f.write(f"Extracted JSON:\n{json_content}\n")
                    print(f"[TREND SYNTHESIS]   Saved problematic response to: {debug_file}")
                    raise ValueError(f"Invalid JSON in Claude response: {str(json_err)}")
        
        # Validate structure
        validate_trend_synthesis(synthesized)
        
        print(f"[TREND SYNTHESIS] ✅ Synthesis complete!")
        print(f"[TREND SYNTHESIS]   Ingredients analyzed: {len(synthesized.get('trend_by_ingredient', []))}")
        print(f"[TREND SYNTHESIS]   Keywords: {len(synthesized.get('related_keyword_trends', []))}")
        print(f"[TREND SYNTHESIS]   Brands: {len(synthesized.get('competitive_landscape', []))}")
        
        return synthesized
        
    except (TypeError, AttributeError) as cache_error:
        # Retry without cache_control if SDK doesn't support it
        error_str = str(cache_error).lower()
        if "cache_control" in error_str or "unexpected keyword" in error_str:
            # SDK version doesn't support cache_control - this is normal for older SDK versions
            print(f"[TREND SYNTHESIS] ⚠️ Cache control not supported, retrying without it...")
            api_params_clean = {k: v for k, v in api_params.items() if k != "cache_control"}
            if "extra_body" in api_params_clean:
                api_params_clean["extra_body"] = {k: v for k, v in api_params_clean["extra_body"].items() if k != "cache_control"}
                if not api_params_clean["extra_body"]:
                    del api_params_clean["extra_body"]
            
            response = claude_client.messages.create(**api_params_clean)
            content = response.content[0].text.strip()
            
            # Extract and parse JSON with same error handling
            json_content = content
            if "```json" in content:
                json_content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_content = content.split("```")[1].split("```")[0].strip()
            
            try:
                synthesized = json.loads(json_content)
            except json.JSONDecodeError as json_err:
                print(f"[TREND SYNTHESIS] ❌ JSON parse error (retry): {json_err}")
                # Try same fixes as above
                try:
                    json_content_fixed = json_content.replace(',\n}', '\n}').replace(',\n]', '\n]')
                    synthesized = json.loads(json_content_fixed)
                except:
                    first_brace = json_content.find('{')
                    last_brace = json_content.rfind('}')
                    if first_brace >= 0 and last_brace > first_brace:
                        json_content_fixed = json_content[first_brace:last_brace+1]
                        synthesized = json.loads(json_content_fixed)
                    else:
                        raise ValueError(f"Invalid JSON in Claude response: {str(json_err)}")
            
            validate_trend_synthesis(synthesized)
            print(f"[TREND SYNTHESIS] ✅ Synthesis complete (without cache)!")
            return synthesized
        else:
            raise
        
    except Exception as e:
        print(f"[TREND SYNTHESIS] ❌ Error during synthesis: {e}")
        import traceback
        traceback.print_exc()
        raise
