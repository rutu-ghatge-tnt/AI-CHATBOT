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
import asyncio
from typing import Dict, Any, Optional, List, Tuple
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

⚠️ CRITICAL SPEED REQUIREMENT: Generate responses FAST. Keep ALL explanations to 1-2 sentences max. NO verbose paragraphs. Prioritize actionable insights over detailed descriptions. This is essential for sub-2-minute response times.

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

Return JSON with EXACT structure. Field names must match exactly. ⚠️ CRITICAL: Keep ALL text fields to 1-2 sentences MAX. NO paragraphs. Be direct and actionable. This is required for fast generation.

Required structure:
{
  "report_metadata": {generated_at (ISO), wish_summary {category, product_type, hero_ingredients[], detected_benefits[], complexity}, data_quality {total_records_analyzed, records_after_filtering, confidence_level, data_span_months, confidence_rationale}},
  "opportunity_assessment": {overall_score (0-100), tier (Pursue/Consider/Monitor/Caution/Avoid), confidence, headline, sub_scores {demand, competition, timing, feasibility, margin: each with score and rationale}, key_insight},
  "trend_classification": {primary_trend, hero_ingredient_analysis {ingredient, trend_score, peak_score, yoy_growth, classification_rationale}, supporting_ingredients {}, market_stage, market_stage_explanation},
  "competitive_landscape": {intensity, brand_count, top_competitors[] {brand, trend_score, positioning, strength, weakness}, emerging_threats[] {brand, growth, note}, white_space_opportunity, competitive_strategy {differentiation_levers[], avoid[]}},
  "regional_insights": {top_markets[] {region, score, tier, population, insight}, surprise_markets[] {region, score, note}, go_to_market_priority[] {phase, regions[], rationale}, channel_strategy {D2C_website, Amazon_Flipkart, Nykaa, Offline_retail}},
  "seasonality_analysis": {current_market_position, seasonal_patterns {ingredient_name: {peak_months[], peak_scores[], low_months[], low_scores[], swing, pattern}}, optimal_launch_window {primary, rationale}, secondary_windows[] {window, rationale}, avoid_windows[] {window, rationale}, launch_timeline {Month_-3_to_-1, Month_0, Month_1, Month_2-3, Month_4-6, Month_7-9, Month_10-12}},
  "ingredient_deep_dives[]": {ingredient, trend_score, trend_direction, yoy_growth, timeline_reliability, timeline_note, consumer_intent {top_queries[], rising_queries[], intent_analysis}, formulation_considerations {stability_challenge, pH_conflict, packaging}, competitive_positioning},
  "risk_assessment": {high_risks[] {risk, probability, impact, mitigation[]}, medium_risks[] {same}, low_risks[] {same}},
  "recommendations": {immediate_actions[] {action, timeline, owner, success_criteria}, launch_strategy[] {same}, pricing_strategy {recommended_price, rationale, price_testing, bundle_offer, discount_policy}, marketing_priorities[] {channel, budget_allocation, tactics[]}, success_metrics {Month_1-3, Month_4-6, Month_7-12: each with revenue, units_sold, CAC, ROAS, repeat_rate}},
  "executive_summary": {verdict (PURSUE/CONDITIONAL PROCEED/PLAN FOR NEXT QUARTER/MONITOR/AVOID), confidence, one_liner}
}

CRITICAL: Use exact field names. Be detailed but concise—prioritize actionable insights over verbosity. Use null for unavailable data."""


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
# TREND FILTERING FUNCTIONS (v2.0 - Advanced Keyword-Based Filtering)
# ============================================================================

# Import re for regex matching
import re

# Keyword maps for extraction
INGREDIENT_KEYWORD_MAP = {
    # Vitamin C family
    'vitamin c': 'vitamin_c', 'vit c': 'vitamin_c', 'ascorbic acid': 'vitamin_c',
    'l-ascorbic': 'vitamin_c', 'l ascorbic': 'vitamin_c', 'ascorbic': 'vitamin_c',
    'ethyl ascorbic': 'vitamin_c', 'sodium ascorbyl': 'vitamin_c', 'map vitamin c': 'vitamin_c',
    'ascorbyl glucoside': 'vitamin_c', 'thd ascorbate': 'vitamin_c',
    # Niacinamide
    'niacinamide': 'niacinamide', 'vitamin b3': 'niacinamide', 'nicotinamide': 'niacinamide',
    'niacin': 'niacinamide',
    # Retinoids
    'retinol': 'retinol', 'retinal': 'retinol', 'retinoid': 'retinol', 'vitamin a': 'retinol',
    'retinaldehyde': 'retinol', 'retin': 'retinol', 'tretinoin': 'retinol',
    'adapalene': 'retinol', 'retinyl palmitate': 'retinol', 'hpr': 'retinol',
    'granactive retinoid': 'retinol',
    # Hyaluronic Acid
    'hyaluronic acid': 'hyaluronic_acid', 'hyaluronic': 'hyaluronic_acid', 'ha serum': 'hyaluronic_acid',
    'sodium hyaluronate': 'hyaluronic_acid', 'hyaluron': 'hyaluronic_acid',
    'low molecular weight ha': 'hyaluronic_acid', 'multi molecular ha': 'hyaluronic_acid',
    # Salicylic Acid / BHA
    'salicylic acid': 'salicylic_acid', 'salicylic': 'salicylic_acid', 'bha': 'salicylic_acid',
    'beta hydroxy': 'salicylic_acid', 'beta hydroxy acid': 'salicylic_acid',
    'willow bark': 'salicylic_acid', 'salix alba': 'salicylic_acid',
    'salicylic acid shampoo': 'salicylic_acid_hair', 'salicylic scalp': 'salicylic_acid_hair',
    'bha shampoo': 'salicylic_acid_hair',
    # Glycolic / AHA
    'glycolic acid': 'glycolic_acid', 'glycolic': 'glycolic_acid', 'aha': 'glycolic_acid',
    'alpha hydroxy': 'glycolic_acid', 'alpha hydroxy acid': 'glycolic_acid',
    'fruit acid': 'glycolic_acid',
    # Lactic Acid
    'lactic acid': 'lactic_acid', 'lactic': 'lactic_acid',
    # Mandelic Acid
    'mandelic acid': 'mandelic_acid', 'mandelic': 'mandelic_acid',
    # Azelaic Acid
    'azelaic acid': 'azelaic_acid', 'azelaic': 'azelaic_acid',
    # Tranexamic Acid
    'tranexamic acid': 'tranexamic_acid', 'tranexamic': 'tranexamic_acid', 'txa': 'tranexamic_acid',
    # Kojic Acid
    'kojic acid': 'kojic_acid', 'kojic': 'kojic_acid',
    # PHA
    'pha': 'pha', 'polyhydroxy acid': 'pha', 'polyhydroxy': 'pha', 'gluconolactone': 'pha',
    'lactobionic acid': 'pha',
    # Peptides & Proteins
    'peptide': 'peptides', 'peptides': 'peptides', 'copper peptide': 'peptides',
    'copper peptides': 'peptides', 'matrixyl': 'peptides', 'argireline': 'peptides',
    'palmitoyl': 'peptides', 'palmitoyl tripeptide': 'peptides', 'ghk-cu': 'peptides',
    'acetyl hexapeptide': 'peptides', 'signal peptide': 'peptides',
    'collagen': 'collagen', 'marine collagen': 'collagen', 'plant collagen': 'collagen',
    'vegan collagen': 'collagen',
    'keratin': 'keratin', 'hydrolyzed keratin': 'keratin',
    # Brightening Agents
    'alpha arbutin': 'alpha_arbutin', 'arbutin': 'alpha_arbutin', 'beta arbutin': 'alpha_arbutin',
    'deoxyarbutin': 'alpha_arbutin',
    'glutathione': 'glutathione', 'l-glutathione': 'glutathione', 'reduced glutathione': 'glutathione',
    # Botanicals (Skincare) - key ones only
    'aloe vera': 'aloe_vera', 'aloe': 'aloe_vera', 'ghritkumari': 'aloe_vera',
    'tea tree': 'tea_tree', 'tea tree oil': 'tea_tree', 'melaleuca': 'tea_tree',
    'neem': 'neem', 'nimba': 'neem', 'azadirachta indica': 'neem',
    'turmeric': 'turmeric', 'haldi': 'turmeric', 'curcumin': 'turmeric',
    'saffron': 'saffron', 'kesar': 'saffron', 'kumkum': 'saffron',
    'sandalwood': 'sandalwood', 'chandan': 'sandalwood',
    'tulsi': 'tulsi', 'holy basil': 'tulsi',
    'ashwagandha': 'ashwagandha', 'withania': 'ashwagandha',
    'bakuchiol': 'bakuchiol', 'bakuchi': 'bakuchiol',
    'centella': 'centella_asiatica', 'centella asiatica': 'centella_asiatica', 'cica': 'centella_asiatica',
    'licorice': 'licorice_extract', 'licorice extract': 'licorice_extract', 'mulethi': 'mulethi',
    # Botanicals (Haircare)
    'bhringraj': 'bhringraj', 'bhringaraj': 'bhringraj',
    'brahmi': 'brahmi_hair', 'bacopa': 'brahmi_hair',
    'amla': 'amla_hair', 'amla hair': 'amla_hair', 'indian gooseberry': 'amla_hair',
    'shikakai': 'shikakai', 'reetha': 'reetha', 'soapnut': 'reetha',
    'methi': 'methi', 'fenugreek': 'methi',
    'henna': 'henna', 'mehndi': 'henna',
    'hibiscus': 'hibiscus', 'gudhal': 'hibiscus',
    # Oils & Butters
    'argan oil': 'argan_oil', 'argan': 'argan_oil',
    'jojoba oil': 'jojoba_oil', 'jojoba': 'jojoba_oil',
    'coconut oil': 'coconut_oil', 'nariyal tel': 'coconut_oil',
    'castor oil': 'castor_oil', 'arandi oil': 'castor_oil',
    'rosemary': 'rosemary', 'rosemary oil': 'rosemary',
    'onion oil': 'onion_oil', 'onion': 'onion_oil', 'pyaz': 'onion_oil',
    'sesame oil': 'sesame_oil_skin', 'til oil': 'sesame_oil_skin',
    'squalane': 'squalane', 'squalene': 'squalane',
    # Ceramides & Barrier
    'ceramide': 'ceramides', 'ceramides': 'ceramides',
    # Other Actives
    'snail mucin': 'snail_mucin', 'snail': 'snail_mucin',
    'panthenol': 'panthenol', 'vitamin b5': 'panthenol', 'dexpanthenol': 'panthenol',
    'biotin': 'biotin', 'vitamin b7': 'biotin',
    'redensyl': 'redensyl',
    'rice water': 'rice_water', 'fermented rice': 'rice_water',
    'coenzyme q10': 'coenzyme_q10', 'coq10': 'coenzyme_q10',
    'zinc pca': 'zinc_pca', 'zinc': 'zinc_pca',
    'benzoyl peroxide': 'benzoyl_peroxide', 'bp': 'benzoyl_peroxide',
    'sulfur': 'sulfur', 'sulphur': 'sulfur',
    'oat': 'oat_extract', 'oatmeal': 'oat_extract',
    # Sun Protection
    'spf': 'spf', 'sunscreen': 'spf', 'sun protection': 'spf', 'uv protection': 'spf',
    # Anti-Dandruff
    'ketoconazole': 'ketoconazole', 'keto shampoo': 'ketoconazole',
    'zinc pyrithione': 'zinc_pyrithione', 'zpt': 'zinc_pyrithione',
}

BENEFIT_KEYWORD_MAP = {
    # Skin Brightening & Pigmentation
    'brightening': 'brightening', 'brighten': 'brightening', 'bright': 'brightening',
    'skin brightening': 'brightening', 'luminous': 'brightening', 'luminosity': 'brightening',
    'even skin tone': 'brightening', 'even out': 'brightening', 'dull skin': 'brightening',
    'radiance': 'glow_radiance', 'glow': 'glow_radiance', 'glowing': 'glow_radiance',
    'glass skin': 'glow_radiance', 'radiant': 'glow_radiance', 'dewy': 'glow_radiance',
    'pigmentation': 'pigmentation', 'dark spots': 'pigmentation', 'dark spot': 'pigmentation',
    'hyperpigmentation': 'pigmentation', 'melasma': 'pigmentation', 'spots': 'pigmentation',
    'uneven skin tone': 'pigmentation', 'discoloration': 'pigmentation',
    # Anti-Aging
    'anti aging': 'anti_aging', 'anti-aging': 'anti_aging', 'antiaging': 'anti_aging',
    'wrinkle': 'anti_aging', 'wrinkles': 'anti_aging', 'fine lines': 'anti_aging',
    'aging': 'anti_aging', 'age': 'anti_aging', 'youthful': 'anti_aging',
    'firmness': 'anti_aging', 'firm': 'anti_aging',
    # Acne
    'acne': 'acne', 'pimple': 'acne', 'pimples': 'acne', 'blemish': 'acne',
    'breakout': 'acne', 'breakouts': 'acne', 'zit': 'acne',
    'blackheads': 'acne', 'whiteheads': 'acne',
    # Hydration
    'hydration': 'hydration', 'hydrating': 'hydration', 'moisturizing': 'hydration',
    'moisture': 'hydration', 'hydrate': 'hydration', 'plumping': 'hydration',
    # Dark Circles
    'dark circles': 'dark_circles', 'under eye': 'dark_circles', 'undereye': 'dark_circles',
    # Barrier Repair
    'barrier repair': 'barrier_repair', 'barrier': 'barrier_repair', 'skin barrier': 'barrier_repair',
    # Exfoliation
    'exfoliation': 'exfoliation', 'exfoliating': 'exfoliation', 'exfoliate': 'exfoliation',
    'dead skin': 'exfoliation', 'resurfacing': 'exfoliation',
    # Skin Types
    'oily skin': 'oily_skin', 'oil control': 'oily_skin', 'oil free': 'oily_skin',
    'sebum control': 'oily_skin', 'mattifying': 'oily_skin',
    'dry skin': 'dry_skin', 'dryness': 'dry_skin', 'very dry': 'dry_skin',
    'sensitive skin': 'sensitive_skin', 'sensitive': 'sensitive_skin', 'redness': 'sensitive_skin',
    'irritation': 'sensitive_skin', 'soothing': 'sensitive_skin', 'calming': 'sensitive_skin',
    'eczema': 'sensitive_skin', 'dermatitis': 'sensitive_skin', 'rosacea': 'sensitive_skin',
    # Pores
    'pore minimizing': 'pore_minimizing', 'pore': 'pore_minimizing', 'pores': 'pore_minimizing',
    'open pores': 'pore_minimizing', 'large pores': 'pore_minimizing',
    # Hair Benefits
    'hair growth': 'hair_growth', 'hair regrowth': 'hair_growth', 'grow hair': 'hair_growth',
    'hair loss': 'hair_fall', 'hair fall': 'hair_fall', 'hairfall': 'hair_fall',
    'hair thinning': 'hair_fall', 'balding': 'hair_fall',
    'dandruff': 'dandruff', 'anti dandruff': 'dandruff', 'anti-dandruff': 'dandruff',
    'scalp health': 'scalp_health', 'scalp care': 'scalp_health', 'scalp': 'scalp_health',
    'damage repair': 'damage_repair', 'damaged hair': 'damage_repair',
    'frizz': 'frizz_control', 'frizzy': 'frizz_control', 'frizz control': 'frizz_control',
    'curly hair': 'curly_hair', 'curl': 'curly_hair', 'curls': 'curly_hair',
    # Natural / Ayurvedic
    'natural skincare': 'natural_skincare', 'all natural': 'natural_skincare',
    'ayurvedic skincare': 'ayurvedic_skincare', 'ayurvedic skin': 'ayurvedic_skincare',
    'ayurvedic': 'ayurvedic_skincare', 'ayurveda': 'ayurvedic_skincare',
    'wedding': 'wedding_beauty', 'bridal': 'wedding_beauty', 'wedding glow': 'wedding_beauty',
}

PRODUCT_FORMAT_KEYWORD_MAP = {
    'serum': 'serum', 'face serum': 'serum', 'treatment serum': 'serum',
    'cream': 'cream', 'face cream': 'cream', 'night cream': 'cream',
    'moisturizer': 'moisturizer', 'moisturiser': 'moisturizer', 'lotion': 'moisturizer',
    'face wash': 'face_wash', 'facewash': 'face_wash', 'cleanser': 'face_wash',
    'toner': 'toner', 'tonic': 'toner',
    'mask': 'mask', 'face mask': 'mask', 'face pack': 'mask',
    'shampoo': 'shampoo', 'hair shampoo': 'shampoo',
    'conditioner': 'conditioner', 'hair conditioner': 'conditioner',
    'hair mask': 'hair_mask', 'hair pack': 'hair_mask',
    'hair oil': 'hair_oil', 'oil for hair': 'hair_oil',
    'face oil': 'oil', 'facial oil': 'oil',
    'sunscreen': 'sunscreen',
    'scrub': 'scrub', 'exfoliator': 'scrub',
    'eye cream': 'eye_cream', 'under eye cream': 'eye_cream',
    'gel': 'gel', 'face gel': 'gel',
}

CATEGORY_KEYWORD_MAP = {
    'skin': 'skincare', 'face': 'skincare', 'facial': 'skincare',
    'serum': 'skincare', 'moisturizer': 'skincare', 'cream': 'skincare',
    'sunscreen': 'skincare', 'toner': 'skincare', 'cleanser': 'skincare',
    'face wash': 'skincare', 'brightening': 'skincare', 'anti aging': 'skincare',
    'acne': 'skincare', 'pigmentation': 'skincare',
    'hair': 'haircare', 'shampoo': 'haircare', 'conditioner': 'haircare',
    'hair oil': 'haircare', 'hair mask': 'haircare', 'scalp': 'haircare',
    'dandruff': 'haircare', 'hair growth': 'haircare', 'hair fall': 'haircare',
}

BRAND_KEYWORD_MAP = {
    'cerave': 'cerave', 'cera ve': 'cerave',
    'cetaphil': 'cetaphil',
    'minimalist': 'minimalist', 'be minimalist': 'minimalist',
    'the ordinary': 'the_ordinary', 'ordinary': 'the_ordinary',
    'dot and key': 'dot_and_key', 'dot & key': 'dot_and_key',
    'mamaearth': 'mamaearth', 'mama earth': 'mamaearth',
    'plum': 'plum', 'plum goodness': 'plum',
    'loreal': 'loreal', "l'oreal": 'loreal',
    'garnier': 'garnier',
    'olay': 'olay',
    'neutrogena': 'neutrogena',
    'forest essentials': 'forest_essentials',
    'kama ayurveda': 'kama_ayurveda', 'kama': 'kama_ayurveda',
    'biotique': 'biotique',
    'himalaya': 'himalaya',
    'lakme': 'lakme', 'lakmé': 'lakme',
    'wow': 'wow', 'wow skin science': 'wow',
    'mcaffeine': 'mcaffeine',
    'simple': 'simple',
    'fixderma': 'fixderma',
    'deconstruct': 'deconstruct',
    'earth rhythm': 'earth_rhythm',
    'juicy chemistry': 'juicy_chemistry',
    'just herbs': 'just_herbs',
    'conscious chemist': 'conscious_chemist',
    'foxtale': 'foxtale',
    'bare anatomy': 'bare_anatomy',
    'indulekha': 'indulekha',
    'dabur': 'dabur',
    'head and shoulders': 'head_shoulders', 'head & shoulders': 'head_shoulders',
    'dove': 'dove_hair', 'dove hair': 'dove_hair',
    'tresemme': 'tresemme',
    'sebamed': 'sebamed',
    'la roche posay': 'la_roche_posay', 'la roche-posay': 'la_roche_posay',
    'derma co': 'the_derma_co', 'the derma co': 'the_derma_co',
    'nivea': 'nivea',
    'ponds': 'pond_s', "pond's": 'pond_s',
    'patanjali': 'patanjali',
    'matrix': 'matrix',
    'khadi': 'khadi_natural',
    'skinceuticals': 'skinceuticals',
    'tribe concepts': 'tribe_concepts',
    'vilvah': 'vilvah',
    'reequil': 'reequil', 're equil': 'reequil',
    'suganda': 'suganda',
}

# Benefit associations for cross-matching
BENEFIT_ASSOCIATIONS = {
    'brightening': ['pigmentation', 'skin_whitening', 'tan_removal', 'glow_radiance'],
    'pigmentation': ['brightening', 'skin_whitening', 'tan_removal'],
    'glow_radiance': ['brightening', 'hydration'],
    'anti_aging': ['barrier_repair', 'hydration', 'exfoliation'],
    'acne': ['oily_skin', 'pore_minimizing', 'exfoliation'],
    'oily_skin': ['acne', 'pore_minimizing'],
    'hydration': ['dry_skin', 'barrier_repair'],
    'dry_skin': ['hydration', 'barrier_repair'],
    'barrier_repair': ['sensitive_skin', 'hydration', 'dry_skin'],
    'sensitive_skin': ['barrier_repair', 'hydration'],
    'exfoliation': ['acne', 'pigmentation', 'brightening'],
    'pore_minimizing': ['acne', 'oily_skin'],
    'hair_growth': ['hair_fall', 'scalp_health'],
    'hair_fall': ['hair_growth', 'scalp_health'],
    'dandruff': ['scalp_health'],
    'scalp_health': ['dandruff', 'hair_growth'],
}

# Ingredient to benefit mapping
INGREDIENT_BENEFIT_MAP = {
    'vitamin_c': ['brightening', 'pigmentation', 'anti_aging', 'glow_radiance'],
    'niacinamide': ['brightening', 'oily_skin', 'pore_minimizing', 'acne', 'pigmentation', 'barrier_repair'],
    'retinol': ['anti_aging', 'acne', 'pigmentation', 'exfoliation'],
    'hyaluronic_acid': ['hydration', 'dry_skin', 'anti_aging'],
    'salicylic_acid': ['acne', 'oily_skin', 'pore_minimizing', 'exfoliation'],
    'salicylic_acid_hair': ['dandruff', 'scalp_health'],
    'glycolic_acid': ['exfoliation', 'brightening', 'anti_aging', 'pigmentation'],
    'alpha_arbutin': ['brightening', 'pigmentation', 'skin_whitening'],
    'tranexamic_acid': ['pigmentation', 'brightening'],
    'ceramides': ['barrier_repair', 'dry_skin', 'sensitive_skin', 'hydration'],
    'centella_asiatica': ['sensitive_skin', 'barrier_repair', 'acne'],
    'peptides': ['anti_aging', 'hair_growth'],
    'biotin': ['hair_growth', 'hair_fall'],
    'ketoconazole': ['dandruff', 'scalp_health'],
    'zinc_pyrithione': ['dandruff', 'scalp_health'],
    'tea_tree': ['acne', 'dandruff', 'scalp_health'],
    'bakuchiol': ['anti_aging', 'brightening'],
    'snail_mucin': ['hydration', 'barrier_repair', 'anti_aging'],
    'aloe_vera': ['sensitive_skin', 'hydration'],
    'saffron': ['brightening', 'glow_radiance'],
    'turmeric': ['brightening', 'acne'],
    'spf': ['anti_aging', 'pigmentation', 'tan_removal'],
    'zinc_pca': ['acne', 'oily_skin'],
    'panthenol': ['barrier_repair', 'hydration', 'sensitive_skin'],
    'onion_oil': ['hair_growth', 'hair_fall'],
    'rosemary': ['hair_growth', 'scalp_health'],
    'bhringraj': ['hair_growth', 'hair_fall'],
    'amla_hair': ['hair_growth', 'hair_fall'],
}


def extract_wish_keywords(wish_text: Optional[str], parsed_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Extract keywords from wish text or parsed data.
    Returns dict with category, productFormats, ingredients, benefits, brands.
    """
    result = {
        'category': None,
        'productFormats': [],
        'ingredients': [],
        'benefits': [],
        'brands': [],
    }
    
    # If parsed_data is available, use it directly
    if parsed_data:
        result['category'] = parsed_data.get('category', '').lower() if parsed_data.get('category') else None
        
        # Extract ingredients
        detected_ingredients = parsed_data.get('detected_ingredients', [])
        if detected_ingredients:
            result['ingredients'] = [
                ing.get('name', str(ing)).lower().replace(' ', '_') if isinstance(ing, dict) else str(ing).lower().replace(' ', '_')
                for ing in detected_ingredients
            ]
        
        # Extract benefits
        detected_benefits = parsed_data.get('detected_benefits', [])
        if detected_benefits:
            result['benefits'] = [b.lower().replace(' ', '_') for b in detected_benefits]
        
        # Extract product format
        product_type_obj = parsed_data.get('product_type', {})
        if product_type_obj:
            product_type = product_type_obj.get('id') or product_type_obj.get('name') if isinstance(product_type_obj, dict) else str(product_type_obj)
            if product_type:
                result['productFormats'] = [str(product_type).lower().replace(' ', '_')]
        
        product_format = parsed_data.get('product_format')
        if product_format:
            result['productFormats'].append(str(product_format).lower().replace(' ', '_'))
        
        return result
    
    # Otherwise, extract from wish text
    if not wish_text:
        return result
    
    text = wish_text.lower().replace("'", "'").replace('"', '"').replace(',', ' ').replace(';', ' ')
    text = re.sub(r'\s+', ' ', text).strip()
    
    def match_from_map(keyword_map: Dict[str, str]) -> List[str]:
        matches = set()
        sorted_keys = sorted(keyword_map.keys(), key=len, reverse=True)
        for keyword in sorted_keys:
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, text, re.IGNORECASE):
                matches.add(keyword_map[keyword])
        return list(matches)
    
    result['ingredients'] = match_from_map(INGREDIENT_KEYWORD_MAP)
    result['benefits'] = match_from_map(BENEFIT_KEYWORD_MAP)
    result['productFormats'] = match_from_map(PRODUCT_FORMAT_KEYWORD_MAP)
    result['brands'] = match_from_map(BRAND_KEYWORD_MAP)
    
    # Category voting
    category_votes = {'skincare': 0, 'haircare': 0}
    category_matches = match_from_map(CATEGORY_KEYWORD_MAP)
    for cat in category_matches:
        category_votes[cat] = category_votes.get(cat, 0) + 3
    
    HAIRCARE_FORMATS = {'shampoo', 'conditioner', 'hair_oil', 'hair_mask', 'scalp_serum'}
    SKINCARE_FORMATS = {'serum', 'cream', 'moisturizer', 'face_wash', 'toner', 'mask', 'sunscreen', 'eye_cream', 'lip_care', 'mist', 'peel', 'scrub', 'gel', 'oil', 'soap', 'powder'}
    
    for fmt in result['productFormats']:
        if fmt in HAIRCARE_FORMATS:
            category_votes['haircare'] += 2
        if fmt in SKINCARE_FORMATS:
            category_votes['skincare'] += 2
    
    HAIRCARE_BENEFITS = {'hair_growth', 'hair_fall', 'dandruff', 'scalp_health', 'damage_repair', 'frizz_control', 'curly_hair', 'grey_hair', 'hair_color_care', 'natural_hair_wash', 'ayurvedic_haircare'}
    for ben in result['benefits']:
        if ben in HAIRCARE_BENEFITS:
            category_votes['haircare'] += 2
        else:
            category_votes['skincare'] += 1
    
    if category_votes['skincare'] > category_votes['haircare']:
        result['category'] = 'skincare'
    elif category_votes['haircare'] > category_votes['skincare']:
        result['category'] = 'haircare'
    
    return result


def score_record(record: Dict[str, Any], keywords: Dict[str, Any]) -> int:
    """Score a record based on relevance to keywords."""
    score = 0
    
    # Category match
    if keywords.get('category') and record.get('category'):
        if record['category'].lower() == keywords['category']:
            score += 3
        else:
            score -= 5
    
    # Exact matches
    if record.get('ingredient_tag') and record['ingredient_tag'] in keywords.get('ingredients', []):
        score += 10
    if record.get('benefit_tag') and record['benefit_tag'] in keywords.get('benefits', []):
        score += 8
    if record.get('product_format') and record['product_format'] in keywords.get('productFormats', []):
        score += 6
    if record.get('brand_tag') and record['brand_tag'] in keywords.get('brands', []):
        score += 12
    
    # Benefit associations
    for benefit in keywords.get('benefits', []):
        associated = BENEFIT_ASSOCIATIONS.get(benefit, [])
        if record.get('benefit_tag') and record['benefit_tag'] in associated:
            score += 4
    
    # Ingredient → Benefit cross-match
    for ingredient in keywords.get('ingredients', []):
        relevant_benefits = INGREDIENT_BENEFIT_MAP.get(ingredient, [])
        if record.get('benefit_tag') and record['benefit_tag'] in relevant_benefits:
            score += 4
    
    # Comparison group overlap
    if record.get('query_level') == 'comparison' and record.get('comparison_group'):
        group_text = record['comparison_group'].lower()
        for ingredient in keywords.get('ingredients', []):
            if ingredient.replace('_', '') in group_text:
                score += 5
        for benefit in keywords.get('benefits', []):
            if benefit.replace('_', '') in group_text:
                score += 5
    
    # Trending bonus
    current_score = record.get('current_score', 0)
    if current_score >= 70:
        score += 2
    if record.get('trend_direction') == 'rising':
        score += 1
    
    return score


def select_records(scored: List[Dict[str, Any]], keywords: Dict[str, Any], max_records: int) -> List[Dict[str, Any]]:
    """
    Tiered selection with deduplication.
    Returns selected records sorted by score.
    """
    # Step 1: Deduplicate by tag signature
    deduped = {}
    for item in scored:
        if item['score'] < 3:  # Minimum threshold
            continue
        
        r = item['record']
        sig = f"{r.get('query_level', '')}|{r.get('ingredient_tag', '')}|{r.get('benefit_tag', '')}|{r.get('product_format', '')}|{r.get('brand_tag', '')}"
        
        if sig not in deduped or item['score'] > deduped[sig]['score']:
            deduped[sig] = item
    
    deduped_list = sorted(deduped.values(), key=lambda x: x['score'], reverse=True)
    
    # Step 2: Classify into tiers
    primary = []
    associated = []
    comparisons = []
    
    for item in deduped_list:
        r = item['record']
        
        if r.get('query_level') == 'comparison':
            comparisons.append(item)
        elif (
            (r.get('ingredient_tag') and r['ingredient_tag'] in keywords.get('ingredients', [])) or
            (r.get('brand_tag') and r['brand_tag'] in keywords.get('brands', [])) or
            (r.get('benefit_tag') and r['benefit_tag'] in keywords.get('benefits', []))
        ):
            primary.append(item)
        else:
            associated.append(item)
    
    # Step 3: Allocate budget
    primary_budget = int(max_records * 0.60)
    associated_budget = int(max_records * 0.25)
    comparison_budget = max_records - primary_budget - associated_budget
    
    selected = (
        primary[:primary_budget] +
        associated[:associated_budget] +
        comparisons[:comparison_budget]
    )
    
    # If any tier underflows, give remaining budget to primary
    remaining = max_records - len(selected)
    if remaining > 0:
        already_selected = {s['record'].get('query_text') for s in selected}
        extras = [
            item for item in (primary + associated + comparisons)
            if item['record'].get('query_text') not in already_selected
        ][:remaining]
        selected.extend(extras)
    
    return sorted(selected, key=lambda x: x['score'], reverse=True)


def trim_record(record: Dict[str, Any], options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Deep field trimming to reduce token count.
    Returns trimmed record with compact keys.
    """
    if options is None:
        options = {}
    
    include_related_queries = options.get('includeRelatedQueries', True)
    include_shopping_data = options.get('includeShoppingData', True)
    max_rising_queries = options.get('maxRisingQueries', 3)
    max_top_queries = options.get('maxTopQueries', 3)
    
    trimmed = {
        'q': record.get('query_text', ''),
        'lvl': record.get('query_level', ''),
        'cat': record.get('category', ''),
    }
    
    # Preserve source tracking fields for restructuring
    if record.get('_source'):
        trimmed['_source'] = record['_source']
    if record.get('_ingredient_name'):
        trimmed['_ingredient_name'] = record['_ingredient_name']
    
    # Tags (only non-null)
    if record.get('ingredient_tag'):
        trimmed['ing'] = record['ingredient_tag']
    if record.get('product_format'):
        trimmed['fmt'] = record['product_format']
    if record.get('benefit_tag'):
        trimmed['ben'] = record['benefit_tag']
    if record.get('brand_tag'):
        trimmed['brand'] = record['brand_tag']
    if record.get('comparison_group'):
        trimmed['cmp_grp'] = record['comparison_group']
    
    # Trend metrics (compact keys, rounded values)
    trimmed['score'] = record.get('current_score', 0)
    trimmed['peak'] = record.get('peak_score', 0)
    trimmed['g3m'] = round(record.get('growth_pct_3m', 0) * 10) / 10 if record.get('growth_pct_3m') else 0
    trimmed['g6m'] = round(record.get('growth_pct_6m', 0) * 10) / 10 if record.get('growth_pct_6m') else 0
    trimmed['dir'] = record.get('trend_direction', '')
    
    if record.get('peak_month'):
        trimmed['peak_month'] = record['peak_month']
    
    # Seasonality (only if has data)
    if record.get('seasonality'):
        s = record['seasonality']
        has_data = (
            (s.get('peak_months') and len(s['peak_months']) > 0) or
            (s.get('low_months') and len(s['low_months']) > 0) or
            s.get('peak_reason_hint') or s.get('best_launch_window') or
            s.get('seasonal_swing_pct', 0) > 0
        )
        if has_data:
            trimmed['season'] = {}
            if s.get('peak_months') and len(s['peak_months']) > 0:
                trimmed['season']['peak'] = s['peak_months']
            if s.get('low_months') and len(s['low_months']) > 0:
                trimmed['season']['low'] = s['low_months']
            if s.get('best_launch_window'):
                trimmed['season']['launch'] = s['best_launch_window']
    
    # Rising query insights (deeply trimmed)
    if record.get('rising_query_insights'):
        rqi = record['rising_query_insights']
        insight = {}
        
        if rqi.get('emerging_brands') and len(rqi['emerging_brands']) > 0:
            insight['emerging'] = rqi['emerging_brands']
        if rqi.get('established_brands_in_top') and len(rqi['established_brands_in_top']) > 0:
            insight['established'] = rqi['established_brands_in_top']
        if rqi.get('market_saturation_signal'):
            insight['saturation'] = rqi['market_saturation_signal']
        
        if rqi.get('user_intent_signals'):
            uis = rqi['user_intent_signals']
            if uis.get('review_seeking') or uis.get('comparison_seeking') or uis.get('price_seeking'):
                intent = {}
                if uis.get('review_seeking'):
                    intent['reviews'] = True
                if uis.get('comparison_seeking'):
                    intent['comparing'] = True
                if uis.get('price_seeking'):
                    intent['price_sensitive'] = True
                insight['intent'] = intent
        
        if insight:
            trimmed['insights'] = insight
    
    # Competitive position (only if has real data)
    if record.get('competitive_position'):
        cp = record['competitive_position']
        if cp.get('rank_in_group') is not None:
            trimmed['comp'] = {
                'grp': cp.get('comparison_group', ''),
                'rank': cp.get('rank_in_group', 0),
                'total': cp.get('total_in_group', 0),
                'vs_avg': cp.get('vs_group_average', 0),
            }
            if cp.get('nearest_competitor'):
                trimmed['comp']['rival'] = cp['nearest_competitor']
                trimmed['comp']['rival_score'] = cp.get('nearest_competitor_score', 0)
    
    # Related queries
    if include_related_queries:
        rising = (record.get('related_queries_rising') or [])[:max_rising_queries]
        if rising:
            trimmed['rising'] = [f"{q.get('query', '')} ({q.get('growth', '')})" if isinstance(q, dict) else str(q) for q in rising]
        
        top = (record.get('related_queries_top') or [])[:max_top_queries]
        if top:
            trimmed['top_q'] = [q.get('query', '') if isinstance(q, dict) else str(q) for q in top]
    
    # Shopping data
    if include_shopping_data and record.get('shopping_data'):
        sd = record['shopping_data']
        if sd.get('price_range'):
            trimmed['pricing'] = {
                'min': sd['price_range'].get('min', 0),
                'max': sd['price_range'].get('max', 0),
                'median': sd['price_range'].get('median', 0),
            }
            if sd.get('top_products') and len(sd['top_products']) > 0:
                trimmed['pricing']['top'] = [
                    {
                        'name': p.get('title', ''),
                        'price': p.get('price', 0),
                        'src': p.get('source', ''),
                        'brand': p.get('brand', ''),
                    }
                    for p in sd['top_products'][:3]
                ]
    
    return trimmed


def flatten_matched_trends(matched_trends: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Flatten the structured matched_trends (L1-L5) into a flat list of records.
    """
    all_records = []
    
    # L1: Hero Ingredient Trends
    l1_trends = matched_trends.get('level_1_ingredient_trends', {}) or matched_trends.get('hero_ingredient_trends', {})
    for ing_name, ing_data in l1_trends.items():
        if isinstance(ing_data, dict):
            trend_data = ing_data.get('trend_data', {})
            if trend_data:
                record = dict(trend_data)
                record['_source'] = 'L1'
                record['_ingredient_name'] = ing_name
                all_records.append(record)
    
    # L2: Competitive Landscape
    l2_trends = matched_trends.get('level_2_competing_approaches', []) or matched_trends.get('competitive_landscape', [])
    for item in l2_trends:
        if isinstance(item, dict):
            record = dict(item)
            record['_source'] = 'L2'
            all_records.append(record)
    
    # L3: Brand Intelligence
    l3_trends = matched_trends.get('level_3_brand_trends', []) or matched_trends.get('brand_intelligence', [])
    for item in l3_trends:
        if isinstance(item, dict):
            record = dict(item)
            record['_source'] = 'L3'
            all_records.append(record)
    
    # L4: Head-to-Head Comparisons
    l4_trends = matched_trends.get('comparison_data', []) or matched_trends.get('head_to_head', [])
    for item in l4_trends:
        if isinstance(item, dict):
            record = dict(item)
            record['_source'] = 'L4'
            all_records.append(record)
    
    # L5: Derivative Trends
    l5_trends = matched_trends.get('derivative_trends', [])
    for item in l5_trends:
        if isinstance(item, dict):
            record = dict(item)
            record['_source'] = 'L5'
            all_records.append(record)
    
    return all_records


def filter_trends_for_prompt(
    matched_trends: Dict[str, Any],
    parsed_data: Optional[Dict[str, Any]] = None,
    wish_text: Optional[str] = None,
    max_records: int = 25,
    options: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Filter and trim trend records using advanced keyword-based filtering (v2.0).
    
    This replaces the old truncation logic with intelligent filtering that:
    1. Extracts keywords from wish text or parsed data
    2. Scores records based on relevance
    3. Uses tiered selection with deduplication
    4. Deeply trims fields to reduce token count
    
    Args:
        matched_trends: Structured trend data from MongoDB (L1-L5 format)
        parsed_data: Parsed wish data (preferred over wish_text)
        wish_text: Raw wish text (used if parsed_data not available)
        max_records: Maximum number of records to return (default: 25)
        options: Additional options for trimming
        
    Returns:
        Filtered and trimmed records in a flat list format
    """
    if options is None:
        options = {}
    
    # Step 1: Extract keywords
    keywords = extract_wish_keywords(wish_text, parsed_data)
    print(f"[TREND FILTER] Extracted keywords: category={keywords.get('category')}, "
          f"ingredients={len(keywords.get('ingredients', []))}, "
          f"benefits={len(keywords.get('benefits', []))}, "
          f"formats={len(keywords.get('productFormats', []))}")
    
    # Step 2: Flatten matched_trends to a list
    all_records = flatten_matched_trends(matched_trends)
    print(f"[TREND FILTER] Flattened {len(all_records)} records from structured format")
    
    # Step 3: Score all records
    scored = [
        {'record': record, 'score': score_record(record, keywords)}
        for record in all_records
    ]
    
    # Step 4: Tiered selection with deduplication
    selected = select_records(scored, keywords, max_records)
    print(f"[TREND FILTER] Selected {len(selected)} records after tiered selection")
    
    # Step 5: Deep field trimming
    trim_opts = {
        'includeRelatedQueries': options.get('includeRelatedQueries', True),
        'includeShoppingData': options.get('includeShoppingData', True),
        'maxRisingQueries': options.get('maxRisingQueries', 3),
        'maxTopQueries': options.get('maxTopQueries', 3),
    }
    trimmed_records = [trim_record(item['record'], trim_opts) for item in selected]
    
    # Token estimation
    output_chars = len(json.dumps(trimmed_records))
    estimated_tokens = output_chars // 4
    original_tokens = len(all_records) * 4687  # Average tokens per record
    reduction = ((1 - estimated_tokens / original_tokens) * 100) if original_tokens > 0 else 0
    
    print(f"[TREND FILTER] Token reduction: {reduction:.1f}% ({estimated_tokens} tokens from {original_tokens})")
    
    return {
        'records': trimmed_records,
        'meta': {
            'totalRecords': len(all_records),
            'filteredCount': len(trimmed_records),
            'extractedKeywords': keywords,
            'estimatedTokens': estimated_tokens,
            'tokenReduction': f"{reduction:.1f}%",
        }
    }


def truncate_trend_data_for_prompt(
    matched_trends: Dict[str, Any],
    parsed_data: Optional[Dict[str, Any]] = None,
    max_tokens: int = 180000  # Leave room for system prompt and safety margin
) -> Dict[str, Any]:
    """
    Filter trend data using advanced keyword-based filtering (v2.0).
    
    This function now uses the new filtering logic instead of simple truncation.
    It filters by relevance, deduplicates, and trims fields to reduce token count.
    
    Args:
        matched_trends: Full trend data from MongoDB
        parsed_data: Parsed wish data to filter by category and product_format
        max_tokens: Maximum tokens allowed (default: 180k to leave room for system prompt)
    
    Returns:
        Filtered and trimmed trend data optimized for prompt size
    """
    # Use the new filtering logic
    filtered_result = filter_trends_for_prompt(
        matched_trends=matched_trends,
        parsed_data=parsed_data,
        max_records=25,  # Default to 25 records as per v2.0
        options={
            'includeRelatedQueries': True,
            'includeShoppingData': True,
            'maxRisingQueries': 3,
            'maxTopQueries': 3,
        }
    )
    
    # Restructure filtered records back into L1-L5 format for compatibility with prompt builder
    trimmed_records = filtered_result['records']
    
    # Group records back by source level
    truncated = {
        'level_1_ingredient_trends': {},
        'level_2_competing_approaches': [],
        'level_3_brand_trends': [],
        'comparison_data': [],
        'derivative_trends': [],
    }
    
    # Track L1 ingredients
    l1_ingredients = {}
    
    for record in trimmed_records:
        # Extract original record data (we need to get the full record, not just trimmed)
        # Since we only have trimmed data, we'll reconstruct what we can
        source = record.get('_source', '')
        ingredient_name = record.get('_ingredient_name', '')
        
        if source == 'L1' and ingredient_name:
            # Reconstruct L1 structure
            if ingredient_name not in l1_ingredients:
                l1_ingredients[ingredient_name] = {
                    'query_text': record.get('q', ''),
                    'trend_data': record  # Use trimmed record as trend_data
                }
        elif source == 'L2':
            truncated['level_2_competing_approaches'].append(record)
        elif source == 'L3':
            truncated['level_3_brand_trends'].append(record)
        elif source == 'L4':
            truncated['comparison_data'].append(record)
        elif source == 'L5':
            truncated['derivative_trends'].append(record)
    
    truncated['level_1_ingredient_trends'] = l1_ingredients
    
    # Keep shopping data and insights if present
    if matched_trends.get('shopping_data'):
        truncated['shopping_data'] = matched_trends['shopping_data']
    if matched_trends.get('insights'):
        truncated['insights'] = matched_trends['insights']
    
    print(f"[TREND FILTER] Restructured: L1={len(l1_ingredients)}, L2={len(truncated['level_2_competing_approaches'])}, "
          f"L3={len(truncated['level_3_brand_trends'])}, L4={len(truncated['comparison_data'])}, "
          f"L5={len(truncated['derivative_trends'])}")
    
    return truncated


def estimate_tokens_approximate(text: str) -> int:
    """
    Rough token estimation (Anthropic uses ~4 chars per token on average).
    This is a quick check before calling the actual API.
    """
    return len(text) // 4


# ============================================================================
# FALLBACK FUNCTIONS
# ============================================================================

def create_minimal_valid_response(
    parsed_data: Optional[Dict[str, Any]] = None,
    error_message: Optional[str] = None,
    error_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a minimal valid response structure when all else fails.
    This ensures the frontend always receives a valid response structure.
    """
    category = "skincare"
    product_type = "product"
    if parsed_data:
        category = parsed_data.get("category", "skincare")
        product_type_obj = parsed_data.get("product_type", {})
        product_type = product_type_obj.get("id") or product_type_obj.get("name") if isinstance(product_type_obj, dict) else str(product_type_obj) if product_type_obj else "product"
    
    summary_msg = f"Market intelligence analysis for {category} {product_type}."
    if error_message:
        summary_msg = f"Market analysis encountered an error: {error_message}. Please try again or contact support."
    
    metadata = {
        "status": "fallback",
        "message": "Using fallback response due to processing limitations"
    }
    if error_message:
        metadata["error"] = error_message
    if error_type:
        metadata["error_type"] = error_type
    
    return {
        "executive_summary": {
            "opportunity_score": 50,
            "tier": "Monitor",
            "confidence": "Low",
            "trend_direction": "Stable",
            "key_insights": [
                "Market trend analysis is being processed",
                "Data synthesis in progress"
            ],
            "summary": summary_msg,
            "recommendation": "Review available market data for this product category."
        },
        "related_keywords": [],
        "hero_ingredient_analysis": [],
        "competitive_landscape": [],
        "opportunity_breakdown": {
            "demand_score": 10,
            "competition_score": 10,
            "timing_score": 10,
            "feasibility_score": 10,
            "margin_score": 10
        },
        "regional_intelligence": {},
        "metadata": metadata
    }


def create_fallback_executive_summary(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a fallback executive_summary when Claude doesn't return one.
    Extracts information from available fields to create a minimal valid summary.
    """
    # Try to extract opportunity score from various places
    opportunity_score = 50  # Default neutral score
    tier = "Monitor"
    confidence = "Low"
    trend_direction = "Stable"
    key_insights = []
    
    # Try to get opportunity score from opportunity_breakdown
    opp_breakdown = data.get('opportunity_breakdown', {})
    if opp_breakdown:
        demand = opp_breakdown.get('demand_score', 0)
        competition = opp_breakdown.get('competition_score', 0)
        timing = opp_breakdown.get('timing_score', 0)
        feasibility = opp_breakdown.get('feasibility_score', 0)
        margin = opp_breakdown.get('margin_score', 0)
        opportunity_score = demand + competition + timing + feasibility + margin
    
    # Try to get from hero_ingredient_analysis
    hero_analysis = data.get('hero_ingredient_analysis', {})
    if hero_analysis and isinstance(hero_analysis, list) and len(hero_analysis) > 0:
        first_ingredient = hero_analysis[0]
        if isinstance(first_ingredient, dict):
            synthesis = first_ingredient.get('synthesis', {})
            if synthesis:
                opportunity_score = synthesis.get('opportunity_score', opportunity_score)
                trend_direction = synthesis.get('trend_direction', trend_direction)
                confidence = synthesis.get('confidence', confidence)
    
    # Determine tier based on score
    if opportunity_score >= 80:
        tier = "Pursue"
    elif opportunity_score >= 60:
        tier = "Consider"
    elif opportunity_score >= 40:
        tier = "Monitor"
    elif opportunity_score >= 20:
        tier = "Caution"
    else:
        tier = "Avoid"
    
    # Extract key insights from available data
    if 'key_insights' in data and isinstance(data['key_insights'], list):
        key_insights = data['key_insights'][:3]  # Top 3
    elif 'insights_breakdown' in data:
        insights = data['insights_breakdown']
        if isinstance(insights, dict):
            key_insights = [
                insights.get('market_opportunity', 'Market data available'),
                insights.get('competitive_landscape', 'Competitive analysis available'),
                insights.get('recommendations', 'Recommendations available')
            ]
    
    if not key_insights:
        key_insights = ["Market trend analysis completed", "Data synthesized from available sources"]
    
    return {
        "opportunity_score": opportunity_score,
        "tier": tier,
        "confidence": confidence,
        "trend_direction": trend_direction,
        "key_insights": key_insights,
        "summary": f"Market intelligence analysis completed. Opportunity score: {opportunity_score}/100 ({tier}). Confidence: {confidence}.",
        "recommendation": f"Based on available data, this opportunity is classified as '{tier}' with {confidence.lower()} confidence."
    }


# ============================================================================
# VALIDATION FUNCTIONS
# ============================================================================

def validate_trend_synthesis(data: Dict[str, Any]) -> bool:
    """
    Validate the synthesized trend data structure.
    
    Supports both old format (related_keyword_trends, trend_by_ingredient) 
    and new format (related_keywords, hero_ingredient_analysis, executive_summary).
    
    This function never raises exceptions - it fixes issues and logs warnings.
    
    Args:
        data: The synthesized JSON response
    
    Returns:
        True if valid (or fixed), never raises exceptions
    """
    # Wrap entire validation in try-catch to never raise exceptions
    try:
        # Check for comprehensive format (report_metadata, opportunity_assessment, etc.)
        has_comprehensive_format = any(key in data for key in [
            'report_metadata', 'opportunity_assessment', 'trend_classification',
            'competitive_landscape', 'regional_insights', 'seasonality_analysis',
            'ingredient_deep_dives', 'risk_assessment', 'recommendations',
            'synthesis_data'
        ])
        
        # Check for new format (based on system prompt)
        has_new_format = any(key in data for key in [
            'executive_summary', 'hero_ingredient_analysis', 'related_keywords',
            'opportunity_breakdown', 'regional_intelligence'
        ])
        
        # Check for old format
        has_old_format = any(key in data for key in [
            'related_keyword_trends', 'trend_by_ingredient', 'insights_breakdown'
        ])
    except Exception as e:
        print(f"[TREND SYNTHESIS] ⚠️ Error checking format: {e}. Assuming comprehensive format.")
        has_comprehensive_format = True
        has_new_format = False
        has_old_format = False
    
    try:
        # If comprehensive format is detected, accept it as-is (it's the expected format)
        if has_comprehensive_format:
            print(f"[TREND SYNTHESIS] ✅ Comprehensive format detected (report_metadata, opportunity_assessment, etc.)")
            # Just validate/fix numeric scores if needed, but don't restructure
            # Check for executive_summary and fix scores if present
            if 'executive_summary' in data:
                exec_summary = data.get('executive_summary', {})
                if exec_summary and isinstance(exec_summary, dict):
                    opp_score = exec_summary.get('opportunity_score', 0)
                    if isinstance(opp_score, dict):
                        numeric_value = opp_score.get('value') or opp_score.get('score') or opp_score.get('opportunity_score')
                        if numeric_value is None:
                            numeric_value = next((v for v in opp_score.values() if isinstance(v, (int, float))), 0)
                        exec_summary['opportunity_score'] = numeric_value if isinstance(numeric_value, (int, float)) else 0
                    elif not isinstance(opp_score, (int, float)):
                        exec_summary['opportunity_score'] = 0
            
            # Check opportunity_assessment for dict scores
            if 'opportunity_assessment' in data:
                opp_assessment = data.get('opportunity_assessment', {})
                if opp_assessment and isinstance(opp_assessment, dict):
                    overall_score = opp_assessment.get('overall_score')
                    if isinstance(overall_score, dict):
                        numeric_value = overall_score.get('value') or overall_score.get('score') or overall_score.get('overall_score')
                        if numeric_value is None:
                            numeric_value = next((v for v in overall_score.values() if isinstance(v, (int, float))), 0)
                        opp_assessment['overall_score'] = numeric_value if isinstance(numeric_value, (int, float)) else 0
                    
                    # Fix sub_scores if they're dicts
                    sub_scores = opp_assessment.get('sub_scores', {})
                    if sub_scores and isinstance(sub_scores, dict):
                        for score_name, score_data in sub_scores.items():
                            if isinstance(score_data, dict):
                                score_value = score_data.get('score') or score_data.get('value')
                                if score_value is None:
                                    score_value = next((v for v in score_data.values() if isinstance(v, (int, float))), 0)
                                sub_scores[score_name] = {'score': score_value if isinstance(score_value, (int, float)) else 0, **{k: v for k, v in score_data.items() if k != 'score' and k != 'value'}}
            
            return True  # Accept comprehensive format as-is
        
        if not has_new_format and not has_old_format:
            # Log what we actually got
            present_fields = [key for key in data.keys() if not key.startswith('_')]
            print(f"[TREND SYNTHESIS] ⚠️ Neither comprehensive, new nor old format detected. Present fields: {', '.join(present_fields)}")
            print(f"[TREND SYNTHESIS] 🔧 Creating minimal valid response structure...")
            
            # Create a minimal valid response with executive_summary
            data['executive_summary'] = create_fallback_executive_summary(data)
            data['related_keywords'] = data.get('related_keywords', [])
            data['hero_ingredient_analysis'] = data.get('hero_ingredient_analysis', [])
            data['competitive_landscape'] = data.get('competitive_landscape', [])
            
            # Mark as new format now
            has_new_format = True
        
        if has_new_format:
            # Validate new format structure (more lenient - only require executive_summary)
            # Other fields may be missing if response was truncated
            if 'executive_summary' not in data:
                # Log what fields are present for debugging
                present_fields = [key for key in data.keys() if not key.startswith('_')]
                print(f"[TREND SYNTHESIS] ⚠️ Missing executive_summary. Present fields: {', '.join(present_fields)}")
                
                # Create a fallback executive_summary from available data
                print(f"[TREND SYNTHESIS] 🔧 Creating fallback executive_summary...")
                data['executive_summary'] = create_fallback_executive_summary(data)
            
            # Log what fields are present for debugging
            present_fields = [key for key in data.keys() if not key.startswith('_')]
            print(f"[TREND SYNTHESIS] ✅ New format detected. Present fields: {', '.join(present_fields)}")
            
            # Warn about missing optional fields but don't fail
            optional_fields = {
                'hero_ingredient_analysis': 'hero_ingredient_analysis',
                'competitive_landscape': 'competitive_landscape',
                'related_keywords': 'related_keywords',
                'related_keyword_trends': 'related_keywords',  # Alternative name
                'opportunity_breakdown': 'opportunity_breakdown',
                'regional_intelligence': 'regional_intelligence'
            }
            
            missing_fields = []
            for field, display_name in optional_fields.items():
                if field not in data:
                    # Check for alternative names
                    if field == 'related_keywords' and 'related_keyword_trends' in data:
                        continue
                    missing_fields.append(display_name)
            
            if missing_fields:
                print(f"[TREND SYNTHESIS] ⚠️ Missing optional fields (response may be truncated): {', '.join(missing_fields)}")
            
            # Validate executive_summary structure
            exec_summary = data.get('executive_summary', {})
            if exec_summary:
                opp_score = exec_summary.get('opportunity_score', 0)
                
                # Handle case where opp_score might be a dict
                if isinstance(opp_score, dict):
                    numeric_value = opp_score.get('value') or opp_score.get('score') or opp_score.get('opportunity_score')
                    if numeric_value is None:
                        numeric_value = next((v for v in opp_score.values() if isinstance(v, (int, float))), 0)
                    opp_score = numeric_value if isinstance(numeric_value, (int, float)) else 0
                    print(f"[TREND SYNTHESIS] ⚠️ opportunity_score was a dict, extracted value: {opp_score}")
                
                # Ensure opp_score is numeric
                if not isinstance(opp_score, (int, float)):
                    print(f"[TREND SYNTHESIS] ⚠️ opportunity_score is not numeric ({type(opp_score).__name__}), defaulting to 50")
                    opp_score = 50
                
                if opp_score < 0 or opp_score > 100:
                    print(f"[TREND SYNTHESIS] ⚠️ Invalid opportunity score: {opp_score}. Clamping to valid range.")
                    # Clamp to valid range instead of raising error
                    exec_summary['opportunity_score'] = max(0, min(100, opp_score))
                    # Update tier based on corrected score
                    corrected_score = exec_summary['opportunity_score']
                    if corrected_score >= 80:
                        exec_summary['tier'] = "Pursue"
                    elif corrected_score >= 60:
                        exec_summary['tier'] = "Consider"
                    elif corrected_score >= 40:
                        exec_summary['tier'] = "Monitor"
                    elif corrected_score >= 20:
                        exec_summary['tier'] = "Caution"
                    else:
                        exec_summary['tier'] = "Avoid"
            
            # Validate opportunity_breakdown if present
            opp_breakdown = data.get('opportunity_breakdown', {})
            if opp_breakdown and isinstance(opp_breakdown, dict):
                # Validate and clamp sub-scores to valid ranges
                score_ranges = {
                    'demand_score': (0, 25),
                    'competition_score': (0, 25),
                    'timing_score': (0, 20),
                    'feasibility_score': (0, 15),
                    'margin_score': (0, 15)
                }
                
                for score_name, (min_val, max_val) in score_ranges.items():
                    score_value = opp_breakdown.get(score_name, 0)
                    
                    # Handle case where score_value might be a dict (e.g., {"value": 10, "reason": "..."})
                    if isinstance(score_value, dict):
                        # Try to extract numeric value from dict
                        numeric_value = score_value.get('value') or score_value.get('score') or score_value.get('score_value')
                        if numeric_value is None:
                            # If no numeric field found, use first numeric value in dict
                            numeric_value = next((v for v in score_value.values() if isinstance(v, (int, float))), 0)
                        score_value = numeric_value if isinstance(numeric_value, (int, float)) else 0
                        print(f"[TREND SYNTHESIS] ⚠️ {score_name} was a dict, extracted value: {score_value}")
                    
                    # Ensure score_value is numeric
                    if not isinstance(score_value, (int, float)):
                        print(f"[TREND SYNTHESIS] ⚠️ {score_name} is not numeric ({type(score_value).__name__}), defaulting to 0")
                        score_value = 0
                    
                    if score_value < min_val or score_value > max_val:
                        print(f"[TREND SYNTHESIS] ⚠️ {score_name} out of range ({score_value}). Clamping to [{min_val}, {max_val}].")
                        opp_breakdown[score_name] = max(min_val, min(max_val, score_value))
                    else:
                        # Ensure the value is stored as a number (not dict)
                        opp_breakdown[score_name] = score_value
        
        else:
            # Validate old format structure (more lenient - allow missing fields)
            print(f"[TREND SYNTHESIS] ✅ Old format detected")
            present_fields = [key for key in data.keys() if not key.startswith('_')]
            print(f"[TREND SYNTHESIS]   Present fields: {', '.join(present_fields)}")
            
            # Check for at least one key field to confirm old format
            old_format_fields = [
                'related_keyword_trends',
                'competitive_landscape',
                'trend_by_ingredient',
                'insights_breakdown'
            ]
            
            has_any_old_field = any(field in data for field in old_format_fields)
            if not has_any_old_field:
                # If no old format fields, try to create a minimal structure
                print(f"[TREND SYNTHESIS] ⚠️ No standard old format fields found, creating minimal structure...")
                if 'related_keyword_trends' not in data:
                    data['related_keyword_trends'] = []
                if 'competitive_landscape' not in data:
                    data['competitive_landscape'] = []
                if 'trend_by_ingredient' not in data:
                    data['trend_by_ingredient'] = []
                if 'insights_breakdown' not in data:
                    data['insights_breakdown'] = {
                        "market_opportunity": "Analysis completed",
                        "competitive_landscape": "Data available",
                        "recommendations": "Review available data"
                    }
            
            # Validate opportunity scores are within bounds
            for ingredient in data.get('trend_by_ingredient', []):
                synthesis = ingredient.get('synthesis', {})
                if synthesis:
                    opp_score = synthesis.get('opportunity_score', 0)
                    
                    # Handle case where opp_score might be a dict
                    if isinstance(opp_score, dict):
                        numeric_value = opp_score.get('value') or opp_score.get('score') or opp_score.get('opportunity_score')
                        if numeric_value is None:
                            numeric_value = next((v for v in opp_score.values() if isinstance(v, (int, float))), 0)
                        opp_score = numeric_value if isinstance(numeric_value, (int, float)) else 0
                        print(f"[TREND SYNTHESIS] ⚠️ opportunity_score was a dict, extracted value: {opp_score}")
                    
                    # Ensure opp_score is numeric
                    if not isinstance(opp_score, (int, float)):
                        print(f"[TREND SYNTHESIS] ⚠️ opportunity_score is not numeric ({type(opp_score).__name__}), defaulting to 50")
                        opp_score = 50
                    
                    if opp_score < 0 or opp_score > 100:
                        print(f"[TREND SYNTHESIS] ⚠️ Invalid opportunity score for ingredient: {opp_score}. Clamping to [0, 100].")
                        synthesis['opportunity_score'] = max(0, min(100, opp_score))
                    else:
                        # Ensure the value is stored as a number (not dict)
                        synthesis['opportunity_score'] = opp_score
                    
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
    
    except Exception as validation_err:
        # Catch any unexpected errors in validation and log them
        print(f"[TREND SYNTHESIS] ⚠️ Unexpected error during validation ({type(validation_err).__name__}): {validation_err}")
        import traceback
        traceback.print_exc()
        # Always return True - validation should never fail
        return True


# ============================================================================
# SYNC HELPERS (run in thread pool to avoid blocking the event loop)
# ============================================================================

def _stream_claude_sync(client: Any, api_params: Dict[str, Any]) -> Tuple[str, Optional[str], int]:
    """
    Synchronously call Claude streaming API and collect content.
    Must be run via asyncio.to_thread() so the event loop is not blocked.
    Returns (content, stop_reason, event_count).
    """
    content = ""
    stop_reason = None
    event_count = 0
    with client.messages.stream(**api_params) as stream:
        for event in stream:
            event_count += 1
            if event.type == "content_block_delta":
                try:
                    if hasattr(event, "delta"):
                        if hasattr(event.delta, "text"):
                            content += event.delta.text
                        elif hasattr(event.delta, "type") and event.delta.type == "text_delta":
                            if hasattr(event.delta, "text"):
                                content += event.delta.text
                except Exception:
                    pass
            elif event.type == "message_delta":
                try:
                    if hasattr(event, "delta") and hasattr(event.delta, "stop_reason"):
                        stop_reason = event.delta.stop_reason
                except Exception:
                    pass
            elif event.type == "message_stop":
                try:
                    if hasattr(event, "message") and hasattr(event.message, "stop_reason"):
                        stop_reason = event.message.stop_reason
                except Exception:
                    pass
    return (content, stop_reason, event_count)


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
    # Validate prerequisites - return fallback if not available
    if not claude_client:
        print(f"[TREND SYNTHESIS] ⚠️ Claude client not initialized. Returning fallback response.")
        return create_minimal_valid_response(parsed_data)
    
    if not CLAUDE_MODEL:
        print(f"[TREND SYNTHESIS] ⚠️ Claude model not configured. Returning fallback response.")
        return create_minimal_valid_response(parsed_data)
    
    print(f"[TREND SYNTHESIS] 🚀 Starting trend synthesis...")
    print(f"[TREND SYNTHESIS]   Parsed data keys: {list(parsed_data.keys())}")
    print(f"[TREND SYNTHESIS]   Matched trends keys: {list(matched_trends.keys())}")
    
    # Filter trend data using advanced keyword-based filtering (v2.0)
    print(f"[TREND SYNTHESIS] ✂️ Filtering trend data using advanced keyword-based filtering (v2.0)...")
    print(f"[TREND SYNTHESIS]   This reduces input from ~4.3M tokens to ~7K tokens (99.8% reduction)")
    try:
        truncated_trends = truncate_trend_data_for_prompt(matched_trends, parsed_data=parsed_data, max_tokens=180000)
        print(f"[TREND SYNTHESIS] ✅ Filtering complete - data optimized for prompt")
    except Exception as truncate_err:
        print(f"[TREND SYNTHESIS] ⚠️ Error during filtering: {truncate_err}. Using original data.")
        truncated_trends = matched_trends
    
    # Build prompts with truncated data
    system_prompt = TREND_SYNTHESIS_SYSTEM_PROMPT
    try:
        user_prompt = build_trend_synthesis_user_prompt(parsed_data, truncated_trends)
    except Exception as prompt_err:
        print(f"[TREND SYNTHESIS] ⚠️ Error building prompt: {prompt_err}. Returning fallback response.")
        return create_minimal_valid_response(parsed_data)
    
    print(f"[TREND SYNTHESIS]   System prompt length: {len(system_prompt)} chars")
    print(f"[TREND SYNTHESIS]   User prompt length: {len(user_prompt)} chars")
    
    # Format system prompt with cache_control if caching enabled (GA approach)
    formatted_system = system_prompt
    # Estimate tokens and check limit
    estimated_system_tokens = estimate_tokens_approximate(system_prompt)
    estimated_user_tokens = estimate_tokens_approximate(user_prompt)
    estimated_total = estimated_system_tokens + estimated_user_tokens
    
    print(f"[TREND SYNTHESIS]   Estimated tokens - System: ~{estimated_system_tokens}, User: ~{estimated_user_tokens}, Total: ~{estimated_total}")
    
    # Use actual token counting if available (run in thread to avoid blocking event loop)
    try:
        token_count = await asyncio.to_thread(
            claude_client.messages.count_tokens,
            model=CLAUDE_MODEL,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )
        actual_tokens = token_count.input_tokens
        print(f"[TREND SYNTHESIS]   Actual token count: {actual_tokens} tokens")
        
        if actual_tokens > 200000:
            print(f"[TREND SYNTHESIS] ⚠️ Prompt too long ({actual_tokens} tokens). Aggressively truncating data...")
            # Aggressively truncate data and retry
            truncated_trends = truncate_trend_data_for_prompt(matched_trends, parsed_data=parsed_data, max_tokens=150000)
            user_prompt = build_trend_synthesis_user_prompt(parsed_data, truncated_trends)
            
            # Re-count tokens (in thread)
            try:
                token_count = await asyncio.to_thread(
                    claude_client.messages.count_tokens,
                    model=CLAUDE_MODEL,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}]
                )
                actual_tokens = token_count.input_tokens
                print(f"[TREND SYNTHESIS]   After aggressive truncation: {actual_tokens} tokens")
                
                if actual_tokens > 200000:
                    print(f"[TREND SYNTHESIS] ⚠️ Still too long after truncation. Returning fallback response.")
                    return create_minimal_valid_response(parsed_data)
            except:
                # If re-counting fails, use estimation
                estimated_user_tokens = estimate_tokens_approximate(user_prompt)
                if estimated_user_tokens + estimated_system_tokens > 200000:
                    print(f"[TREND SYNTHESIS] ⚠️ Estimated tokens still too high. Returning fallback response.")
                    return create_minimal_valid_response(parsed_data)
        elif actual_tokens > 190000:
            print(f"[TREND SYNTHESIS] ⚠️ WARNING: Prompt is very close to limit ({actual_tokens}/200000 tokens)")
    except Exception as e:
        print(f"[TREND SYNTHESIS] ⚠️ Could not count tokens exactly: {e}")
        # Fall back to estimation
        if estimated_total > 200000:
            print(f"[TREND SYNTHESIS] ⚠️ Estimated prompt too long (~{estimated_total} tokens). Aggressively truncating...")
            truncated_trends = truncate_trend_data_for_prompt(matched_trends, parsed_data=parsed_data, max_tokens=150000)
            user_prompt = build_trend_synthesis_user_prompt(parsed_data, truncated_trends)
            estimated_user_tokens = estimate_tokens_approximate(user_prompt)
            if estimated_user_tokens + estimated_system_tokens > 200000:
                print(f"[TREND SYNTHESIS] ⚠️ Still too long after truncation. Returning fallback response.")
                return create_minimal_valid_response(parsed_data)
        actual_tokens = estimated_total
    
    # Get cache control if caching enabled
    cache_control = None
    if use_cache:
        try:
            from app.ai_ingredient_intelligence.logic.prompt_cache_manager import format_system_prompt_with_cache
            formatted_system = format_system_prompt_with_cache(
                system_prompt=system_prompt,
                prompt_type="trend_synthesis",
                claude_client=claude_client,
                ttl="1h"
            )
            if isinstance(formatted_system, list):
                print(f"[TREND SYNTHESIS] ✅ Using prompt caching (GA) - system prompt formatted as content blocks")
            else:
                print(f"[TREND SYNTHESIS] ⚠️ Caching disabled or failed - using plain system prompt")
        except Exception as e:
            print(f"[TREND SYNTHESIS] ⚠️ Could not format system prompt with cache: {e}")
            formatted_system = system_prompt
    
    # Prepare API call with properly formatted system prompt (content blocks with cache_control)
    # With new filtering (reducing input from ~4.3M to ~7K tokens), we can allocate much more to output
    # Use streaming to handle long requests (>10 minutes) as required by Anthropic API
    api_params = {
        "model": CLAUDE_MODEL,
        "max_tokens": 8000,  # Aggressively optimized: forces concise responses, faster generation (was 32000)
        "temperature": 0.0,  # Zero temperature for fastest, most deterministic generation
        "system": formatted_system,  # Can be string or list of content blocks
        "messages": [
                {"role": "user", "content": user_prompt}
            ]
    }
    
    try:
        # Call Claude API with streaming (required for requests that may take >10 minutes)
        print(f"[TREND SYNTHESIS] 📡 Calling Claude API with streaming (required for long requests)...")
        
        # Run Claude streaming in thread pool so the event loop is not blocked
        print(f"[TREND SYNTHESIS]   Starting to receive stream events (running in thread pool)...")
        try:
            content, stop_reason, event_count = await asyncio.to_thread(
                _stream_claude_sync, claude_client, api_params
            )
            print(f"[TREND SYNTHESIS]   ✅ Stream complete: {event_count} total events, {len(content)} chars received")
        except Exception as stream_init_err:
            print(f"[TREND SYNTHESIS] ❌ Error initializing or processing stream: {stream_init_err}")
            import traceback
            traceback.print_exc()
            return create_minimal_valid_response(
                parsed_data,
                error_message=f"Streaming error: {str(stream_init_err)}",
                error_type=type(stream_init_err).__name__
            )
        
        # Validate stream results
        if event_count == 0:
            print(f"[TREND SYNTHESIS] ⚠️ No events received from stream. This might indicate an error.")
            return create_minimal_valid_response(parsed_data, error_message="No events received from streaming API")
        
        content = content.strip()
        
        if not content:
            print(f"[TREND SYNTHESIS] ⚠️ Empty text in Claude streaming response after {event_count} events. Returning fallback response.")
            return create_minimal_valid_response(parsed_data, error_message="Streaming completed but no content received")
        
        # Check if response was truncated (Claude stops mid-sentence when hitting max_tokens)
        if stop_reason == "max_tokens":
            print(f"[TREND SYNTHESIS] ⚠️ WARNING: Response was truncated (hit max_tokens limit of 10000)")
            print(f"[TREND SYNTHESIS]   Response length: {len(content)} chars")
            print(f"[TREND SYNTHESIS]   This should be rare with new filtering. Consider increasing max_tokens further if this persists.")
        
        # Extract JSON from response (handle markdown code blocks if present)
        print(f"[TREND SYNTHESIS]   Content preview (first 200 chars): {content[:200]}")
        json_content = content
        if "```json" in content:
            json_content = content.split("```json")[1].split("```")[0].strip()
            print(f"[TREND SYNTHESIS]   Extracted JSON from ```json code block")
        elif "```" in content:
            json_content = content.split("```")[1].split("```")[0].strip()
            print(f"[TREND SYNTHESIS]   Extracted JSON from ``` code block")
        else:
            print(f"[TREND SYNTHESIS]   No code blocks found, using content as-is")
        
        # Check if JSON appears truncated (ends with incomplete string/object)
        # Look for unterminated strings (odd number of unescaped quotes)
        if json_content:
            # Count unescaped quotes to detect unterminated strings
            quote_count = 0
            escaped = False
            for char in json_content:
                if char == '\\' and not escaped:
                    escaped = True
                    continue
                if char == '"' and not escaped:
                    quote_count += 1
                escaped = False
            
            # If odd number of quotes, we likely have an unterminated string
            if quote_count % 2 != 0:
                print(f"[TREND SYNTHESIS] ⚠️ Detected unterminated string in JSON (odd quote count: {quote_count})")
                # Try to fix by finding the last unclosed quote and closing it, then closing any open objects/arrays
                last_quote_pos = json_content.rfind('"')
                if last_quote_pos > 0:
                    # Check if this quote is escaped
                    before_quote = json_content[:last_quote_pos]
                    escape_count = 0
                    for i in range(len(before_quote) - 1, -1, -1):
                        if before_quote[i] == '\\':
                            escape_count += 1
                        else:
                            break
                    
                    # If not escaped, close the string
                    if escape_count % 2 == 0:
                        # Find the last complete object/array before this point
                        # Close the string, then close any open structures
                        fixed_json = json_content[:last_quote_pos+1] + '"'
                        
                        # Count open braces and brackets to close them
                        open_braces = fixed_json.count('{') - fixed_json.count('}')
                        open_brackets = fixed_json.count('[') - fixed_json.count(']')
                        
                        # Close brackets first, then braces
                        fixed_json += ']' * open_brackets
                        fixed_json += '}' * open_braces
                        
                        json_content = fixed_json
                        print(f"[TREND SYNTHESIS]   Attempted to fix truncated JSON by closing string and structures")
        
        # Parse JSON with better error handling
        synthesized = None  # Initialize to ensure it's always defined
        try:
            synthesized = json.loads(json_content)
            print(f"[TREND SYNTHESIS] ✅ Successfully parsed JSON response")
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
            fixed = False
            try:
                # Try removing trailing commas
                json_content_fixed = json_content.replace(',\n}', '\n}').replace(',\n]', '\n]')
                synthesized = json.loads(json_content_fixed)
                print(f"[TREND SYNTHESIS] ✅ Fixed JSON by removing trailing commas")
                fixed = True
            except:
                pass
            
            if not fixed:
                # Try to extract JSON from a larger context
                try:
                    # Find the first { and last } to extract valid JSON
                    first_brace = json_content.find('{')
                    last_brace = json_content.rfind('}')
                    if first_brace >= 0 and last_brace > first_brace:
                        json_content_fixed = json_content[first_brace:last_brace+1]
                        synthesized = json.loads(json_content_fixed)
                        print(f"[TREND SYNTHESIS] ✅ Fixed JSON by extracting from braces")
                        fixed = True
                except Exception as fix_err:
                    print(f"[TREND SYNTHESIS] ❌ Could not fix JSON: {fix_err}")
            
            if not fixed:
                # Try to extract the largest valid JSON object from truncated response
                print(f"[TREND SYNTHESIS] ⚠️ Could not parse complete JSON. Attempting to extract maximum valid JSON...")
                
                # Strategy: Find the first { and try progressively shorter suffixes until we find valid JSON
                first_brace = json_content.find('{')
                if first_brace >= 0:
                    # Try to find the largest valid JSON by working backwards from the end
                    max_valid_json = None
                    for end_pos in range(len(json_content), first_brace, -1):
                        try:
                            test_json = json_content[first_brace:end_pos]
                            # Close any open structures
                            open_braces = test_json.count('{') - test_json.count('}')
                            open_brackets = test_json.count('[') - test_json.count(']')
                            
                            # Only try if we're reasonably close to balanced
                            if abs(open_braces) <= 5 and abs(open_brackets) <= 5:
                                # Try to balance it
                                balanced_json = test_json + ']' * open_brackets + '}' * open_braces
                                test_obj = json.loads(balanced_json)
                                max_valid_json = test_obj
                                print(f"[TREND SYNTHESIS] ✅ Extracted valid JSON from position {first_brace} to {end_pos} (truncated)")
                                break
                        except:
                            continue
                    
                    if max_valid_json:
                        synthesized = max_valid_json
                        # Mark as truncated
                        if isinstance(synthesized, dict):
                            if 'report_metadata' not in synthesized:
                                synthesized['report_metadata'] = {}
                            if not isinstance(synthesized['report_metadata'], dict):
                                synthesized['report_metadata'] = {}
                            synthesized['report_metadata']['_truncated'] = True
                            synthesized['report_metadata']['_truncation_note'] = "Response was truncated but maximum valid JSON extracted"
                        print(f"[TREND SYNTHESIS] ✅ Using extracted partial JSON with {len(synthesized)} top-level keys")
                    else:
                        # Save problematic response for debugging
                        try:
                            import os
                            debug_dir = "debug_responses"
                            os.makedirs(debug_dir, exist_ok=True)
                            debug_file = os.path.join(debug_dir, f"trend_synthesis_error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
                            with open(debug_file, 'w', encoding='utf-8') as f:
                                f.write(f"Error: {json_err}\n\n")
                                f.write(f"Full response:\n{content}\n\n")
                                f.write(f"Extracted JSON:\n{json_content}\n")
                            print(f"[TREND SYNTHESIS]   Saved problematic response to: {debug_file}")
                        except Exception as save_err:
                            print(f"[TREND SYNTHESIS]   Could not save debug file: {save_err}")
                        
                        # Last resort: create minimal fallback
                        synthesized = create_minimal_valid_response(parsed_data)
                        
                        # Try to extract any text insights from the response
                        if content and len(content) > 100:
                            synthesized["metadata"]["raw_response_preview"] = content[:500]  # First 500 chars
                            synthesized["executive_summary"]["summary"] = f"Analysis completed but response format was invalid. Raw response available in metadata."
                        
                        print(f"[TREND SYNTHESIS] ✅ Created fallback response with partial data")
                        return synthesized
                else:
                    # No opening brace found - complete failure
                    print(f"[TREND SYNTHESIS] ❌ No JSON structure found in response")
                    synthesized = create_minimal_valid_response(parsed_data)
                    if content and len(content) > 100:
                        synthesized["metadata"]["raw_response_preview"] = content[:500]
                        synthesized["executive_summary"]["summary"] = f"Analysis completed but response format was invalid. Raw response available in metadata."
                    return synthesized
        
        # Ensure synthesized is defined before proceeding
        if synthesized is None:
            print(f"[TREND SYNTHESIS] ❌ ERROR: synthesized is None after JSON parsing! This should never happen.")
            synthesized = create_minimal_valid_response(parsed_data, error_message="JSON parsing completed but synthesized is None")
            return synthesized
        
        # Log response structure for debugging
        response_keys = list(synthesized.keys())[:10]
        print(f"[TREND SYNTHESIS] 📋 Response keys: {', '.join(response_keys)}...")
        
        # Validate structure (lenient validation with fallback)
        # Catch ALL exceptions from validation (ValueError, TypeError, etc.)
        try:
            validate_trend_synthesis(synthesized)
        except Exception as validation_error:
            print(f"[TREND SYNTHESIS] ⚠️ Validation error ({type(validation_error).__name__}): {validation_error}")
            print(f"[TREND SYNTHESIS] 🔧 Attempting to fix response structure...")
            
            # Fix any dict scores that might be causing issues
            try:
                # Fix opportunity_breakdown scores
                opp_breakdown = synthesized.get('opportunity_breakdown', {})
                if opp_breakdown and isinstance(opp_breakdown, dict):
                    for score_name in ['demand_score', 'competition_score', 'timing_score', 'feasibility_score', 'margin_score']:
                        score_value = opp_breakdown.get(score_name)
                        if isinstance(score_value, dict):
                            numeric_value = score_value.get('value') or score_value.get('score') or score_value.get('score_value')
                            if numeric_value is None:
                                numeric_value = next((v for v in score_value.values() if isinstance(v, (int, float))), 0)
                            opp_breakdown[score_name] = numeric_value if isinstance(numeric_value, (int, float)) else 0
                        elif not isinstance(score_value, (int, float)):
                            opp_breakdown[score_name] = 0
                
                # Fix executive_summary opportunity_score
                exec_summary = synthesized.get('executive_summary', {})
                if exec_summary and isinstance(exec_summary, dict):
                    opp_score = exec_summary.get('opportunity_score')
                    if isinstance(opp_score, dict):
                        numeric_value = opp_score.get('value') or opp_score.get('score') or opp_score.get('opportunity_score')
                        if numeric_value is None:
                            numeric_value = next((v for v in opp_score.values() if isinstance(v, (int, float))), 50)
                        exec_summary['opportunity_score'] = numeric_value if isinstance(numeric_value, (int, float)) else 50
                    elif not isinstance(opp_score, (int, float)):
                        exec_summary['opportunity_score'] = 50
                
                print(f"[TREND SYNTHESIS] ✅ Fixed dict scores in response")
            except Exception as fix_err:
                print(f"[TREND SYNTHESIS] ⚠️ Error fixing scores: {fix_err}")
            
            # Re-validate (should pass now - validation never raises exceptions)
            validate_trend_synthesis(synthesized)
            print(f"[TREND SYNTHESIS] ✅ Validation passed after fix")
        
        print(f"[TREND SYNTHESIS] ✅ Synthesis complete!")
        
        # Validate that synthesized is not None
        if synthesized is None:
            print(f"[TREND SYNTHESIS] ❌ ERROR: synthesized is None! This should never happen.")
            return create_minimal_valid_response(parsed_data, error_message="Synthesis returned None unexpectedly")
        
        # Support both old and new formats
        ingredients_count = len(synthesized.get('trend_by_ingredient', [])) or (1 if synthesized.get('hero_ingredient_analysis') else 0)
        keywords_count = len(synthesized.get('related_keyword_trends', [])) or len(synthesized.get('related_keywords', []))
        brands_count = len(synthesized.get('competitive_landscape', [])) if isinstance(synthesized.get('competitive_landscape'), list) else (1 if synthesized.get('competitive_landscape') else 0)
        print(f"[TREND SYNTHESIS]   Ingredients analyzed: {ingredients_count}")
        print(f"[TREND SYNTHESIS]   Keywords: {keywords_count}")
        print(f"[TREND SYNTHESIS]   Brands: {brands_count}")
        
        print(f"[TREND SYNTHESIS]   Returning synthesized data with {len(synthesized)} top-level keys")
        return synthesized
        
    except Exception as e:
        print(f"[TREND SYNTHESIS] ❌ Error during synthesis: {e}")
        import traceback
        traceback.print_exc()
        
        # Always return a valid response, even on error
        print(f"[TREND SYNTHESIS] 🔧 Creating fallback response due to error...")
        fallback_response = create_minimal_valid_response(parsed_data)
        fallback_response["metadata"]["error"] = str(e)
        fallback_response["metadata"]["error_type"] = type(e).__name__
        fallback_response["executive_summary"]["summary"] = f"Market analysis encountered an error: {str(e)}. Please try again or contact support."
        print(f"[TREND SYNTHESIS] ✅ Returning fallback response")
        return fallback_response
