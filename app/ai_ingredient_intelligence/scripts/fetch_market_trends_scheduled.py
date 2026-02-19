"""
Scheduled Market Trends Fetcher - Monthly Batch Processing
==========================================================

This script runs monthly (1st of every month at 2:00 AM IST) to fetch market trend data
for all ingredients, benefits, brands, and comparison queries defined in the config.
Uses SerpAPI to fetch Google Trends and Google Shopping data.

Based on: Formulynx SerpAPI Market Trends Batch Config v2.0.0
"""

import asyncio
import os
import sys
import json
import statistics
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Set
from pathlib import Path
from collections import defaultdict
from tqdm import tqdm

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from app.ai_ingredient_intelligence.db.collections import market_trends_storage_col
from app.ai_ingredient_intelligence.logic.trend_analyzer import TrendAnalyzer
from app.ai_ingredient_intelligence.logic.trend_analyzer import SerpAPIClient
from app.ai_ingredient_intelligence.serpapi_batch_config.serpapi_batch_config import load_config

# Global variable for tracking batch start time
_batch_start_time = None


class BatchQueryGenerator:
    """Generates queries from config based on query generation rules"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.ingredients = config.get("ingredients", {})
        self.product_formats = config.get("product_formats", {})
        self.benefits = config.get("benefits", {})
        self.brands = config.get("brands", {})
        self.query_rules = config.get("query_generation_rules", {})
    
    def generate_level_1_queries(self) -> List[Dict[str, Any]]:
        """Generate Level 1: Ingredient × Format combinations"""
        queries = []
        rules = self.query_rules.get("level_1_ingredient_queries", {})
        max_per_ingredient = rules.get("max_queries_per_ingredient", 8)
        
        # Process skincare ingredients
        skincare_ingredients = self.ingredients.get("skincare", {})
        for category, ingredient_list in skincare_ingredients.items():
            # Skip non-list values like "_description"
            if not isinstance(ingredient_list, list):
                continue
            for ingredient in ingredient_list:
                if not isinstance(ingredient, dict):
                    continue
                ingredient_queries = self._generate_ingredient_queries(
                    ingredient, "skincare", max_per_ingredient
                )
                queries.extend(ingredient_queries)
        
        # Process haircare ingredients
        haircare_ingredients = self.ingredients.get("haircare", {})
        for category, ingredient_list in haircare_ingredients.items():
            # Skip non-list values like "_description"
            if not isinstance(ingredient_list, list):
                continue
            for ingredient in ingredient_list:
                if not isinstance(ingredient, dict):
                    continue
                ingredient_queries = self._generate_ingredient_queries(
                    ingredient, "haircare", max_per_ingredient
                )
                queries.extend(ingredient_queries)
        
        return queries
    
    def _generate_ingredient_queries(
        self, 
        ingredient: Dict[str, Any], 
        category: str,
        max_queries: int
    ) -> List[Dict[str, Any]]:
        """Generate queries for a single ingredient"""
        queries = []
        ingredient_id = ingredient.get("id", "")
        common_name = ingredient.get("common_name", "")
        search_terms = ingredient.get("search_terms", [common_name])
        compatible_formats = ingredient.get("compatible_formats", [])
        hindi_terms = ingredient.get("hindi_terms", [])
        
        # Get formats for this category
        formats = self.product_formats.get(category, [])
        format_map = {f["id"]: f for f in formats}
        
        # Generate format-based queries
        for format_id in compatible_formats[:max_queries]:
            if format_id in format_map:
                format_info = format_map[format_id]
                format_search_terms = format_info.get("search_terms", [format_id])
                
                # Primary query: ingredient + format
                for search_term in search_terms[:2]:  # Limit search terms
                    for format_term in format_search_terms[:1]:  # Limit format terms
                        query_text = f"{search_term} {format_term}"
                        queries.append({
                            "query_text": query_text,
                            "query_level": "ingredient",
                            "category": category,
                            "ingredient_tag": ingredient_id,
                            "ingredient_name": common_name,
                            "product_format": format_id,
                            "benefit_tag": None,
                            "brand_tag": None,
                            "comparison_group": None
                        })
        
        # Generate Hindi queries if available
        if hindi_terms:
            for hindi_term in hindi_terms[:2]:  # Limit to 2 Hindi queries
                queries.append({
                    "query_text": f"{hindi_term} for face",
                    "query_level": "ingredient",
                    "category": category,
                    "ingredient_tag": ingredient_id,
                    "ingredient_name": common_name,
                    "product_format": None,
                    "benefit_tag": None,
                    "brand_tag": None,
                    "comparison_group": None,
                    "is_hindi": True
                })
        
        return queries[:max_queries]  # Limit total queries per ingredient
    
    def generate_level_2_queries(self) -> List[Dict[str, Any]]:
        """Generate Level 2: Benefit × Format combinations"""
        queries = []
        rules = self.query_rules.get("level_2_benefit_queries", {})
        max_per_benefit = rules.get("max_queries_per_benefit", 6)
        skin_types = rules.get("skin_types_to_cross", [])
        
        # Process skincare benefits
        skincare_benefits = self.benefits.get("skincare", [])
        for benefit in skincare_benefits:
            if not isinstance(benefit, dict):
                continue
            benefit_queries = self._generate_benefit_queries(
                benefit, "skincare", max_per_benefit, skin_types
            )
            queries.extend(benefit_queries)
        
        # Process haircare benefits
        haircare_benefits = self.benefits.get("haircare", [])
        for benefit in haircare_benefits:
            if not isinstance(benefit, dict):
                continue
            benefit_queries = self._generate_benefit_queries(
                benefit, "haircare", max_per_benefit, []
            )
            queries.extend(benefit_queries)
        
        return queries
    
    def _generate_benefit_queries(
        self,
        benefit: Dict[str, Any],
        category: str,
        max_queries: int,
        skin_types: List[str]
    ) -> List[Dict[str, Any]]:
        """Generate queries for a single benefit"""
        queries = []
        benefit_id = benefit.get("id", "")
        search_terms = benefit.get("search_terms", [])
        
        # Get formats for this category
        formats = self.product_formats.get(category, [])
        
        # Generate benefit + format queries
        for format_info in formats[:3]:  # Limit to top 3 formats
            format_id = format_info.get("id", "")
            format_search_terms = format_info.get("search_terms", [format_id])
            
            for benefit_term in search_terms[:2]:  # Limit benefit terms
                for format_term in format_search_terms[:1]:  # Limit format terms
                    query_text = f"{benefit_term} {format_term}"
                    queries.append({
                        "query_text": query_text,
                        "query_level": "benefit",
                        "category": category,
                        "ingredient_tag": None,
                        "product_format": format_id,
                        "benefit_tag": benefit_id,
                        "brand_tag": None,
                        "comparison_group": None
                    })
        
        # Add skin type variations
        for skin_type in skin_types[:2]:  # Limit skin types
            for benefit_term in search_terms[:1]:
                queries.append({
                    "query_text": f"{benefit_term} for {skin_type}",
                    "query_level": "benefit",
                    "category": category,
                    "ingredient_tag": None,
                    "product_format": None,
                    "benefit_tag": benefit_id,
                    "brand_tag": None,
                    "comparison_group": None
                })
        
        return queries[:max_queries]
    
    def generate_level_3_queries(self) -> List[Dict[str, Any]]:
        """Generate Level 3: Brand × Hero Product combinations"""
        queries = []
        rules = self.query_rules.get("level_3_brand_queries", {})
        max_per_brand = rules.get("max_queries_per_brand", 5)
        
        # Process all brand categories
        for brand_category, brand_list in self.brands.items():
            # Skip non-list values like "_description"
            if not isinstance(brand_list, list):
                continue
            
            for brand in brand_list:
                # Skip if brand is not a dict
                if not isinstance(brand, dict):
                    continue
                    
                brand_queries = self._generate_brand_queries(
                    brand, brand_category, max_per_brand
                )
                queries.extend(brand_queries)
        
        return queries
    
    def _generate_brand_queries(
        self,
        brand: Dict[str, Any],
        brand_category: str,
        max_queries: int
    ) -> List[Dict[str, Any]]:
        """Generate queries for a single brand"""
        queries = []
        brand_id = brand.get("id", "")
        brand_prefix = brand.get("search_prefix", brand.get("name", ""))
        hero_products = brand.get("hero_products", [])[:5]  # Top 5 products
        
        for product in hero_products:
            query_text = f"{brand_prefix} {product}"
            queries.append({
                "query_text": query_text,
                "query_level": "brand",
                "category": "skincare" if "skincare" in brand_category else "haircare",
                "ingredient_tag": None,
                "product_format": None,
                "benefit_tag": None,
                "brand_tag": brand_id,
                "brand_name": brand.get("name", ""),
                "comparison_group": None
            })
        
        return queries[:max_queries]
    
    def generate_comparison_queries(self) -> List[Dict[str, Any]]:
        """Generate comparison queries for Google Trends comparison mode"""
        queries = []
        rules = self.query_rules.get("comparison_queries", {})
        comparison_groups = rules.get("comparison_groups", {})
        max_per_group = rules.get("max_comparisons_per_group", 3)
        
        for group_name, items in comparison_groups.items():
            if len(items) >= 2:
                # Generate pairwise comparisons
                for i in range(min(len(items), max_per_group * 2)):
                    for j in range(i + 1, min(len(items), i + max_per_group + 1)):
                        if j - i <= max_per_group:
                            query_text = f"{items[i]},{items[j]}"
                            queries.append({
                                "query_text": query_text,
                                "query_level": "comparison",
                                "category": "skincare" if "hair" not in group_name.lower() else "haircare",
                                "ingredient_tag": None,
                                "product_format": None,
                                "benefit_tag": None,
                                "brand_tag": None,
                                "comparison_group": group_name
                            })
        
        return queries
    
    def generate_all_queries(self) -> List[Dict[str, Any]]:
        """Generate all queries and deduplicate"""
        all_queries = []
        
        print("📝 Generating Level 1 (Ingredient × Format) queries...")
        level_1 = self.generate_level_1_queries()
        all_queries.extend(level_1)
        print(f"   Generated {len(level_1)} Level 1 queries")
        
        print("📝 Generating Level 2 (Benefit × Format) queries...")
        level_2 = self.generate_level_2_queries()
        all_queries.extend(level_2)
        print(f"   Generated {len(level_2)} Level 2 queries")
        
        print("📝 Generating Level 3 (Brand × Product) queries...")
        level_3 = self.generate_level_3_queries()
        all_queries.extend(level_3)
        print(f"   Generated {len(level_3)} Level 3 queries")
        
        print("📝 Generating comparison queries...")
        comparisons = self.generate_comparison_queries()
        all_queries.extend(comparisons)
        print(f"   Generated {len(comparisons)} comparison queries")
        
        # Deduplicate by query_text
        seen = set()
        unique_queries = []
        for q in all_queries:
            query_text = q["query_text"]
            if query_text not in seen:
                seen.add(query_text)
                unique_queries.append(q)
        
        print(f"\n✅ Total unique queries: {len(unique_queries)} (deduplicated from {len(all_queries)})")
        
        return unique_queries


class BatchTrendFetcher:
    """Fetches trend data in batches with rate limiting and retries"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.batch_config = config.get("batch_job_config", {})
        self.client = SerpAPIClient()
        self.rate_limit_per_second = self.batch_config.get("rate_limit_per_second", 5)
        self.max_retries = self.batch_config.get("max_retries", 3)
        self.retry_delay = self.batch_config.get("retry_delay_seconds", 10)
        self.time_range = self.batch_config.get("trends_time_range", "today 12-m")
        self.geo = self.batch_config.get("geo", "IN")
        self.language = self.batch_config.get("language", "en")
    
    async def fetch_trends_data(self, query_info: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch trends data for a single query with retries"""
        query_text = query_info["query_text"]
        query_level = query_info["query_level"]
        
        for attempt in range(self.max_retries):
            try:
                # Rate limiting
                if attempt > 0:
                    await asyncio.sleep(self.retry_delay * attempt)
                
                # Fetch interest over time
                trends_data = self.client.get_trends_timeseries(
                    query_text,
                    time_range=self.time_range,
                    geo=self.geo,
                    hl=self.language
                )
                
                if trends_data and "error" in trends_data:
                    if attempt < self.max_retries - 1:
                        continue
                    return {"error": trends_data.get("error")}
                
                # Fetch related queries
                related_data = {}
                try:
                    related_data = self.client.get_trends_related_queries(
                        query_text,
                        time_range=self.time_range,
                        geo=self.geo,
                        hl=self.language
                    )
                    if related_data and "error" in related_data:
                        related_data = {}
                except:
                    related_data = {}
                
                # Fetch regional data
                regional_data = {}
                try:
                    regional_data = self.client.get_trends_regional(
                        query_text,
                        time_range=self.time_range,
                        geo=self.geo,
                        hl=self.language
                    )
                    if regional_data and "error" in regional_data:
                        regional_data = {}
                except:
                    regional_data = {}
                
                # Fetch related topics (NEW)
                related_topics_data = {}
                try:
                    related_topics_data = self.client.get_trends_related_topics(
                        query_text,
                        time_range=self.time_range,
                        geo=self.geo,
                        hl=self.language
                    )
                    if related_topics_data and "error" in related_topics_data:
                        related_topics_data = {}
                except:
                    related_topics_data = {}
                
                # Process and calculate metrics
                processed_data = self._process_trends_data(
                    trends_data, related_data, regional_data, related_topics_data, query_info
                )
                
                return processed_data
                
            except Exception as e:
                if attempt < self.max_retries - 1:
                    print(f"   ⚠️  Attempt {attempt + 1} failed: {str(e)}, retrying...")
                    continue
                else:
                    return {"error": str(e)}
        
        return {"error": "Max retries exceeded"}
    
    def _process_trends_data(
        self,
        trends_data: Dict[str, Any],
        related_data: Dict[str, Any],
        regional_data: Dict[str, Any],
        related_topics_data: Dict[str, Any],
        query_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process raw trends data and calculate derived metrics"""
        interest_over_time = trends_data.get("interest_over_time", {})
        timeline = interest_over_time.get("timeline_data", [])
        
        if not timeline:
            return {"error": "No timeline data available"}
        
        # Extract values
        values = []
        dates = []
        for point in timeline:
            if point.get("values"):
                val = point["values"][0].get("extracted_value", 0)
                if val is not None:
                    # Ensure value is numeric
                    try:
                        val = int(val) if isinstance(val, (int, float, str)) else 0
                    except (ValueError, TypeError):
                        val = 0
                    values.append(val)
                    dates.append(point.get("date", ""))
        
        if len(values) < 4:
            return {"error": "Insufficient data points"}
        
        # Calculate metrics
        current_score = values[-1] if values else 0
        peak_score = max(values) if values else 0
        peak_idx = values.index(peak_score) if peak_score in values else -1
        peak_month = dates[peak_idx] if peak_idx >= 0 and peak_idx < len(dates) else ""
        
        # Calculate growth percentages
        growth_pct_3m = self._calculate_growth(values, 4)  # ~1 month
        growth_pct_6m = self._calculate_growth(values, 12)  # ~3 months
        growth_pct_12m = self._calculate_growth(values, 48)  # ~12 months
        
        # Determine trend direction
        trend_direction = self._classify_trend_direction(growth_pct_6m)
        
        # Process related queries
        related_queries_rising = []
        related_queries_top = []
        if related_data:
            related_queries = related_data.get("related_queries", {})
            for item in related_queries.get("rising", [])[:10]:
                related_queries_rising.append({
                    "query": item.get("query", ""),
                    "growth": item.get("value", ""),
                    "extracted_value": item.get("extracted_value", 0)
                })
            for item in related_queries.get("top", [])[:10]:
                related_queries_top.append({
                    "query": item.get("query", ""),
                    "volume": item.get("value", ""),
                    "extracted_value": item.get("extracted_value", 0)
                })
        
        # Process regional data
        regional_interest = []
        if regional_data:
            interest_by_region = regional_data.get("interest_by_region", [])
            for region in interest_by_region[:20]:  # Top 20 regions
                regional_interest.append({
                    "location": region.get("location", ""),
                    "value": region.get("value", ""),
                    "extracted_value": region.get("extracted_value", 0)
                })
        
        # Process related topics (NEW)
        related_topics_rising = []
        related_topics_top = []
        if related_topics_data:
            related_topics = related_topics_data.get("related_topics", {})
            for item in related_topics.get("rising", [])[:10]:
                related_topics_rising.append({
                    "topic": item.get("topic", ""),
                    "type": item.get("type", ""),
                    "growth": item.get("value", ""),
                    "extracted_value": item.get("extracted_value", 0)
                })
            for item in related_topics.get("top", [])[:10]:
                related_topics_top.append({
                    "topic": item.get("topic", ""),
                    "type": item.get("type", ""),
                    "value": item.get("value", ""),
                    "extracted_value": item.get("extracted_value", 0)
                })
        
        # Compute derived insights
        seasonality = self._compute_seasonality(values, dates)
        rising_query_insights = self._compute_rising_query_insights(related_queries_rising)
        regional_insights = self._compute_regional_insights(regional_interest)
        
        # Competitive position will be computed later when we have comparison group data
        competitive_position = {
            "comparison_group": query_info.get("comparison_group"),
            "rank_in_group": None,  # Will be computed in post-processing
            "total_in_group": None,
            "vs_group_average": None,
            "nearest_competitor": None,
            "nearest_competitor_score": None,
            "gap": None
        }
        
        return {
            "query_text": query_info["query_text"],
            "query_level": query_info["query_level"],
            "category": query_info.get("category"),
            "ingredient_tag": query_info.get("ingredient_tag"),
            "product_format": query_info.get("product_format"),
            "benefit_tag": query_info.get("benefit_tag"),
            "brand_tag": query_info.get("brand_tag"),
            "comparison_group": query_info.get("comparison_group"),
            "interest_over_time": {
                "timeline_data": timeline,
                "values": values,
                "dates": dates
            },
            "related_queries_rising": related_queries_rising,
            "related_queries_top": related_queries_top,
            "related_topics_rising": related_topics_rising,  # NEW
            "related_topics_top": related_topics_top,  # NEW
            "regional_interest": regional_interest,
            "current_score": current_score,
            "peak_score": peak_score,
            "peak_month": peak_month,
            "growth_pct_3m": growth_pct_3m,
            "growth_pct_6m": growth_pct_6m,
            "growth_pct_12m": growth_pct_12m,
            "trend_direction": trend_direction,
            "seasonality": seasonality,  # NEW
            "rising_query_insights": rising_query_insights,  # NEW
            "regional_insights": regional_insights,  # NEW
            "competitive_position": competitive_position,  # NEW (will be computed in post-processing)
            "shopping_data": None,  # Will be added separately if fetched
            "fetched_at": datetime.utcnow(),
            "fetch_source": "batch"
        }
    
    def _calculate_growth(self, values: List[int], period_weeks: int) -> float:
        """Calculate growth percentage over a period"""
        if len(values) < period_weeks * 2:
            return 0.0
        
        current_period = statistics.mean(values[-period_weeks:])
        previous_period = statistics.mean(values[-period_weeks*2:-period_weeks])
        
        if previous_period > 0:
            return ((current_period - previous_period) / previous_period) * 100
        return 0.0
    
    def _classify_trend_direction(self, growth_pct_6m: float) -> str:
        """Classify trend direction based on 6-month growth"""
        if growth_pct_6m > 100:
            return "rising_fast"
        elif growth_pct_6m > 20:
            return "rising"
        elif growth_pct_6m > -20:
            return "stable"
        elif growth_pct_6m > -50:
            return "declining"
        else:
            return "declining_fast"
    
    def _compute_seasonality(self, values: List[int], dates: List[str]) -> Dict[str, Any]:
        """Compute seasonality insights from timeline data"""
        if len(values) < 12 or len(dates) < 12:
            return {
                "peak_months": [],
                "low_months": [],
                "peak_reason_hint": "",
                "best_launch_window": "",
                "seasonal_swing_pct": 0,
                "seasonal_swing_note": ""
            }
        
        # Group by month
        monthly_avg = {}
        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", 
                      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        
        for i, date_str in enumerate(dates):
            if i >= len(values):
                break
            try:
                # Extract month from date string (format: "2024-01-15" or similar)
                if "-" in date_str:
                    month_num = int(date_str.split("-")[1]) - 1
                elif "/" in date_str:
                    month_num = int(date_str.split("/")[0]) - 1
                else:
                    continue
                
                if 0 <= month_num < 12:
                    month_name = month_names[month_num]
                    if month_name not in monthly_avg:
                        monthly_avg[month_name] = []
                    monthly_avg[month_name].append(values[i])
            except:
                continue
        
        # Calculate averages per month
        monthly_scores = {}
        for month, vals in monthly_avg.items():
            if vals:
                # Ensure all values are numeric
                numeric_vals = []
                for v in vals:
                    try:
                        numeric_vals.append(float(v) if not isinstance(v, (int, float)) else v)
                    except (ValueError, TypeError):
                        continue
                if numeric_vals:
                    monthly_scores[month] = statistics.mean(numeric_vals)
        
        if not monthly_scores:
            return {
                "peak_months": [],
                "low_months": [],
                "peak_reason_hint": "",
                "best_launch_window": "",
                "seasonal_swing_pct": 0,
                "seasonal_swing_note": ""
            }
        
        # Find peak and low months
        sorted_months = sorted(monthly_scores.items(), key=lambda x: x[1], reverse=True)
        peak_months = [m[0] for m in sorted_months[:2]]  # Top 2
        low_months = [m[0] for m in sorted_months[-2:]]  # Bottom 2
        
        peak_score = sorted_months[0][1] if sorted_months else 0
        low_score = sorted_months[-1][1] if sorted_months else 0
        
        # Calculate seasonal swing
        seasonal_swing_pct = 0
        if peak_score > 0:
            seasonal_swing_pct = ((peak_score - low_score) / peak_score) * 100
        
        # Determine best launch window
        best_launch_window = ""
        if peak_months:
            if "Feb" in peak_months or "Mar" in peak_months:
                best_launch_window = "Feb-Mar"
            elif "Oct" in peak_months or "Nov" in peak_months:
                best_launch_window = "Oct-Nov"
            else:
                best_launch_window = f"{peak_months[0]}-{peak_months[-1] if len(peak_months) > 1 else peak_months[0]}"
        
        # Peak reason hint
        peak_reason_hint = ""
        if "Feb" in peak_months or "Mar" in peak_months:
            peak_reason_hint = "Pre-summer brightening season"
        elif "Oct" in peak_months or "Nov" in peak_months:
            peak_reason_hint = "Diwali/festive shopping season"
        else:
            peak_reason_hint = f"Peak interest in {', '.join(peak_months)}"
        
        seasonal_swing_note = f"Interest drops ~{seasonal_swing_pct:.0f}% from peak ({peak_score:.0f}) to trough ({low_score:.0f})"
        
        return {
            "peak_months": peak_months,
            "low_months": low_months,
            "peak_reason_hint": peak_reason_hint,
            "best_launch_window": best_launch_window,
            "seasonal_swing_pct": round(seasonal_swing_pct, 1),
            "seasonal_swing_note": seasonal_swing_note
        }
    
    def _compute_rising_query_insights(self, related_queries_rising: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Extract insights from rising queries"""
        emerging_brands = []
        established_brands = []
        review_queries = []
        comparison_queries = []
        price_queries = []
        concern_queries = []
        
        # Known established brands (from config or common knowledge)
        established_brand_names = [
            "Garnier", "Minimalist", "Himalaya", "L'Oreal", "Neutrogena",
            "Cetaphil", "Plum", "Mamaearth", "The Derma Co", "Dot and Key",
            "Forest Essentials", "Kama Ayurveda", "Biotique"
        ]
        
        for query_item in related_queries_rising:
            query = query_item.get("query", "").lower()
            
            # Extract brand names (simple heuristic - words that might be brands)
            words = query.split()
            for word in words:
                if len(word) > 3 and word.isalpha():
                    # Check if it's a known brand
                    if any(brand.lower() in query for brand in established_brand_names):
                        brand_found = next((b for b in established_brand_names if b.lower() in query), None)
                        if brand_found and brand_found not in established_brands:
                            established_brands.append(brand_found)
                    elif word not in ["serum", "cream", "for", "skin", "face", "best", "review", "price", "buy"]:
                        # Potential new brand
                        if word.title() not in emerging_brands and word.title() not in established_brands:
                            emerging_brands.append(word.title())
            
            # Categorize query intent
            if "review" in query:
                review_queries.append(query_item.get("query", ""))
            if "vs" in query or "versus" in query or "compare" in query:
                comparison_queries.append(query_item.get("query", ""))
            if "price" in query or "cost" in query or "buy" in query or "₹" in query:
                price_queries.append(query_item.get("query", ""))
            if any(word in query for word in ["acne", "pigmentation", "dark", "spots", "wrinkle", "dry", "oily"]):
                concern_queries.append(query_item.get("query", ""))
        
        # Limit emerging brands to top 5
        emerging_brands = emerging_brands[:5]
        
        # Market saturation signal
        market_saturation_signal = "low"
        market_saturation_note = ""
        if len(emerging_brands) >= 4:
            market_saturation_signal = "high"
            market_saturation_note = f"Multiple new brand entries ({len(emerging_brands)}) suggest high competition but also strong demand"
        elif len(emerging_brands) >= 2:
            market_saturation_signal = "medium"
            market_saturation_note = f"Some new brand activity ({len(emerging_brands)} brands) indicates growing market"
        else:
            market_saturation_note = "Limited new brand activity suggests stable market"
        
        return {
            "emerging_brands": emerging_brands,
            "emerging_brands_note": f"{len(emerging_brands)} new brands rising fast in this space" if emerging_brands else "No new brands detected",
            "established_brands_in_top": established_brands[:5],
            "user_intent_signals": {
                "review_seeking": len(review_queries) > 0,
                "review_queries": review_queries[:3],
                "comparison_seeking": len(comparison_queries) > 0,
                "price_seeking": len(price_queries) > 0,
                "concern_queries": concern_queries[:3]
            },
            "market_saturation_signal": market_saturation_signal,
            "market_saturation_note": market_saturation_note
        }
    
    def _compute_regional_insights(self, regional_interest: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compute regional insights with tier classification"""
        # Tier classification
        metro_states = ["Delhi", "Maharashtra", "Karnataka", "Tamil Nadu", "West Bengal", 
                       "Gujarat", "Telangana", "Andhra Pradesh"]
        tier2_states = ["Madhya Pradesh", "Rajasthan", "Uttar Pradesh", "Punjab", 
                       "Haryana", "Bihar", "Odisha", "Assam"]
        northeast_states = ["Nagaland", "Manipur", "Mizoram", "Meghalaya", 
                           "Arunachal Pradesh", "Tripura", "Sikkim"]
        
        top_metros = []
        top_tier2 = []
        surprise_markets = []
        
        for region in regional_interest:
            location = region.get("location", "")
            # Ensure value is an integer
            value = region.get("extracted_value", 0) or region.get("value", 0)
            try:
                value = int(value) if value else 0
            except (ValueError, TypeError):
                value = 0
            
            if not location:
                continue
            
            region_data = {
                "location": location,
                "value": value,
                "tier": "other"
            }
            
            # Classify by tier
            if any(metro in location for metro in metro_states):
                region_data["tier"] = "metro"
                top_metros.append(region_data)
            elif any(tier2 in location for tier2 in tier2_states):
                region_data["tier"] = "tier2"
                top_tier2.append(region_data)
            elif any(ne in location for ne in northeast_states):
                region_data["tier"] = "northeast"
                if value >= 70:  # High interest
                    surprise_markets.append(region_data)
        
        # Sort by value
        top_metros = sorted(top_metros, key=lambda x: x["value"], reverse=True)[:5]
        top_tier2 = sorted(top_tier2, key=lambda x: x["value"], reverse=True)[:5]
        surprise_markets = sorted(surprise_markets, key=lambda x: x["value"], reverse=True)
        
        # Calculate northeast index
        northeast_values = [r["value"] for r in surprise_markets if r["tier"] == "northeast"]
        northeast_index = statistics.mean(northeast_values) if northeast_values else 0
        
        northeast_note = ""
        if northeast_index >= 70:
            northeast_note = "Northeast India shows exceptionally high interest — K-beauty influence likely driving this"
        elif northeast_index >= 50:
            northeast_note = "Northeast India shows above-average interest"
        
        return {
            "top_metros": top_metros,
            "top_tier2": top_tier2,
            "surprise_markets": surprise_markets[:5],
            "northeast_index": round(northeast_index, 1) if northeast_index > 0 else None,
            "northeast_note": northeast_note
        }
    
    async def fetch_shopping_data(self, query_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Fetch Google Shopping data for price range analysis"""
        query_text = query_info["query_text"]
        
        try:
            shopping_data = self.client.get_shopping_results(query_text)
            
            if shopping_data and "error" in shopping_data:
                return None
            
            products = shopping_data.get("shopping_results", [])
            if not products:
                return None
            
            # Extract prices and product details
            prices = []
            brands = {}
            top_products = []
            
            for product in products[:20]:  # Top 20 products
                price_str = product.get("price", "")
                price = None
                if price_str:
                    try:
                        price = int("".join(filter(str.isdigit, price_str)))
                        prices.append(price)
                    except:
                        pass
                
                # Extract brand from title or source
                title = product.get("title", "")
                source = product.get("source", "") or product.get("merchant", "")
                brand = self._extract_brand_from_title(title) or source
                
                if brand:
                    brands[brand] = brands.get(brand, 0) + 1
                
                # Collect top products
                if price:
                    top_products.append({
                        "title": title,
                        "price": price,
                        "source": source,
                        "rating": product.get("rating"),
                        "brand": brand
                    })
            
            if not prices:
                return None
            
            # Calculate price segments
            price_segments = {
                "under_300": len([p for p in prices if p < 300]),
                "300_to_600": len([p for p in prices if 300 <= p < 600]),
                "600_to_1000": len([p for p in prices if 600 <= p < 1000]),
                "above_1000": len([p for p in prices if p >= 1000])
            }
            
            # Sort top products by rating (if available) or price
            top_products_sorted = sorted(
                top_products,
                key=lambda x: (x.get("rating") or 0, -x.get("price", 0)),
                reverse=True
            )[:10]
            
            return {
                "query_text": query_text,
                "category": query_info.get("category"),
                "ingredient_tag": query_info.get("ingredient_tag"),
                "product_format": query_info.get("product_format"),
                "price_range": {
                    "min": min(prices),
                    "max": max(prices),
                    "median": statistics.median(prices),
                    "currency": "INR"
                },
                "total_results": len(products),
                "top_products": top_products_sorted,
                "brand_distribution": dict(sorted(brands.items(), key=lambda x: x[1], reverse=True)[:10]),
                "price_segments": price_segments,
                "fetched_at": datetime.utcnow()
            }
        except Exception as e:
            print(f"   ⚠️  Shopping data fetch error: {str(e)}")
            return None
    
    def _extract_brand_from_title(self, title: str) -> Optional[str]:
        """Extract brand name from product title"""
        if not title:
            return None
        
        # Known brands to look for
        known_brands = [
            "Minimalist", "The Derma Co", "Dot and Key", "Plum", "Mamaearth",
            "Garnier", "L'Oreal", "Neutrogena", "Cetaphil", "Himalaya",
            "Forest Essentials", "Kama Ayurveda", "Biotique", "WOW",
            "Lakme", "Pond's", "Nivea", "Simple", "Fixderma", "Re'equil"
        ]
        
        title_lower = title.lower()
        for brand in known_brands:
            if brand.lower() in title_lower:
                return brand
        
        # Try to extract first capitalized word (simple heuristic)
        words = title.split()
        for word in words[:3]:  # Check first 3 words
            if word and word[0].isupper() and len(word) > 3:
                # Skip common words
                if word.lower() not in ["the", "for", "with", "and", "best", "buy"]:
                    return word
        
        return None


async def store_trend_data(trend_data: Dict[str, Any]) -> bool:
    """Store trend data in MongoDB"""
    try:
        query_text = trend_data["query_text"]
        fetched_at = trend_data.get("fetched_at", datetime.utcnow())
        
        # Check if data exists for this query today (for resume functionality)
        start_of_day = fetched_at.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)
        
        existing = await market_trends_storage_col.find_one({
            "query_text": query_text,
            "fetch_source": "batch",
            "fetched_at": {
                "$gte": start_of_day,
                "$lt": end_of_day
            }
        })
        
        document = {
            **trend_data,
            "is_active": True
        }
        
        if existing:
            # Update existing (same day)
            await market_trends_storage_col.update_one(
                {"_id": existing["_id"]},
                {"$set": document}
            )
        else:
            # Insert new
            await market_trends_storage_col.insert_one(document)
        
        return True
    except Exception as e:
        print(f"   ❌ Storage error: {str(e)}")
        return False


async def get_auto_add_queries() -> List[str]:
    """Get queries from on-demand log that should be auto-added to batch"""
    try:
        # This would query the on_demand_log collection
        # For now, return empty list - implement when on_demand_log collection exists
        return []
    except:
        return []


async def compute_competitive_positions(config: Dict[str, Any]):
    """Post-process competitive positions for queries in comparison groups"""
    try:
        comparison_groups = config.get("query_generation_rules", {}).get("comparison_queries", {}).get("comparison_groups", {})
        
        for group_name, items in comparison_groups.items():
            # Find all queries in this comparison group
            group_queries = []
            cursor = market_trends_storage_col.find({
                "comparison_group": group_name,
                "fetch_source": "batch",
                "fetched_at": {
                    "$gte": datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                }
            })
            
            async for doc in cursor:
                if doc.get("current_score") is not None:
                    group_queries.append({
                        "query_text": doc.get("query_text"),
                        "current_score": doc.get("current_score", 0),
                        "_id": doc.get("_id")
                    })
            
            if len(group_queries) < 2:
                continue  # Need at least 2 for comparison
            
            # Sort by score
            group_queries.sort(key=lambda x: x["current_score"], reverse=True)
            group_avg = statistics.mean([q["current_score"] for q in group_queries])
            
            # Update each query with competitive position
            for rank, query_data in enumerate(group_queries, 1):
                current_score = query_data["current_score"]
                vs_avg = ((current_score - group_avg) / group_avg * 100) if group_avg > 0 else 0
                
                # Find nearest competitor
                nearest_competitor = None
                nearest_competitor_score = None
                gap = None
                
                if rank > 1:
                    nearest_competitor = group_queries[rank - 2]["query_text"]
                    nearest_competitor_score = group_queries[rank - 2]["current_score"]
                    gap = current_score - nearest_competitor_score
                elif rank < len(group_queries):
                    nearest_competitor = group_queries[rank]["query_text"]
                    nearest_competitor_score = group_queries[rank]["current_score"]
                    gap = current_score - nearest_competitor_score
                
                competitive_position = {
                    "comparison_group": group_name,
                    "rank_in_group": rank,
                    "total_in_group": len(group_queries),
                    "vs_group_average": f"{vs_avg:+.1f}%",
                    "nearest_competitor": nearest_competitor,
                    "nearest_competitor_score": nearest_competitor_score,
                    "gap": gap
                }
                
                # Update document
                await market_trends_storage_col.update_one(
                    {"_id": query_data["_id"]},
                    {"$set": {"competitive_position": competitive_position}}
                )
        
        print(f"✅ Computed competitive positions for comparison groups")
    except Exception as e:
        print(f"⚠️  Error computing competitive positions: {str(e)}")


async def get_already_processed_queries(today: datetime) -> Set[str]:
    """Get set of query texts that have already been processed today"""
    try:
        # Check for queries processed today (within last 24 hours)
        start_of_day = today.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)
        
        cursor = market_trends_storage_col.find({
            "fetch_source": "batch",
            "fetched_at": {
                "$gte": start_of_day,
                "$lt": end_of_day
            }
        }, {"query_text": 1})
        
        processed = set()
        async for doc in cursor:
            query_text = doc.get("query_text")
            if query_text:
                processed.add(query_text)
        
        return processed
    except Exception as e:
        print(f"⚠️  Error checking processed queries: {str(e)}")
        return set()


async def run_monthly_batch_fetch(skip_api_calls: bool = False):
    """Run the monthly batch fetch process"""
    global _batch_start_time
    _batch_start_time = datetime.now()
    
    print(f"\n{'='*80}")
    print(f"🔄 Monthly Market Trends Batch Fetch")
    print(f"{'='*80}")
    print(f"⏰ Started at: {_batch_start_time.isoformat()}")
    print(f"⏭️  API calls: {'DISABLED' if skip_api_calls else 'ENABLED'}")
    print(f"{'='*80}\n")
    
    # Load config
    try:
        config = load_config()
        print("✅ Config loaded successfully")
    except Exception as e:
        print(f"❌ Failed to load config: {str(e)}")
        return
    
    # Generate queries
    generator = BatchQueryGenerator(config)
    all_queries = generator.generate_all_queries()
    
    # Get auto-add queries from on-demand log
    auto_add_queries = await get_auto_add_queries()
    if auto_add_queries:
        print(f"📥 Adding {len(auto_add_queries)} queries from on-demand log...")
        # Convert auto-add queries to query info format
        for query_text in auto_add_queries:
            all_queries.append({
                "query_text": query_text,
                "query_level": "on_demand_auto_add",
                "category": None,
                "ingredient_tag": None,
                "product_format": None,
                "benefit_tag": None,
                "brand_tag": None,
                "comparison_group": None
            })
    
    print(f"\n📊 Total queries to process: {len(all_queries)}\n")
    
    if skip_api_calls:
        print("⏭️  Skipping API calls (dry run mode)")
        return
    
    # Check for already processed queries (resume functionality)
    today = datetime.utcnow()
    processed_queries = await get_already_processed_queries(today)
    
    if processed_queries:
        print(f"📋 Found {len(processed_queries)} queries already processed today")
        print(f"🔄 Resuming from where we left off...\n")
        
        # Filter out already processed queries
        remaining_queries = [
            q for q in all_queries 
            if q["query_text"] not in processed_queries
        ]
        
        print(f"📊 Remaining queries to process: {len(remaining_queries)} (skipped {len(all_queries) - len(remaining_queries)} already done)")
        all_queries = remaining_queries
        
        if not all_queries:
            print("✅ All queries already processed today!")
            return
    else:
        print("🆕 Starting fresh batch run\n")
    
    # Calculate time estimate
    rate_limit = config.get("batch_job_config", {}).get("rate_limit_per_second", 5)
    estimated_seconds = len(all_queries) / rate_limit
    estimated_minutes = estimated_seconds / 60
    print(f"⏱️  Estimated time: ~{estimated_minutes:.1f} minutes ({estimated_seconds:.0f} seconds)")
    print(f"   (Rate limit: {rate_limit} requests/second)\n")
    
    # Initialize fetcher
    fetcher = BatchTrendFetcher(config)
    
    # Process queries with rate limiting
    results = {
        "success": 0,
        "error": 0,
        "skipped": 0,
        "total": len(all_queries),
        "already_processed": len(processed_queries) if processed_queries else 0,
        "failed_queries": []  # Track failed queries
    }
    
    # Process in batches with rate limiting
    delay_between_requests = 1.0 / fetcher.rate_limit_per_second
    
    # Create progress bar
    pbar = tqdm(
        total=len(all_queries),
        desc="Fetching trends",
        unit="query",
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]"
    )
    
    start_time = datetime.now()
    
    for i, query_info in enumerate(all_queries, 1):
        query_text = query_info["query_text"]
        pbar.set_description(f"Processing: {query_text[:40]}...")
        
        try:
            # Fetch trends data
            trend_data = await fetcher.fetch_trends_data(query_info)
            
            if "error" in trend_data:
                error_msg = trend_data.get("error", "Unknown error")
                results["error"] += 1
                results["failed_queries"].append({
                    "query_text": query_text,
                    "query_level": query_info.get("query_level"),
                    "error": error_msg,
                    "attempted_at": datetime.now().isoformat()
                })
                pbar.set_postfix({"status": "error", "failed": len(results["failed_queries"])})
            else:
                # Store data
                stored = await store_trend_data(trend_data)
                if stored:
                    results["success"] += 1
                    pbar.set_postfix({"status": "success", "success": results["success"]})
                else:
                    results["error"] += 1
                    results["failed_queries"].append({
                        "query_text": query_text,
                        "query_level": query_info.get("query_level"),
                        "error": "Storage failed",
                        "attempted_at": datetime.now().isoformat()
                    })
                    pbar.set_postfix({"status": "storage_error", "failed": len(results["failed_queries"])})
            
            # Rate limiting
            if i < len(all_queries):
                await asyncio.sleep(delay_between_requests)
            
            # Fetch shopping data for top ingredient queries (every 10th query)
            if i % 10 == 0 and query_info.get("query_level") == "ingredient" and "error" not in trend_data:
                try:
                    shopping_data = await fetcher.fetch_shopping_data(query_info)
                    if shopping_data:
                        # Add shopping data to trend_data before storing
                        trend_data["shopping_data"] = shopping_data
                        # Update stored document with shopping data
                        await store_trend_data(trend_data)
                        
                        price_range = shopping_data.get("price_range", {})
                        pbar.write(f"   📦 Shopping: {shopping_data.get('total_results', 0)} products, "
                                  f"₹{price_range.get('min', 0)}-₹{price_range.get('max', 0)}")
                except Exception as e:
                    # Shopping data failure shouldn't fail the whole query
                    pass
        
        except Exception as e:
            results["error"] += 1
            results["failed_queries"].append({
                "query_text": query_text,
                "query_level": query_info.get("query_level"),
                "error": str(e),
                "attempted_at": datetime.now().isoformat()
            })
            pbar.set_postfix({"status": "exception", "failed": len(results["failed_queries"])})
        
        pbar.update(1)
    
    pbar.close()
    end_time = datetime.now()
    elapsed_time = (end_time - start_time).total_seconds()
    
    # Post-process competitive positions
    if results['success'] > 0:
        print(f"\n🔄 Computing competitive positions...")
        await compute_competitive_positions(config)
    
    # Summary
    print(f"\n{'='*80}")
    print(f"📊 Batch Fetch Summary")
    print(f"{'='*80}")
    print(f"✅ Success: {results['success']}")
    print(f"❌ Errors: {results['error']}")
    print(f"⏭️  Skipped: {results['skipped']}")
    if results.get('already_processed', 0) > 0:
        print(f"📋 Already processed (resumed): {results['already_processed']}")
    print(f"📊 Total processed this run: {results['total']}")
    
    # Timing information
    print(f"\n⏱️  Timing Information:")
    print(f"   Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Ended: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Total time: {elapsed_time/60:.2f} minutes ({elapsed_time:.0f} seconds)")
    if results['total'] > 0:
        avg_time_per_query = elapsed_time / results['total']
        print(f"   Average per query: {avg_time_per_query:.2f} seconds")
        print(f"   Effective rate: {results['total']/elapsed_time:.2f} queries/second")
    
    # Failed queries list
    if results['failed_queries']:
        print(f"\n❌ Failed Queries ({len(results['failed_queries'])}):")
        print(f"{'='*80}")
        
        # Group by error type
        error_groups = {}
        for failed in results['failed_queries']:
            error = failed.get('error', 'Unknown error')
            if error not in error_groups:
                error_groups[error] = []
            error_groups[error].append(failed)
        
        for error, queries in error_groups.items():
            print(f"\n   Error: {error[:80]}")
            print(f"   Count: {len(queries)}")
            print(f"   Queries:")
            for q in queries[:10]:  # Show first 10 of each error type
                print(f"      - {q['query_text']} ({q.get('query_level', 'unknown')})")
            if len(queries) > 10:
                print(f"      ... and {len(queries) - 10} more")
        
        # Save failed queries to file
        failed_file = project_root / "failed_queries.json"
        with open(failed_file, 'w', encoding='utf-8') as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "total_failed": len(results['failed_queries']),
                "failed_queries": results['failed_queries']
            }, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Failed queries saved to: {failed_file}")
    
    print(f"\n⏰ Completed at: {datetime.now().isoformat()}")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Monthly batch market trends fetcher")
    parser.add_argument(
        "--enable-api",
        action="store_true",
        help="Enable actual API calls (default: disabled for safety)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode - generate queries but don't fetch data"
    )
    
    args = parser.parse_args()
    skip_api_calls = not args.enable_api or args.dry_run
    
    asyncio.run(run_monthly_batch_fetch(skip_api_calls=skip_api_calls))
