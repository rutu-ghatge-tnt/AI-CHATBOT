"""
Market Trends Service for Make A Wish
=====================================

Fetches market trends from MongoDB (batch data) with SerpAPI fallback.
Provides formatted data ready for frontend visualization.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import statistics
from collections import defaultdict

from app.ai_ingredient_intelligence.db.collections import market_trends_storage_col
from app.ai_ingredient_intelligence.logic.market_trends_queries import (
    get_comprehensive_market_trends,
    normalize_ingredient_name,
    normalize_benefit,
    normalize_product_type
)
from app.ai_ingredient_intelligence.logic.trend_analyzer import TrendAnalyzer, SerpAPIClient


class MarketTrendsService:
    """Service for fetching and formatting market trends data"""
    
    def __init__(self):
        self.trend_analyzer = TrendAnalyzer()
        self.serpapi_client = SerpAPIClient()
    
    async def fetch_trends_for_wish(
        self,
        hero_ingredients: Optional[List[str]] = None,
        benefits: Optional[List[str]] = None,
        product_type: Optional[str] = None,
        category: str = "skincare",
        max_age_days: int = 35,
        use_fallback: bool = True
    ) -> Dict[str, Any]:
        """
        Main function to fetch market trends for Make A Wish.
        
        Strategy:
        1. Try MongoDB first (batch data)
        2. If missing, fallback to SerpAPI (if use_fallback=True)
        3. Store SerpAPI results in MongoDB for future use
        4. Format data for frontend visualization
        
        Args:
            hero_ingredients: List of ingredient names
            benefits: List of benefits
            product_type: Product format (serum, cream, etc.)
            category: "skincare" or "haircare"
            max_age_days: Max age of cached data (default: 35 days)
            use_fallback: Whether to use SerpAPI if MongoDB has no data
        
        Returns:
            Formatted trends data ready for frontend
        """
        hero_ingredients = hero_ingredients or []
        benefits = benefits or []
        
        # Step 1: Try MongoDB first
        mongo_data = await get_comprehensive_market_trends(
            hero_ingredients=hero_ingredients,
            benefits=benefits,
            product_type=product_type,
            category=category,
            max_age_days=max_age_days
        )
        
        # Check if we have sufficient data
        has_ingredient_data = bool(mongo_data.get("level_1_ingredient_trends"))
        has_benefit_data = bool(mongo_data.get("level_2_competing_approaches"))
        
        # Step 2: Fallback to SerpAPI if needed
        if use_fallback and (not has_ingredient_data or not has_benefit_data):
            fallback_data = await self._fetch_from_serpapi_fallback(
                hero_ingredients=hero_ingredients,
                benefits=benefits,
                product_type=product_type,
                category=category
            )
            
            # Merge fallback data with MongoDB data
            mongo_data = self._merge_trends_data(mongo_data, fallback_data)
        
        # Step 3: Format for frontend
        formatted_data = self._format_for_frontend(
            mongo_data,
            hero_ingredients=hero_ingredients,
            benefits=benefits,
            product_type=product_type,
            category=category
        )
        
        return formatted_data
    
    async def _fetch_from_serpapi_fallback(
        self,
        hero_ingredients: List[str],
        benefits: List[str],
        product_type: Optional[str],
        category: str
    ) -> Dict[str, Any]:
        """Fetch missing data from SerpAPI and store in MongoDB"""
        fallback_data = {
            "level_1_ingredient_trends": {},
            "level_2_competing_approaches": [],
            "shopping_data": None,
            "fetched_from": "serpapi"
        }
        
        # Check if SerpAPI is available
        if not self.serpapi_client.api_key:
            print("⚠️ SerpAPI key not available, skipping fallback")
            return fallback_data
        
        # Fetch ingredient trends
        for ingredient in hero_ingredients[:3]:  # Limit to 3 to avoid rate limits
            try:
                # Build query
                if product_type:
                    query = f"{ingredient} {product_type}"
                else:
                    query = f"{ingredient} {category}"
                
                # Fetch trends
                trends_data = self.serpapi_client.get_trends_timeseries(
                    query=query,
                    time_range="today 12-m",
                    geo="IN"
                )
                
                # Fetch related queries
                related_data = self.serpapi_client.get_trends_related_queries(
                    query=query,
                    time_range="today 12-m",
                    geo="IN"
                )
                
                # Fetch regional data
                regional_data = self.serpapi_client.get_trends_regional(
                    query=query,
                    time_range="today 12-m",
                    geo="IN"
                )
                
                # Process and store in MongoDB
                processed_doc = await self._process_and_store_serpapi_data(
                    query_text=query,
                    ingredient=ingredient,
                    product_type=product_type,
                    category=category,
                    trends_data=trends_data,
                    related_data=related_data,
                    regional_data=regional_data
                )
                
                if processed_doc:
                    fallback_data["level_1_ingredient_trends"][ingredient] = {
                        "trend_data": processed_doc,
                        "query_text": query,
                        "match_type": "serpapi_fallback",
                        "confidence": "medium"
                    }
            
            except Exception as e:
                print(f"⚠️ Error fetching SerpAPI data for {ingredient}: {e}")
                continue
        
        # Fetch benefit trends if needed
        if benefits:
            for benefit in benefits[:2]:  # Limit to 2
                try:
                    if product_type:
                        query = f"{benefit} {product_type}"
                    else:
                        query = f"{benefit} {category}"
                    
                    trends_data = self.serpapi_client.get_trends_timeseries(
                        query=query,
                        time_range="today 12-m",
                        geo="IN"
                    )
                    
                    # Process benefit data
                    processed_doc = await self._process_and_store_serpapi_data(
                        query_text=query,
                        ingredient=None,
                        product_type=product_type,
                        category=category,
                        benefit=benefit,
                        trends_data=trends_data,
                        related_data={},
                        regional_data={}
                    )
                    
                    if processed_doc:
                        fallback_data["level_2_competing_approaches"].append(processed_doc)
                
                except Exception as e:
                    print(f"⚠️ Error fetching SerpAPI data for benefit {benefit}: {e}")
                    continue
        
        return fallback_data
    
    async def _process_and_store_serpapi_data(
        self,
        query_text: str,
        ingredient: Optional[str],
        product_type: Optional[str],
        category: str,
        trends_data: Dict[str, Any],
        related_data: Dict[str, Any],
        regional_data: Dict[str, Any],
        benefit: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Process SerpAPI response and store in MongoDB"""
        try:
            # Extract timeline data
            interest_over_time = trends_data.get("interest_over_time", {})
            timeline_data = interest_over_time.get("timeline_data", [])
            
            if not timeline_data:
                return None
            
            # Process values
            values = []
            dates = []
            for point in timeline_data:
                if point.get("values"):
                    val = point["values"][0].get("extracted_value", 0)
                    if val is not None:
                        values.append(val)
                        dates.append(point.get("date", ""))
            
            if len(values) < 4:
                return None
            
            # Calculate metrics
            current_score = values[-1] if values else 0
            peak_score = max(values) if values else 0
            peak_idx = values.index(peak_score) if peak_score in values else -1
            peak_month = dates[peak_idx] if peak_idx >= 0 and peak_idx < len(dates) else ""
            
            # Calculate growth rates
            growth_3m = 0
            growth_6m = 0
            if len(values) >= 12:
                current_3mo = statistics.mean(values[-12:])
                previous_3mo = statistics.mean(values[-24:-12]) if len(values) >= 24 else statistics.mean(values[:12])
                growth_6m = ((current_3mo - previous_3mo) / previous_3mo * 100) if previous_3mo > 0 else 0
            
            if len(values) >= 4:
                current_1mo = statistics.mean(values[-4:])
                previous_1mo = statistics.mean(values[-8:-4]) if len(values) >= 8 else statistics.mean(values[:4])
                growth_3m = ((current_1mo - previous_1mo) / previous_1mo * 100) if previous_1mo > 0 else 0
            
            # Determine trend direction
            if growth_6m > 20:
                trend_direction = "rising"
            elif growth_6m > -20:
                trend_direction = "stable"
            else:
                trend_direction = "declining"
            
            # Process related queries
            related_queries_rising = []
            related_queries_top = []
            
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
            interest_by_region = regional_data.get("interest_by_region", [])
            for region in interest_by_region[:20]:
                regional_interest.append({
                    "location": region.get("location", ""),
                    "value": region.get("value", ""),
                    "extracted_value": region.get("extracted_value", 0) or region.get("value", 0)
                })
            
            # Build document
            doc = {
                "query_text": query_text,
                "query_level": "ingredient" if ingredient else "benefit",
                "category": category,
                "ingredient_tag": normalize_ingredient_name(ingredient) if ingredient else None,
                "product_format": normalize_product_type(product_type) if product_type else None,
                "benefit_tag": normalize_benefit(benefit) if benefit else None,
                "brand_tag": None,
                "comparison_group": None,
                "interest_over_time": {
                    "timeline_data": timeline_data,
                    "values": values,
                    "dates": dates
                },
                "related_queries_rising": related_queries_rising,
                "related_queries_top": related_queries_top,
                "regional_interest": regional_interest,
                "current_score": current_score,
                "peak_score": peak_score,
                "peak_month": peak_month,
                "growth_pct_3m": round(growth_3m, 2),
                "growth_pct_6m": round(growth_6m, 2),
                "growth_pct_12m": 0,
                "trend_direction": trend_direction,
                "seasonality": {},
                "rising_query_insights": {},
                "regional_insights": {},
                "competitive_position": {},
                "shopping_data": None,
                "fetched_at": datetime.utcnow(),
                "fetch_source": "serpapi_fallback",
                "is_active": True
            }
            
            # Store in MongoDB
            await market_trends_storage_col.insert_one(doc)
            
            return doc
        
        except Exception as e:
            print(f"⚠️ Error processing SerpAPI data: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _merge_trends_data(
        self,
        mongo_data: Dict[str, Any],
        fallback_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Merge MongoDB data with SerpAPI fallback data"""
        # Merge ingredient trends
        if fallback_data.get("level_1_ingredient_trends"):
            mongo_data["level_1_ingredient_trends"].update(
                fallback_data["level_1_ingredient_trends"]
            )
        
        # Merge competing approaches
        if fallback_data.get("level_2_competing_approaches"):
            mongo_data["level_2_competing_approaches"].extend(
                fallback_data["level_2_competing_approaches"]
            )
        
        # Merge shopping data
        if fallback_data.get("shopping_data") and not mongo_data.get("shopping_data"):
            mongo_data["shopping_data"] = fallback_data["shopping_data"]
        
        return mongo_data
    
    def _format_for_frontend(
        self,
        trends_data: Dict[str, Any],
        hero_ingredients: List[str],
        benefits: List[str],
        product_type: Optional[str],
        category: str
    ) -> Dict[str, Any]:
        """
        Format trends data for frontend visualization.
        
        Returns structured data ready for charts, graphs, and cards.
        """
        formatted = {
            "summary": {
                "total_ingredients_analyzed": len(hero_ingredients),
                "total_benefits_analyzed": len(benefits),
                "data_source": "mongodb" if trends_data.get("fetched_from") != "serpapi" else "mixed",
                "last_updated": datetime.utcnow().isoformat()
            },
            "ingredient_trends": [],
            "benefit_trends": [],
            "competitive_landscape": [],
            "regional_insights": {},
            "shopping_insights": None,
            "key_insights": []
        }
        
        # Format ingredient trends
        level_1 = trends_data.get("level_1_ingredient_trends", {})
        for ingredient_name, ingredient_data in level_1.items():
            if not ingredient_data or not ingredient_data.get("trend_data"):
                continue
            
            trend_doc = ingredient_data["trend_data"]
            
            # Extract timeseries for line chart
            interest_over_time = trend_doc.get("interest_over_time", {})
            timeline_data = interest_over_time.get("timeline_data", [])
            
            chart_data = []
            for point in timeline_data:
                if point.get("values"):
                    val = point["values"][0].get("extracted_value", 0)
                    chart_data.append({
                        "date": point.get("date", ""),
                        "timestamp": point.get("timestamp", ""),
                        "value": val
                    })
            
            # Format related queries
            rising_queries = trend_doc.get("related_queries_rising", [])[:5]
            top_queries = trend_doc.get("related_queries_top", [])[:5]
            
            # Format regional data
            regional_data = trend_doc.get("regional_interest", [])[:10]
            
            ingredient_trend = {
                "ingredient_name": ingredient_name,
                "query_text": ingredient_data.get("query_text", ""),
                "match_confidence": ingredient_data.get("confidence", "medium"),
                "current_score": trend_doc.get("current_score", 0),
                "peak_score": trend_doc.get("peak_score", 0),
                "peak_month": trend_doc.get("peak_month", ""),
                "growth_3m": trend_doc.get("growth_pct_3m", 0),
                "growth_6m": trend_doc.get("growth_pct_6m", 0),
                "trend_direction": trend_doc.get("trend_direction", "stable"),
                "timeseries_chart": chart_data,
                "rising_queries": rising_queries,
                "top_queries": top_queries,
                "regional_distribution": regional_data,
                "seasonality": trend_doc.get("seasonality", {}),
                "insights": {
                    "trend_classification": self._classify_trend(trend_doc),
                    "market_opportunity": self._assess_market_opportunity(trend_doc),
                    "competitive_position": trend_doc.get("competitive_position", {})
                }
            }
            
            formatted["ingredient_trends"].append(ingredient_trend)
        
        # Format benefit trends (competing approaches)
        level_2 = trends_data.get("level_2_competing_approaches", [])
        for benefit_doc in level_2[:5]:  # Top 5
            benefit_trend = {
                "benefit": benefit_doc.get("benefit_tag", ""),
                "query_text": benefit_doc.get("query_text", ""),
                "current_score": benefit_doc.get("current_score", 0),
                "trend_direction": benefit_doc.get("trend_direction", "stable"),
                "growth_6m": benefit_doc.get("growth_pct_6m", 0),
                "alternative_ingredients": self._extract_alternative_ingredients(benefit_doc)
            }
            formatted["benefit_trends"].append(benefit_trend)
        
        # Format competitive landscape
        level_3 = trends_data.get("level_3_brand_trends", [])
        for brand_doc in level_3[:5]:
            competitive_item = {
                "brand": brand_doc.get("brand_tag", ""),
                "query_text": brand_doc.get("query_text", ""),
                "current_score": brand_doc.get("current_score", 0),
                "trend_direction": brand_doc.get("trend_direction", "stable")
            }
            formatted["competitive_landscape"].append(competitive_item)
        
        # Aggregate regional insights
        if formatted["ingredient_trends"]:
            first_ingredient = formatted["ingredient_trends"][0]
            formatted["regional_insights"] = {
                "top_regions": first_ingredient.get("regional_distribution", [])[:5],
                "surprise_markets": self._identify_surprise_markets(first_ingredient.get("regional_distribution", []))
            }
        
        # Shopping insights
        shopping_data = trends_data.get("shopping_data")
        if shopping_data:
            formatted["shopping_insights"] = {
                "price_range": shopping_data.get("price_range", {}),
                "average_price": shopping_data.get("average_price", 0),
                "product_count": shopping_data.get("products_found", 0)
            }
        
        # Generate key insights
        formatted["key_insights"] = self._generate_key_insights(formatted)
        
        return formatted
    
    def _classify_trend(self, trend_doc: Dict[str, Any]) -> Dict[str, Any]:
        """Classify trend trajectory"""
        growth_6m = trend_doc.get("growth_pct_6m", 0)
        current_score = trend_doc.get("current_score", 0)
        trend_direction = trend_doc.get("trend_direction", "stable")
        
        if growth_6m > 50:
            classification = "explosive_growth"
            icon = "🚀"
            description = "Rapidly growing trend with strong momentum"
        elif growth_6m > 20:
            classification = "steady_rise"
            icon = "📈"
            description = "Consistent upward trajectory"
        elif growth_6m > -20:
            classification = "stable"
            icon = "➡️"
            description = "Stable market with consistent interest"
        else:
            classification = "declining"
            icon = "📉"
            description = "Declining interest, consider alternatives"
        
        return {
            "classification": classification,
            "icon": icon,
            "description": description,
            "growth_rate": growth_6m,
            "current_interest": current_score
        }
    
    def _assess_market_opportunity(self, trend_doc: Dict[str, Any]) -> Dict[str, Any]:
        """Assess market opportunity"""
        current_score = trend_doc.get("current_score", 0)
        growth_6m = trend_doc.get("growth_pct_6m", 0)
        peak_score = trend_doc.get("peak_score", 0)
        
        # Calculate opportunity score (0-100)
        opportunity_score = (current_score * 0.4) + (min(growth_6m, 100) * 0.3) + (min(peak_score, 100) * 0.3)
        
        if opportunity_score >= 70:
            opportunity = "high"
            recommendation = "Strong market opportunity - high interest and growth"
        elif opportunity_score >= 50:
            opportunity = "medium"
            recommendation = "Moderate opportunity - consider market positioning"
        else:
            opportunity = "low"
            recommendation = "Limited opportunity - explore alternative approaches"
        
        return {
            "opportunity_score": round(opportunity_score, 1),
            "opportunity_level": opportunity,
            "recommendation": recommendation
        }
    
    def _extract_alternative_ingredients(self, benefit_doc: Dict[str, Any]) -> List[str]:
        """Extract alternative ingredients from benefit trend"""
        # Look at related queries to find alternative ingredients
        related_queries = benefit_doc.get("related_queries_top", [])
        alternatives = []
        
        for query_item in related_queries[:5]:
            query_text = query_item.get("query", "")
            # Simple extraction - look for ingredient-like terms
            # This is a simplified version - could be enhanced with NLP
            alternatives.append(query_text)
        
        return alternatives
    
    def _identify_surprise_markets(self, regional_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Identify surprise markets (unexpectedly high interest)"""
        # Sort by interest value
        sorted_regions = sorted(regional_data, key=lambda x: x.get("extracted_value", 0), reverse=True)
        
        # Identify regions with high interest but not typically major markets
        surprise_markets = []
        tier2_tier3_states = ["Manipur", "Meghalaya", "Nagaland", "Tripura", "Mizoram", 
                             "Arunachal Pradesh", "Sikkim", "Chhattisgarh", "Jharkhand"]
        
        for region in sorted_regions[:10]:
            location = region.get("location", "")
            value = region.get("extracted_value", 0)
            
            if location in tier2_tier3_states and value >= 60:
                surprise_markets.append({
                    "location": location,
                    "interest": value,
                    "insight": f"Unexpectedly high interest in {location}"
                })
        
        return surprise_markets[:3]
    
    def _generate_key_insights(self, formatted_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate key insights from all trend data"""
        insights = []
        
        # Ingredient insights
        if formatted_data.get("ingredient_trends"):
            best_ingredient = max(
                formatted_data["ingredient_trends"],
                key=lambda x: x.get("growth_6m", 0)
            )
            
            insights.append({
                "type": "best_performer",
                "title": f"{best_ingredient['ingredient_name']} shows strongest growth",
                "description": f"{best_ingredient['ingredient_name']} has {best_ingredient['growth_6m']:.1f}% growth over 6 months",
                "icon": "⭐",
                "priority": "high"
            })
        
        # Regional insights
        if formatted_data.get("regional_insights", {}).get("surprise_markets"):
            surprise = formatted_data["regional_insights"]["surprise_markets"][0]
            insights.append({
                "type": "regional_opportunity",
                "title": f"High interest in {surprise['location']}",
                "description": surprise["insight"],
                "icon": "📍",
                "priority": "medium"
            })
        
        # Trend direction insights
        if formatted_data.get("ingredient_trends"):
            rising_count = sum(1 for ing in formatted_data["ingredient_trends"] 
                            if ing.get("trend_direction") == "rising")
            
            if rising_count > 0:
                insights.append({
                    "type": "market_momentum",
                    "title": f"{rising_count} ingredient(s) showing rising trends",
                    "description": "Market is showing positive momentum",
                    "icon": "📊",
                    "priority": "high"
                })
        
        return insights[:5]  # Top 5 insights

