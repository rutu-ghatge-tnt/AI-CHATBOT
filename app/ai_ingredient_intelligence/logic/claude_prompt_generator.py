"""
Claude Prompt Generator for Business Strategy Presentations
===========================================================

This module generates business strategy presentation prompts using Claude AI.
It can be used with any data source (Make a Wish, Formulation Reports, etc.)

FLOW:
1. Receives structured data
2. Formats data for Claude
3. Sends to Claude to generate business strategy prompt
4. Returns prompt ready for Gamma API
"""

import os
from typing import Dict, Any, Optional
import json

# Import Claude client
try:
    from app.ai_ingredient_intelligence.logic.make_wish_generator import (
        claude_client,
        claude_model
    )
    claude_api_key = os.getenv("CLAUDE_API_KEY")
    CLAUDE_AVAILABLE = claude_client is not None and claude_api_key is not None
except (ImportError, AttributeError):
    claude_client = None
    claude_model = None
    CLAUDE_AVAILABLE = False


BUSINESS_STRATEGY_SYSTEM_PROMPT = """You are a skincare formulation expert and skincare brand commercialization strategist.

Your task is to analyze Make a Wish product data (product wish, technical formulation, market insights) and create a specific, detailed prompt for Gamma API that will generate a 15-slide professional presentation.

The prompt must:
- Be very specific to the provided wish data (not generalized)
- Follow the exact 15-slide structure provided
- Translate technical formulation data into clear, founder-ready language
- Be simple, focused, and actionable
- Generate content that is commercially realistic and science-backed
- **CRITICAL: All prices, costs, and monetary values MUST be displayed in Indian Rupees (₹). Never use dollars ($) or any other currency. All cost figures in the data are in Indian Rupees.**

The output prompt should instruct Gamma API to create a presentation that is professional, commercially realistic, and easy to understand for aspiring skincare founders."""


DEFAULT_BUSINESS_STRATEGY_PROMPT = """You are a skincare formulation expert and skincare brand commercialization strategist.

I will provide:
- A product wish from an aspiring skincare founder
- Technical formulation data (ingredients, percentages, functions, complexity score, safety, compliance)
- Market insights (audience, pricing, trends, competition)

Your task is to generate content for a 15-slide professional presentation that translates this data into clear, founder-ready language.

OUTPUT INSTRUCTIONS:
Follow the exact slide structure below. For each slide, provide:
- Slide Title
- Concise bullet points (3–6 max)

Keep tone:
- Professional
- Commercially realistic
- Science-backed but easy to understand

**CRITICAL CURRENCY REQUIREMENT: All prices, costs, and monetary values MUST be displayed in Indian Rupees (₹). Never use dollars ($) or any other currency. All cost figures in the data are in Indian Rupees (₹).**

Do NOT mention Formulynx in the output. Avoid emojis and marketing fluff.

SLIDE STRUCTURE (MANDATORY - 15 SLIDES ONLY):
Slide 1 – Product Overview: Name, Product Positioning Statement (1–2 lines), Complexity Score, Date
Slide 2 – Formula Overview: Product type and format, Target Audience, Texture and Sensory Experience, Possible Claims
Slide 3 – Hero Ingredients: Key active ingredients, Functional role, Why relevant for target consumer
Slide 4 – Complete Formulation: Ingredient categories, Functional architecture, Notable formulation highlights
Slide 5 – Cost and Packaging: Estimated formulation cost drivers, Packaging format recommendation, Impact on cost and positioning
Slide 6 – Pricing Economics & Strategy: Suggested price range, Cost-to-price logic, Target margin logic
Slide 7 – Compliance & Safety: Safety considerations, Skin-type suitability, Regulatory readiness overview
Slide 8 – Go-To-Market Snapshot: Primary launch channel, Secondary channels, Key marketing angle
Slide 9 – Market Trends: Relevant skincare trends, Ingredient or format trends, Consumer behavior shifts
Slide 10 – Market Gaps: Limitations of current products, Unmet consumer needs, How this product addresses the gap
Slide 11 – Brand Competition Landscape: Type of competing brands, Common positioning strategies, Differentiation opportunity
Slide 12 – The Opportunity: Why this product can succeed, Market attractiveness, Scalability potential
Slide 13 – Recommended Action Plan: Immediate next steps, Mid-term development actions, Commercial readiness milestones
Slide 14 – Closing Slide: Summary of value proposition, Brand vision outlook, Final takeaway statement"""


async def generate_business_strategy_prompt(
    data_text: str,
    data_type: str = "cosmetic_formulation",
    custom_instructions: Optional[str] = None
) -> str:
    """
    Generate a business strategy presentation prompt using Claude AI.
    
    Args:
        data_text: Formatted text containing all the data to analyze
        data_type: Type of data (e.g., "cosmetic_formulation", "product_analysis")
        custom_instructions: Optional custom instructions to add to the prompt
    
    Returns:
        str: Business strategy prompt ready for Gamma API
    """
    
    if not CLAUDE_AVAILABLE or not claude_client:
        print("⚠️ Claude client not available, using default business strategy prompt")
        return DEFAULT_BUSINESS_STRATEGY_PROMPT
    
    try:
        user_prompt = f"""Analyze the following Make a Wish product data and create a SPECIFIC, DETAILED prompt for Gamma API.

DATA TO ANALYZE:
{data_text}

Your task:
1. Extract the product wish/vision from the data
2. Extract technical formulation details (ingredients, percentages, functions, complexity)
3. Extract market insights (target audience, pricing, trends, competition)
4. Create a VERY SPECIFIC prompt for Gamma API that follows the exact 15-slide structure

The prompt you create must:
- Be SPECIFIC to this exact product and wish data (not generic)
- Follow the EXACT 15-slide structure provided in the system prompt
- Translate technical formulation data into founder-ready language
- Be simple, clear, and actionable
- Include specific details from the data (product name, ingredients, costs, etc.)
- Generate exactly 15 slides (no more, no less)
- Use professional, commercially realistic tone
- Be science-backed but easy to understand
- **CRITICAL: All prices, costs, and monetary values MUST be in Indian Rupees (₹). The data contains costs in ₹ (rupees), and the presentation MUST display all monetary values in ₹ only. Never convert to dollars ($) or any other currency.**

IMPORTANT:
- The prompt should reference specific details from the data (e.g., actual ingredient names, cost figures in ₹, target audience)
- Do NOT create a generic template - make it specific to THIS product
- Ensure the prompt will generate content that is directly relevant to the provided wish data
- Keep it focused on Make a Wish product commercialization
- **Explicitly instruct Gamma API to use Indian Rupees (₹) for all pricing, costs, and monetary values in the presentation**

{f"ADDITIONAL REQUIREMENTS: {custom_instructions}" if custom_instructions else ""}

Return ONLY the prompt text that should be sent to Gamma API's additionalInstructions field. The prompt should be specific enough that Gamma will generate a presentation directly relevant to the provided product data. Do not include any explanations or meta-commentary."""
        
        print(f"[CLAUDE] 🤖 Generating business strategy prompt from {data_type} data...")
        print(f"[CLAUDE] Data length: {len(data_text)} characters")
        print(f"[CLAUDE] 📋 First 500 chars of data being sent to Claude:")
        print(f"[CLAUDE] {data_text[:500]}...")
        print(f"[CLAUDE] 📋 Last 500 chars of data being sent to Claude:")
        print(f"[CLAUDE] ...{data_text[-500:]}")
        
        print(f"\n[CLAUDE] 📤 Sending request to Claude...")
        print(f"[CLAUDE] System prompt length: {len(BUSINESS_STRATEGY_SYSTEM_PROMPT)} characters")
        print(f"[CLAUDE] User prompt length: {len(user_prompt)} characters")
        
        # Format system prompt with cache_control (GA approach - SDK 0.34.0+)
        from app.ai_ingredient_intelligence.logic.prompt_cache_manager import format_system_prompt_with_cache
        formatted_system = format_system_prompt_with_cache(
            system_prompt=BUSINESS_STRATEGY_SYSTEM_PROMPT,
            prompt_type="business_strategy_prompt",
            claude_client=claude_client,
            ttl="1h"  # 1 hour ephemeral cache
        )
        
        if isinstance(formatted_system, list):
            print(f"[CLAUDE] [CACHE] Using prompt caching (GA) - system prompt formatted as content blocks")
        else:
            print(f"[CLAUDE] Using plain system prompt (caching disabled or failed)")
        
        claude_response = claude_client.messages.create(
            model=claude_model,
            max_tokens=4096,
            temperature=0.3,
            system=formatted_system,  # Can be string or list of content blocks with cache_control
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )
        
        if claude_response.content and len(claude_response.content) > 0:
            generated_prompt = claude_response.content[0].text.strip()
            print(f"\n[CLAUDE] ✅ Generated business strategy prompt ({len(generated_prompt)} characters)")
            print(f"[CLAUDE] 📋 Full Claude-generated prompt:")
            print(f"{'='*80}")
            print(f"{generated_prompt}")
            print(f"{'='*80}")
            print(f"[CLAUDE] 📋 First 1000 chars of generated prompt:")
            print(f"{generated_prompt[:1000]}...")
            print(f"[CLAUDE] 📋 Last 1000 chars of generated prompt:")
            print(f"...{generated_prompt[-1000:]}")
            return generated_prompt
        else:
            print(f"[CLAUDE] ⚠️ Claude returned empty response, using default prompt")
            return DEFAULT_BUSINESS_STRATEGY_PROMPT
            
    except Exception as e:
        print(f"[CLAUDE] ❌ Error generating prompt: {e}")
        import traceback
        traceback.print_exc()
        return DEFAULT_BUSINESS_STRATEGY_PROMPT


def get_default_business_strategy_prompt() -> str:
    """
    Get the default business strategy prompt (fallback when Claude is unavailable).
    
    Returns:
        str: Default business strategy prompt
    """
    return DEFAULT_BUSINESS_STRATEGY_PROMPT

