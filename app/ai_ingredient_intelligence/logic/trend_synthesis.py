"""
Trend Synthesis Engine - Claude AI Integration
==============================================

AI-powered synthesis of trend data into actionable insights and recommendations.
"""

import os
import json
from typing import Dict, Any, Optional

# Claude AI setup
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    anthropic = None

claude_api_key = os.getenv("CLAUDE_API_KEY")
claude_model = os.getenv("CLAUDE_MODEL") or os.getenv("MODEL_NAME") or "claude-sonnet-4-5-20250929"

if ANTHROPIC_AVAILABLE and claude_api_key:
    try:
        claude_client = anthropic.Anthropic(api_key=claude_api_key)
    except Exception as e:
        print(f"Warning: Could not initialize Claude client: {e}")
        claude_client = None
else:
    claude_client = None


TREND_SYNTHESIS_SYSTEM_PROMPT = """
You are a market intelligence analyst specializing in the Indian personal care and cosmetics market.
Your role is to synthesize trend data from multiple sources (Google Trends, consumer intent, competitive landscape, regional demand) 
into actionable product development and marketing recommendations.

ANALYSIS FRAMEWORK:

1. OPPORTUNITY SCORING (0-100):
   Calculate composite score from:
   - Demand Score (30%): Growth rate + search volume indicators
   - Competition Score (25%): Inverse of market saturation (fewer competitors = higher score)
   - Timing Score (20%): How well launch aligns with seasonality/trend momentum
   - Feasibility Score (15%): Manufacturing complexity (assume standard for most ingredients)
   - Margin Score (10%): Price gap opportunities identified

2. RECOMMENDATION TIERS:
   - TIER 1 - IMMEDIATE ACTION (Score > 80): Launch within 3 months, high confidence
   - TIER 2 - PLAN FOR NEXT QUARTER (Score 60-80): Launch within 6 months, good opportunity
   - TIER 3 - MONITOR (Score 40-60): Track for 3-6 months, potential future opportunity
   - TIER 4 - AVOID (Score < 40): Do not pursue currently

3. OUTPUT STRUCTURE:
   Provide JSON with:
   - opportunity_score: Overall score (0-100)
   - scores_breakdown: Individual component scores
   - tier: Recommendation tier
   - confidence: "high", "medium", or "low"
   - key_insights: Array of 3-5 key insights
   - product_recommendations: Specific product concepts
   - marketing_angles: Key messaging opportunities
   - risks: Array of risk factors
   - next_steps: Actionable next steps

4. FOCUS AREAS:
   - Identify format gaps (e.g., cream vs serum dominance)
   - Highlight specific concern targeting opportunities
   - Note regional demand patterns
   - Flag competitive positioning opportunities
   - Suggest optimal launch timing

Be specific, actionable, and data-driven in your recommendations.
"""


async def synthesize_trend_insights(
    ingredient: str,
    trend_data: Dict[str, Any],
    consumer_intent_data: Optional[Dict[str, Any]] = None,
    competitive_data: Optional[Dict[str, Any]] = None,
    regional_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Synthesize all trend data sources into actionable insights using Claude AI
    
    Args:
        ingredient: Ingredient name
        trend_data: Trend analysis results
        consumer_intent_data: Consumer intent analysis results
        competitive_data: Competitive landscape analysis
        regional_data: Regional demand analysis
        
    Returns:
        Synthesis with opportunity score, recommendations, and insights
    """
    if not claude_client:
        return {
            "error": "Claude AI not available",
            "synthesis": None
        }
    
    # Check if we have any data to analyze
    # Handle both None and empty dict cases
    has_trend = trend_data and (isinstance(trend_data, dict) and len(trend_data) > 0)
    has_consumer = consumer_intent_data and (isinstance(consumer_intent_data, dict) and len(consumer_intent_data) > 0)
    has_competitive = competitive_data is not None
    has_regional = regional_data is not None
    
    default_synthesis = {
        "opportunity_score": None,
        "scores_breakdown": {},
        "tier": None,
        "confidence": "low",
        "key_insights": [],
        "product_recommendations": [],
        "marketing_angles": [],
        "risks": [],
        "next_steps": []
    }
    
    if not (has_trend or has_consumer or has_competitive or has_regional):
        return {
            "error": "No trend data available for synthesis",
            "synthesis": default_synthesis  # Return default structure instead of None
        }
    
    # Build user prompt with all data
    user_prompt = f"""
Analyze the following trend data for {ingredient} in the Indian personal care market:

"""
    
    if trend_data:
        user_prompt += f"""
=== TREND ANALYSIS ===
{json.dumps(trend_data, indent=2)}

"""
    
    if consumer_intent_data:
        user_prompt += f"""
=== CONSUMER INTENT ANALYSIS ===
{json.dumps(consumer_intent_data, indent=2)}

"""
    
    if competitive_data:
        user_prompt += f"""
=== COMPETITIVE LANDSCAPE ===
{json.dumps(competitive_data, indent=2)}

"""
    
    if regional_data:
        user_prompt += f"""
=== REGIONAL DEMAND ===
{json.dumps(regional_data, indent=2)}

"""
    
    user_prompt += """
Based on this comprehensive data, provide:
1. Overall opportunity score (0-100) with breakdown
2. Recommendation tier (immediate_action, plan_next_quarter, monitor, avoid)
3. Key insights (3-5 most important findings)
4. Specific product recommendations (format, concentration, positioning)
5. Marketing angles (key messaging opportunities)
6. Risk factors
7. Next steps

Return your analysis as JSON matching the structure specified in the system prompt.
"""
    
    try:
        if not claude_model:
            return {
                "error": "Claude model not configured",
                "synthesis": None
            }
        
        response = claude_client.messages.create(
            model=claude_model,
            max_tokens=4096,
            temperature=0.3,
            system=TREND_SYNTHESIS_SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )
        
        if not response.content or len(response.content) == 0:
            return {
                "error": "Empty response from Claude",
                "synthesis": None
            }
        
        content = response.content[0].text.strip()
        
        if not content:
            return {
                "error": "Empty content in Claude response",
                "synthesis": None
            }
        
        # Extract JSON from response
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        # Try to parse JSON
        synthesis = None
        try:
            synthesis = json.loads(content)
        except json.JSONDecodeError as json_err:
            # If JSON parsing fails, try to extract just the JSON object
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                try:
                    synthesis = json.loads(json_match.group(0))
                except json.JSONDecodeError:
                    # Try to fix common JSON issues
                    json_str = json_match.group(0)
                    # Remove trailing commas before closing braces/brackets
                    json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
                    try:
                        synthesis = json.loads(json_str)
                    except json.JSONDecodeError:
                        # Fallback: return structured text response
                        synthesis = {
                            "opportunity_score": None,
                            "key_insights": [content[:500]],  # Limit length
                            "recommendation": "Analysis completed but could not parse structured response",
                            "raw_response": content[:1000]  # Include first 1000 chars for debugging
                        }
            else:
                # Fallback: return structured text response
                synthesis = {
                    "opportunity_score": None,
                    "key_insights": [content[:500]],  # Limit length
                    "recommendation": "Analysis completed but could not parse structured response",
                    "raw_response": content[:1000]  # Include first 1000 chars for debugging
                }
        
        # Ensure synthesis has all required fields with defaults
        default_synthesis = {
            "opportunity_score": None,
            "scores_breakdown": {},
            "tier": None,
            "confidence": "low",
            "key_insights": [],
            "product_recommendations": [],
            "marketing_angles": [],
            "risks": [],
            "next_steps": []
                }
        
        if not synthesis:
            return {
                "error": "Failed to extract synthesis data from Claude response",
                "synthesis": default_synthesis  # Return default structure instead of None
            }
        
        # Merge synthesis with defaults to ensure all fields exist
        if isinstance(synthesis, dict):
            final_synthesis = default_synthesis.copy()
            final_synthesis.update(synthesis)
            # Ensure key_insights is always a list
            if "key_insights" not in final_synthesis or not isinstance(final_synthesis.get("key_insights"), list):
                final_synthesis["key_insights"] = []
        else:
            final_synthesis = default_synthesis
        
        return {
            "ingredient": ingredient,
            "synthesis": final_synthesis,
            "data_sources_used": {
                "trend": bool(trend_data),
                "consumer_intent": consumer_intent_data is not None,
                "competitive": competitive_data is not None,
                "regional": regional_data is not None
            }
        }
        
    except Exception as e:
        # Check if it's an API-related error
        error_type = type(e).__name__
        default_synthesis = {
            "opportunity_score": None,
            "scores_breakdown": {},
            "tier": None,
            "confidence": "low",
            "key_insights": [],
            "product_recommendations": [],
            "marketing_angles": [],
            "risks": [],
            "next_steps": []
        }
        if "API" in error_type or "api" in str(e).lower():
            return {
                "error": f"Claude API error: {str(e)}",
                "synthesis": default_synthesis  # Return default structure instead of None
            }
        import traceback
        error_trace = traceback.format_exc()
        print(f"❌ Synthesis error: {error_trace}")
        return {
            "error": f"Claude synthesis failed: {str(e)}",
            "synthesis": None
        }

