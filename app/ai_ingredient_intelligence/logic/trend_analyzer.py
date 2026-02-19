"""
Trend Insights Module - SerpAPI Integration
===========================================

Real-time market intelligence using SerpAPI Google Trends, Google Search, and Google Shopping APIs.
"""

import os
import json
import statistics
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from serpapi.google_search import GoogleSearch

# Caching disabled - always fetch fresh data
# from app.ai_ingredient_intelligence.utils.trend_cache import TrendCache

# SerpAPI key (different from Serper)
SERPAPI_KEY = os.getenv("SERPAPI_KEY")


class SerpAPIClient:
    """Wrapper for SerpAPI Google Trends, Search, and Shopping APIs"""
    
    def __init__(self):
        if not SERPAPI_KEY:
            self.api_key = None
            print("Warning: SERPAPI_KEY not set. Trend analysis will not work.")
        else:
            self.api_key = SERPAPI_KEY
    
    def _check_api_key(self):
        """Check if API key is available"""
        if not self.api_key:
            raise ValueError("SERPAPI_KEY environment variable not set. Please configure it in your .env file.")
    
    def get_trends_timeseries(
        self, 
        query: str, 
        time_range: str = "today 12-m", 
        geo: str = "IN",
        hl: str = "en",
        tz: int = -330  # IST offset in minutes (UTC+5:30 = -330)
    ) -> Dict:
        """Get interest over time data"""
        self._check_api_key()
        params = {
            "engine": "google_trends",
            "q": query,
            "data_type": "TIMESERIES",
            "date": time_range,
            "geo": geo,
            "hl": hl,
            "tz": str(tz),
            "api_key": self.api_key
        }
        search = GoogleSearch(params)
        return search.get_dict()
    
    def get_trends_regional(
        self,
        query: str,
        time_range: str = "today 12-m",
        geo: str = "IN",
        hl: str = "en",
        tz: int = -330
    ) -> Dict:
        """Get interest by region data (GEO_MAP_0)"""
        self._check_api_key()
        params = {
            "engine": "google_trends",
            "q": query,
            "data_type": "GEO_MAP_0",
            "date": time_range,
            "geo": geo,
            "hl": hl,
            "tz": str(tz),
            "api_key": self.api_key
        }
        search = GoogleSearch(params)
        return search.get_dict()
    
    def get_trends_related_queries(
        self,
        query: str,
        time_range: str = "today 12-m",
        geo: str = "IN",
        hl: str = "en",
        tz: int = -330
    ) -> Dict:
        """Get related queries (rising and top)"""
        self._check_api_key()
        params = {
            "engine": "google_trends",
            "q": query,
            "data_type": "RELATED_QUERIES",
            "date": time_range,
            "geo": geo,
            "hl": hl,
            "tz": str(tz),
            "api_key": self.api_key
        }
        search = GoogleSearch(params)
        return search.get_dict()
    
    def get_trends_related_topics(
        self,
        query: str,
        time_range: str = "today 12-m",
        geo: str = "IN",
        hl: str = "en",
        tz: int = -330
    ) -> Dict:
        """Get related topics (rising and top)"""
        self._check_api_key()
        params = {
            "engine": "google_trends",
            "q": query,
            "data_type": "RELATED_TOPICS",
            "date": time_range,
            "geo": geo,
            "hl": hl,
            "tz": str(tz),
            "api_key": self.api_key
        }
        search = GoogleSearch(params)
        return search.get_dict()
    
    def get_people_also_ask(
        self,
        query: str,
        location: str = "India",
        google_domain: str = "google.co.in",
        gl: str = "in",
        hl: str = "en"
    ) -> Dict:
        """Get People Also Ask questions from Google Search"""
        self._check_api_key()
        params = {
            "engine": "google",
            "q": query,
            "location": location,
            "google_domain": google_domain,
            "gl": gl,
            "hl": hl,
            "api_key": self.api_key
        }
        search = GoogleSearch(params)
        return search.get_dict()
    
    def get_shopping_results(
        self,
        query: str,
        location: str = "India",
        google_domain: str = "google.co.in",
        gl: str = "in",
        hl: str = "en",
        price_min: Optional[int] = None,
        price_max: Optional[int] = None
    ) -> Dict:
        """Get Google Shopping results"""
        self._check_api_key()
        params = {
            "engine": "google_shopping",
            "q": query,
            "location": location,
            "google_domain": google_domain,
            "gl": gl,
            "hl": hl,
            "api_key": self.api_key
        }
        if price_min:
            params["price_min"] = price_min
        if price_max:
            params["price_max"] = price_max
        search = GoogleSearch(params)
        return search.get_dict()
    
    def compare_trends(
        self,
        queries: List[str],  # Max 5 queries
        time_range: str = "today 12-m",
        geo: str = "IN",
        hl: str = "en",
        tz: int = -330
    ) -> Dict:
        """Compare multiple queries (up to 5)"""
        self._check_api_key()
        if len(queries) > 5:
            queries = queries[:5]
        
        params = {
            "engine": "google_trends",
            "q": ",".join(queries),
            "data_type": "TIMESERIES",
            "date": time_range,
            "geo": geo,
            "hl": hl,
            "tz": str(tz),
            "api_key": self.api_key
        }
        search = GoogleSearch(params)
        return search.get_dict()


class TrendAnalyzer:
    """Main trend analysis engine"""
    
    def __init__(self):
        self.client = SerpAPIClient()
        # Caching disabled - always fetch fresh data
        # self.cache = TrendCache()
    
    async def analyze_ingredient_trend(
        self,
        ingredient: str,
        time_range: str = "today 12-m",
        compare_with: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Analyze trend for a single ingredient
        
        Returns trend classification, growth rates, and related queries
        """
        # Normalize ingredient name for consistent caching (lowercase, strip whitespace)
        ingredient_normalized = ingredient.lower().strip()
        
        # Build search queries for skincare context
        queries = [f"{ingredient} serum", f"{ingredient} for skin", f"{ingredient} benefits"]
        main_query = queries[0]
        
        # DISABLED CACHING - Always fetch fresh data
        # cache_key_params = {
        #     "ingredient": ingredient_normalized,
        #     "time_range": time_range,
        #     "query": main_query.lower()
        # }
        # trends_data = await self.cache.get("trends_timeseries", **cache_key_params)
        
        trends_data = None  # Force fresh fetch
        print(f"🔄 Fetching fresh data for ingredient: {ingredient_normalized} (query: {main_query}) - caching disabled")
        
        try:
            trends_data = self.client.get_trends_timeseries(main_query, time_range)
            # Check for API errors in response
            if trends_data and "error" in trends_data:
                error_msg = trends_data.get("error", "Unknown API error")
                return {"error": f"SerpAPI error: {error_msg}"}
            # CACHING DISABLED - Don't cache
            # await self.cache.set("trends_timeseries", trends_data, **cache_key_params)
            print(f"✅ Fetched fresh trend data for ingredient: {ingredient_normalized}")
        except Exception as e:
            print(f"❌ Error fetching trends data: {str(e)}")
            import traceback
            traceback.print_exc()
            return {"error": f"Failed to fetch trends data: {str(e)}"}
        
        # Check if trends_data is valid
        if not trends_data:
            return {"error": "No trends data received from API"}
        
        # Check for API errors in cached data
        if "error" in trends_data:
            error_msg = trends_data.get("error", "Unknown API error")
            return {"error": f"SerpAPI error: {error_msg}"}
        
        # Get related queries (CACHING DISABLED)
        related_data = None
        try:
            related_data = self.client.get_trends_related_queries(main_query, time_range)
            # Don't use if there's an error
            if related_data and "error" in related_data:
                related_data = {}
            # CACHING DISABLED
            # await self.cache.set("trends_related", related_data, **cache_key_params)
            print(f"✅ Fetched fresh related queries for ingredient: {ingredient_normalized}")
        except Exception as e:
            print(f"⚠️ Error fetching related queries: {str(e)}")
            related_data = {}
        
        # Process interest over time
        interest_over_time = trends_data.get("interest_over_time")
        if not interest_over_time:
            # Try alternative queries if main query fails
            for alt_query in queries[1:]:  # Try remaining queries
                try:
                    # CACHING DISABLED - Always fetch fresh
                    alt_trends_data = self.client.get_trends_timeseries(alt_query, time_range)
                    if alt_trends_data and "error" not in alt_trends_data:
                        print(f"✅ Fetched alternative query data for ingredient: {ingredient_normalized}")
                    
                    if alt_trends_data and "error" not in alt_trends_data:
                        interest_over_time = alt_trends_data.get("interest_over_time")
                        if interest_over_time:
                            trends_data = alt_trends_data
                            main_query = alt_query  # Update main query for related queries
                            break
                except Exception:
                    continue
            
            if not interest_over_time:
                return {"error": "No timeline data available. The ingredient may have insufficient search volume in Google Trends, or the API may be temporarily unavailable. Try a more common ingredient name or check back later."}
        
        timeline = interest_over_time.get("timeline_data", [])
        if not timeline:
            return {"error": "No timeline data available. The ingredient may have insufficient search volume in Google Trends, or the API may be temporarily unavailable. Try a more common ingredient name or check back later."}
        
        values = []
        dates = []
        for point in timeline:
            if point.get("values"):
                val = point["values"][0].get("extracted_value", 0)
                if val is not None:
                    values.append(val)
                    dates.append(point.get("date", ""))
        
        if len(values) < 4:
            return {"error": "Insufficient data points for analysis"}
        
        # Calculate growth rates
        current_interest = values[-1] if values else 0
        peak_interest = max(values) if values else 0
        avg_interest = statistics.mean(values) if values else 0
        lowest_interest = min(values) if values else 0
        
        # Calculate 3-month and 6-month growth
        growth_3mo = 0
        growth_6mo = 0
        growth_12mo = 0
        
        if len(values) >= 12:  # At least 12 weeks (3 months)
            current_3mo = statistics.mean(values[-12:])  # Last 3 months
            previous_3mo = statistics.mean(values[-24:-12]) if len(values) >= 24 else statistics.mean(values[:12])
            growth_6mo = ((current_3mo - previous_3mo) / previous_3mo * 100) if previous_3mo > 0 else 0
        
        if len(values) >= 4:  # At least 4 weeks
            current_1mo = statistics.mean(values[-4:])  # Last month
            previous_1mo = statistics.mean(values[-8:-4]) if len(values) >= 8 else statistics.mean(values[:4])
            growth_3mo = ((current_1mo - previous_1mo) / previous_1mo * 100) if previous_1mo > 0 else 0
        
        if len(values) >= 48:  # At least 48 weeks (12 months)
            current_12mo = statistics.mean(values[-48:])
            previous_12mo = statistics.mean(values[-96:-48]) if len(values) >= 96 else statistics.mean(values[:48])
            growth_12mo = ((current_12mo - previous_12mo) / previous_12mo * 100) if previous_12mo > 0 else 0
        
        # Calculate volatility (standard deviation as % of mean)
        volatility_pct = (statistics.stdev(values) / avg_interest * 100) if avg_interest > 0 else 0
        volatility = "high" if volatility_pct > 20 else "medium" if volatility_pct > 10 else "low"
        
        # Classify trajectory
        if growth_6mo > 50:
            trajectory = "explosive_growth"
            trajectory_icon = "🚀"
        elif growth_6mo > 20:
            trajectory = "steady_rise"
            trajectory_icon = "📈"
        elif growth_6mo > -20:
            trajectory = "stable"
            trajectory_icon = "➡️"
        else:
            trajectory = "declining"
            trajectory_icon = "📉"
        
        # Process related queries
        rising_queries = []
        top_queries = []
        
        related_queries = related_data.get("related_queries", {})
        for item in related_queries.get("rising", [])[:10]:
            rising_queries.append({
                "query": item.get("query", ""),
                "growth": item.get("value", ""),
                "extracted_value": item.get("extracted_value", 0)
            })
        
        for item in related_queries.get("top", [])[:10]:
            top_queries.append({
                "query": item.get("query", ""),
                "volume": item.get("value", ""),
                "extracted_value": item.get("extracted_value", 0)
            })
        
        # Find peak and lowest dates
        peak_idx = values.index(peak_interest) if peak_interest in values else -1
        lowest_idx = values.index(lowest_interest) if lowest_interest in values else -1
        peak_date = dates[peak_idx] if peak_idx >= 0 and peak_idx < len(dates) else ""
        lowest_date = dates[lowest_idx] if lowest_idx >= 0 and lowest_idx < len(dates) else ""
        
        return {
            "ingredient": ingredient,  # Return original ingredient name (not normalized)
            "analysis_period": f"{dates[0] if dates else 'N/A'} - {dates[-1] if dates else 'N/A'}",
            "data_points": len(values),
            "trend_classification": {
                "trajectory": trajectory,
                "trajectory_icon": trajectory_icon,
                "confidence": "high" if len(values) >= 24 else "medium",
                "growth_rate_3mo": round(growth_3mo, 2),
                "growth_rate_6mo": round(growth_6mo, 2),
                "growth_rate_12mo": round(growth_12mo, 2),
                "volatility": volatility,
                "volatility_pct": round(volatility_pct, 2)
            },
            "interest_metrics": {
                "current_interest": current_interest,
                "peak_interest": peak_interest,
                "peak_date": peak_date,
                "average_interest": round(avg_interest, 2),
                "lowest_interest": lowest_interest,
                "lowest_date": lowest_date
            },
            "related_queries": {
                "rising": rising_queries,
                "top": top_queries
            }
        }
    
    async def analyze_consumer_intent(
        self,
        ingredient: str,
        concerns: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Analyze consumer intent from People Also Ask questions"""
        # Normalize ingredient name for consistent caching
        ingredient_normalized = ingredient.lower().strip()
        
        queries = [
            f"{ingredient} serum",
            f"{ingredient} for skin",
            f"best {ingredient} products",
            f"{ingredient} benefits"
        ]
        
        if concerns:
            queries.extend([f"{ingredient} for {c}" for c in concerns[:3]])  # Limit to 3 concerns
        
        all_paa = []
        for query in queries:
            # CACHING DISABLED - Always fetch fresh
            try:
                paa_data = self.client.get_people_also_ask(query)
                if paa_data and "error" not in paa_data:
                    print(f"✅ Fetched fresh PAA data for query: {query}")
                elif paa_data and "error" in paa_data:
                    print(f"⚠️ PAA API error for query {query}: {paa_data.get('error')}")
                    continue
            except Exception as e:
                print(f"⚠️ Error fetching PAA for query {query}: {str(e)}")
                continue
            
            paa_list = paa_data.get("people_also_ask", [])
            for item in paa_list:
                question = item.get("question", "")
                if question and question not in [q["question"] for q in all_paa]:
                    all_paa.append({
                        "question": question,
                        "snippet": item.get("snippet", ""),
                        "title": item.get("title", "")
                    })
        
        # Classify questions by intent
        efficacy_q = []
        safety_q = []
        usage_q = []
        purchase_q = []
        comparison_q = []
        
        for q in all_paa:
            q_lower = q["question"].lower()
            if any(word in q_lower for word in ["work", "effective", "results", "help", "benefits"]):
                efficacy_q.append(q)
            elif any(word in q_lower for word in ["safe", "side effects", "pregnancy", "sensitive", "harmful"]):
                safety_q.append(q)
            elif any(word in q_lower for word in ["use", "how to", "when", "with", "apply"]):
                usage_q.append(q)
            elif any(word in q_lower for word in ["best", "price", "buy", "where", "purchase"]):
                purchase_q.append(q)
            elif any(word in q_lower for word in ["vs", "versus", "difference", "compare", "better"]):
                comparison_q.append(q)
        
        return {
            "ingredient": ingredient,
            "queries_analyzed": len(queries),
            "total_paa_questions": len(all_paa),
            "unique_questions": len(all_paa),
            "intent_breakdown": {
                "efficacy_questions": efficacy_q[:10],
                "safety_questions": safety_q[:10],
                "usage_questions": usage_q[:10],
                "purchase_questions": purchase_q[:10],
                "comparison_questions": comparison_q[:10]
            }
        }
    
    async def analyze_competitive_landscape(
        self,
        category: str,
        price_min: Optional[int] = None,
        price_max: Optional[int] = None
    ) -> Dict[str, Any]:
        """Analyze competitive landscape from Google Shopping"""
        # Normalize category for consistent caching
        category_normalized = category.lower().strip()
        cache_key_params = {
            "category": category_normalized,
            "price_min": price_min,
            "price_max": price_max
        }
        # CACHING DISABLED - Always fetch fresh
        shopping_data = None
        print(f"🔄 Fetching fresh competitive landscape data for: {category_normalized}")
        try:
            shopping_data = self.client.get_shopping_results(
                category,
                price_min=price_min,
                price_max=price_max
            )
            if shopping_data and "error" not in shopping_data:
                print(f"✅ Fetched fresh shopping data for: {category_normalized}")
            elif shopping_data and "error" in shopping_data:
                error_msg = shopping_data.get("error", "Unknown error")
                return {"error": f"SerpAPI error: {error_msg}"}
        except Exception as e:
            print(f"❌ Error fetching shopping data: {str(e)}")
            return {"error": f"Failed to fetch shopping data: {str(e)}"}
        
        # Check if shopping_data is valid
        if not shopping_data:
            return {"error": "No shopping data received from API"}
        
        products = shopping_data.get("shopping_results", [])
        
        # Analyze price distribution
        prices = []
        brands = {}
        ratings = []
        
        for product in products:
            price_str = product.get("price", "")
            if price_str:
                try:
                    # Extract numeric value from price string (e.g., "₹499" -> 499)
                    price = int("".join(filter(str.isdigit, price_str)))
                    prices.append(price)
                except:
                    pass
            
            brand = product.get("source", "") or product.get("merchant", "")
            if brand:
                brands[brand] = brands.get(brand, 0) + 1
            
            rating = product.get("rating")
            if rating:
                try:
                    ratings.append(float(rating))
                except:
                    pass
        
        avg_price = statistics.mean(prices) if prices else 0
        median_price = statistics.median(prices) if prices else 0
        
        # Price tier distribution
        price_tiers = {
            "budget": {"range": "< ₹300", "count": 0, "products": []},
            "mass": {"range": "₹300-500", "count": 0, "products": []},
            "masstige": {"range": "₹500-800", "count": 0, "products": []},
            "premium": {"range": "₹800-1,500", "count": 0, "products": []},
            "prestige": {"range": "> ₹1,500", "count": 0, "products": []}
        }
        
        for price in prices:
            if price < 300:
                price_tiers["budget"]["count"] += 1
            elif price < 500:
                price_tiers["mass"]["count"] += 1
            elif price < 800:
                price_tiers["masstige"]["count"] += 1
            elif price < 1500:
                price_tiers["premium"]["count"] += 1
            else:
                price_tiers["prestige"]["count"] += 1
        
        return {
            "category": category,
            "products_found": len(products),
            "brands_found": len(brands),
            "analysis_date": datetime.now().isoformat(),
            "market_overview": {
                "average_price": round(avg_price, 2),
                "median_price": round(median_price, 2),
                "price_range": {
                    "min": min(prices) if prices else 0,
                    "max": max(prices) if prices else 0
                },
                "average_rating": round(statistics.mean(ratings), 2) if ratings else 0
            },
            "price_tier_distribution": price_tiers,
            "brand_analysis": {
                "top_brands": dict(sorted(brands.items(), key=lambda x: x[1], reverse=True)[:10])
            }
        }
    
    async def analyze_regional_demand(
        self,
        ingredient: str,
        time_range: str = "today 12-m"
    ) -> Dict[str, Any]:
        """Analyze regional demand across Indian states"""
        # Normalize ingredient name for consistent caching
        ingredient_normalized = ingredient.lower().strip()
        query = f"{ingredient} serum"
        cache_key_params = {
            "ingredient": ingredient_normalized,
            "time_range": time_range,
            "query": query.lower()  # Normalize query
        }
        
        # CACHING DISABLED - Always fetch fresh
        regional_data = None
        print(f"🔄 Fetching fresh regional demand data for: {ingredient_normalized}")
        try:
            regional_data = self.client.get_trends_regional(query, time_range)
            if regional_data and "error" not in regional_data:
                print(f"✅ Fetched fresh regional data for: {ingredient_normalized}")
            elif regional_data and "error" in regional_data:
                error_msg = regional_data.get("error", "Unknown error")
                return {"error": f"SerpAPI error: {error_msg}"}
        except Exception as e:
            print(f"❌ Error fetching regional data: {str(e)}")
            return {"error": f"Failed to fetch regional data: {str(e)}"}
        
        # Check if regional_data is valid
        if not regional_data:
            return {"error": "No regional data received from API"}
        
        if "error" in regional_data:
            error_msg = regional_data.get("error", "Unknown error")
            return {"error": f"SerpAPI error: {error_msg}"}
        
        interest_by_region = regional_data.get("interest_by_region", [])
        
        # Map Indian states
        high_demand = []
        moderate_demand = []
        low_demand = []
        
        for region in interest_by_region:
            interest = region.get("extracted_value", 0) or region.get("value", 0)
            location = region.get("location", "")
            
            if interest >= 70:
                high_demand.append({"state": location, "interest": interest})
            elif interest >= 40:
                moderate_demand.append({"state": location, "interest": interest})
            else:
                low_demand.append({"state": location, "interest": interest})
        
        return {
            "ingredient": ingredient,
            "total_regions": len(interest_by_region),
            "high_demand_regions": sorted(high_demand, key=lambda x: x["interest"], reverse=True),
            "moderate_demand_regions": sorted(moderate_demand, key=lambda x: x["interest"], reverse=True),
            "low_demand_regions": sorted(low_demand, key=lambda x: x["interest"], reverse=True)
        }
    
    async def compare_ingredients(
        self,
        ingredients: List[str],
        time_range: str = "today 12-m"
    ) -> Dict[str, Any]:
        """Compare multiple ingredients"""
        if len(ingredients) > 5:
            ingredients = ingredients[:5]
        
        queries = [f"{ing} serum" for ing in ingredients]
        
        try:
            comparison_data = self.client.compare_trends(queries, time_range)
            timeline = comparison_data.get("interest_over_time", {}).get("timeline_data", [])
            
            # Extract values for each ingredient
            ingredient_data = {}
            for ing in ingredients:
                ingredient_data[ing] = []
            
            for point in timeline:
                if point.get("values"):
                    for val_obj in point["values"]:
                        query = val_obj.get("query", "")
                        value = val_obj.get("extracted_value", 0)
                        # Match query to ingredient
                        for ing in ingredients:
                            if ing.lower() in query.lower():
                                ingredient_data[ing].append(value)
                                break
            
            # Calculate averages
            comparison = []
            for ing, values in ingredient_data.items():
                if values:
                    avg = statistics.mean(values)
                    comparison.append({
                        "ingredient": ing,
                        "average_interest": round(avg, 2),
                        "data_points": len(values)
                    })
            
            return {
                "ingredients": ingredients,
                "time_range": time_range,
                "comparison": sorted(comparison, key=lambda x: x["average_interest"], reverse=True)
            }
        except Exception as e:
            return {"error": f"Failed to compare ingredients: {str(e)}"}

