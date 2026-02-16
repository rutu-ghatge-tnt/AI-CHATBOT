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
        use_fallback: bool = True,
        parsed_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Main function to fetch market trends for Make A Wish using Claude synthesis.
        
        Strategy:
        1. Try MongoDB first (batch data)
        2. If missing, fallback to SerpAPI (if use_fallback=True)
        3. Store SerpAPI results in MongoDB for future use
        4. Call Claude to synthesize into structured intelligence
        
        Args:
            hero_ingredients: List of ingredient names
            benefits: List of benefits
            product_type: Product format (serum, cream, etc.)
            category: "skincare" or "haircare"
            max_age_days: Max age of cached data (default: 35 days)
            use_fallback: Whether to use SerpAPI if MongoDB has no data
            parsed_data: Parsed wish data from NLP stage (REQUIRED)
        
        Returns:
            Structured synthesis JSON ready for frontend with executive summary,
            opportunity analysis, competitive intelligence, and recommendations.
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
        
        # Check if we have sufficient data (not just empty dicts/lists)
        level_1_trends = mongo_data.get("level_1_ingredient_trends", {})
        level_2_approaches = mongo_data.get("level_2_competing_approaches", [])
        
        # Check if we have actual trend data with meaningful content
        has_ingredient_data = False
        ingredient_count = 0
        if level_1_trends:
            # Check if any ingredient has actual trend_data with current_score > 0
            for ing_name, ing_data in level_1_trends.items():
                if ing_data and ing_data.get("trend_data"):
                    trend_doc = ing_data["trend_data"]
                    current_score = trend_doc.get("current_score", 0)
                    if current_score > 0:
                        has_ingredient_data = True
                        ingredient_count += 1
                        print(f"   ✅ Found valid trend data for {ing_name}: current_score={current_score}")
                    else:
                        print(f"   ⚠️ Trend data for {ing_name} has current_score=0, will use SerpAPI fallback")
        
        has_benefit_data = False
        benefit_count = 0
        if level_2_approaches:
            for item in level_2_approaches:
                if isinstance(item, dict) and item.get("current_score", 0) > 0:
                    has_benefit_data = True
                    benefit_count += 1
        
        print(f"📊 Market trends check: ingredient_data={has_ingredient_data} ({ingredient_count} valid), benefit_data={has_benefit_data} ({benefit_count} valid)")
        print(f"   Total ingredients requested: {len(hero_ingredients)}, Total benefits requested: {len(benefits)}")
        
        # Step 2: Fallback to SerpAPI if needed (query on-demand and store)
        # ALWAYS use fallback if we don't have data for ALL requested ingredients/benefits
        needs_fallback = False
        if use_fallback:
            # Check if we need fallback: missing data OR current_score = 0
            if not has_ingredient_data or ingredient_count < len(hero_ingredients):
                needs_fallback = True
                print(f"📡 Missing ingredient data: have {ingredient_count}, need {len(hero_ingredients)}")
            if not has_benefit_data and benefits:
                needs_fallback = True
                print(f"📡 Missing benefit data: have {benefit_count}, need {len(benefits)}")
        
        if needs_fallback:
            print(f"📡 MongoDB has insufficient data (or current_score=0), querying SerpAPI on-demand...")
            fallback_data = await self._fetch_from_serpapi_fallback(
                hero_ingredients=hero_ingredients,
                benefits=benefits,
                product_type=product_type,
                category=category
            )
            
            # Merge fallback data with MongoDB data
            mongo_data = self._merge_trends_data(mongo_data, fallback_data)
            print(f"✅ SerpAPI fallback completed. Merged data ready for frontend.")
        else:
            if not use_fallback:
                print(f"ℹ️ SerpAPI fallback disabled. Using only MongoDB data.")
            else:
                print(f"✅ MongoDB has sufficient data for all ingredients/benefits. No SerpAPI fallback needed.")
        
        # Step 3: Synthesize with Claude (REQUIRED - no legacy fallback)
        if not parsed_data:
            raise ValueError("parsed_data is required for trend synthesis. Please ensure the wish has been parsed first.")
        
        try:
            # Import synthesis module
            from app.ai_ingredient_intelligence.logic.trend_synthesis import synthesize_trends
            
            print(f"🧠 Using trend synthesis (Claude) to generate structured intelligence...")
            
            # Prepare matched_trends in the format expected by synthesis
            matched_trends = {
                "level_1_ingredient_trends": mongo_data.get("level_1_ingredient_trends", {}),
                "level_2_competing_approaches": mongo_data.get("level_2_competing_approaches", []),
                "level_3_brand_trends": mongo_data.get("level_3_brand_trends", []),
                "comparison_data": mongo_data.get("comparison_data", []),
                "shopping_data": mongo_data.get("shopping_data"),
                "insights": mongo_data.get("insights", {})
            }
            
            # Call synthesis
            synthesized = await synthesize_trends(
                parsed_data=parsed_data,
                matched_trends=matched_trends
            )
            
            print(f"✅ Trend synthesis complete!")
            return synthesized
            
        except Exception as e:
            print(f"❌ Trend synthesis failed: {e}")
            import traceback
            traceback.print_exc()
            raise ValueError(f"Failed to synthesize market trends: {str(e)}")
    
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
        
        # Fetch ingredient trends - query multiple variations to catch everything
        for ingredient in hero_ingredients[:3]:  # Limit to 3 to avoid rate limits
            try:
                # Build multiple query variations to catch all related searches
                query_variations = []
                
                # 1. Base ingredient query
                query_variations.append(ingredient)
                
                # 2. Ingredient + product type variations
                if product_type:
                    query_variations.extend([
                        f"{ingredient} {product_type}",
                        f"{product_type} with {ingredient}",
                        f"{ingredient} {product_type} benefits"
                    ])
                else:
                    query_variations.extend([
                        f"{ingredient} {category}",
                        f"{category} {ingredient}"
                    ])
                
                # 3. Ingredient + benefit combinations
                if benefits:
                    for benefit in benefits[:2]:  # Top 2 benefits
                        if product_type:
                            query_variations.append(f"{ingredient} {product_type} {benefit}")
                        else:
                            query_variations.append(f"{ingredient} {benefit}")
                
                # 4. Common variations
                query_variations.extend([
                    f"{ingredient} for skin",
                    f"{ingredient} benefits",
                    f"{ingredient} products",
                    f"best {ingredient} {product_type}" if product_type else f"best {ingredient}"
                ])
                
                # Remove duplicates while preserving order
                seen = set()
                unique_variations = []
                for q in query_variations:
                    q_lower = q.lower()
                    if q_lower not in seen:
                        seen.add(q_lower)
                        unique_variations.append(q)
                
                print(f"   🔍 Fetching trends for {ingredient} with {len(unique_variations)} query variations...")
                
                # Fetch trends for primary query (most comprehensive)
                primary_query = unique_variations[0] if unique_variations else ingredient
                print(f"   📊 Primary query: '{primary_query}'")
                
                # Fetch trends for primary query
                trends_data = self.serpapi_client.get_trends_timeseries(
                    query=primary_query,
                    time_range="today 12-m",
                    geo="IN"
                )
                
                # Fetch related queries to discover more variations
                related_data = self.serpapi_client.get_trends_related_queries(
                    query=primary_query,
                    time_range="today 12-m",
                    geo="IN"
                )
                
                # Fetch regional data
                regional_data = self.serpapi_client.get_trends_regional(
                    query=primary_query,
                    time_range="today 12-m",
                    geo="IN"
                )
                
                # Extract related queries and fetch trends for top related searches
                related_queries_to_fetch = []
                if related_data and "related_queries" in related_data:
                    related_queries = related_data["related_queries"]
                    # Get top rising queries
                    rising = related_queries.get("rising", [])[:5]
                    top = related_queries.get("top", [])[:5]
                    
                    for item in rising + top:
                        related_query = item.get("query", "")
                        if related_query and ingredient.lower() in related_query.lower():
                            related_queries_to_fetch.append(related_query)
                
                # Process and store primary query data
                processed_doc = await self._process_and_store_serpapi_data(
                    query_text=primary_query,
                    ingredient=ingredient,
                    product_type=product_type,
                    category=category,
                    trends_data=trends_data,
                    related_data=related_data,
                    regional_data=regional_data,
                    related_queries_list=related_queries_to_fetch
                )
                
                if processed_doc:
                    fallback_data["level_1_ingredient_trends"][ingredient] = {
                        "trend_data": processed_doc,
                        "query_text": primary_query,
                        "query_variations": unique_variations[:10],  # Store top 10 variations
                        "related_queries_found": related_queries_to_fetch[:10],
                        "match_type": "serpapi_fallback_comprehensive",
                        "confidence": "high"
                    }
                    
                    # Also fetch and store trends for top related queries (if they contain the ingredient)
                    for related_query in related_queries_to_fetch[:3]:  # Limit to 3 to avoid rate limits
                        try:
                            print(f"   🔗 Fetching related query: '{related_query}'")
                            related_trends = self.serpapi_client.get_trends_timeseries(
                                query=related_query,
                                time_range="today 12-m",
                                geo="IN"
                            )
                            
                            # Store related query data
                            await self._process_and_store_serpapi_data(
                                query_text=related_query,
                                ingredient=ingredient,  # Tag with original ingredient
                                product_type=product_type,
                                category=category,
                                trends_data=related_trends,
                                related_data={},
                                regional_data={}
                            )
                        except Exception as e:
                            print(f"   ⚠️ Error fetching related query '{related_query}': {e}")
                            continue
            
            except Exception as e:
                print(f"⚠️ Error fetching SerpAPI data for {ingredient}: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        # Fetch benefit trends - query multiple variations to catch everything
        if benefits:
            for benefit in benefits[:2]:  # Limit to 2
                try:
                    # Build multiple query variations for benefit
                    benefit_variations = []
                    
                    # 1. Base benefit query
                    benefit_variations.append(benefit)
                    
                    # 2. Benefit + product type variations
                    if product_type:
                        benefit_variations.extend([
                            f"{benefit} {product_type}",
                            f"{product_type} for {benefit}",
                            f"{product_type} {benefit}",
                            f"best {benefit} {product_type}"
                        ])
                    else:
                        benefit_variations.extend([
                            f"{benefit} {category}",
                            f"{category} for {benefit}"
                        ])
                    
                    # 3. Benefit + ingredient combinations
                    if hero_ingredients:
                        for ing in hero_ingredients[:2]:  # Top 2 ingredients
                            if product_type:
                                benefit_variations.append(f"{benefit} {product_type} {ing}")
                            else:
                                benefit_variations.append(f"{benefit} {ing}")
                    
                    # 4. Common benefit variations
                    benefit_variations.extend([
                        f"{benefit} treatment",
                        f"{benefit} solution",
                        f"how to {benefit}",
                        f"{benefit} products"
                    ])
                    
                    # Remove duplicates
                    seen = set()
                    unique_benefit_variations = []
                    for q in benefit_variations:
                        q_lower = q.lower()
                        if q_lower not in seen:
                            seen.add(q_lower)
                            unique_benefit_variations.append(q)
                    
                    print(f"   🔍 Fetching trends for benefit '{benefit}' with {len(unique_benefit_variations)} query variations...")
                    
                    # Primary benefit query
                    primary_benefit_query = unique_benefit_variations[0] if unique_benefit_variations else benefit
                    print(f"   📊 Primary benefit query: '{primary_benefit_query}'")
                    
                    # Fetch trends
                    trends_data = self.serpapi_client.get_trends_timeseries(
                        query=primary_benefit_query,
                        time_range="today 12-m",
                        geo="IN"
                    )
                    
                    # Fetch related queries to discover more variations
                    related_data = self.serpapi_client.get_trends_related_queries(
                        query=primary_benefit_query,
                        time_range="today 12-m",
                        geo="IN"
                    )
                    
                    # Fetch regional data
                    regional_data = self.serpapi_client.get_trends_regional(
                        query=primary_benefit_query,
                        time_range="today 12-m",
                        geo="IN"
                    )
                    
                    # Extract related queries for benefits
                    related_benefit_queries = []
                    if related_data and "related_queries" in related_data:
                        related_queries = related_data["related_queries"]
                        rising = related_queries.get("rising", [])[:5]
                        top = related_queries.get("top", [])[:5]
                        
                        for item in rising + top:
                            related_query = item.get("query", "")
                            if related_query and benefit.lower() in related_query.lower():
                                related_benefit_queries.append(related_query)
                    
                    # Process and store benefit data
                    processed_doc = await self._process_and_store_serpapi_data(
                        query_text=primary_benefit_query,
                        ingredient=None,
                        product_type=product_type,
                        category=category,
                        benefit=benefit,
                        trends_data=trends_data,
                        related_data=related_data,
                        regional_data=regional_data,
                        related_queries_list=related_benefit_queries
                    )
                    
                    if processed_doc:
                        # Add query variations to the document
                        processed_doc["query_variations"] = unique_benefit_variations[:10]
                        processed_doc["related_queries_found"] = related_benefit_queries[:10]
                        fallback_data["level_2_competing_approaches"].append(processed_doc)
                        
                        # Also fetch trends for top related benefit queries
                        for related_query in related_benefit_queries[:3]:
                            try:
                                print(f"   🔗 Fetching related benefit query: '{related_query}'")
                                related_trends = self.serpapi_client.get_trends_timeseries(
                                    query=related_query,
                                    time_range="today 12-m",
                                    geo="IN"
                                )
                                
                                await self._process_and_store_serpapi_data(
                                    query_text=related_query,
                                    ingredient=None,
                                    product_type=product_type,
                                    category=category,
                                    benefit=benefit,  # Tag with original benefit
                                    trends_data=related_trends,
                                    related_data={},
                                    regional_data={}
                                )
                            except Exception as e:
                                print(f"   ⚠️ Error fetching related benefit query '{related_query}': {e}")
                                continue
                
                except Exception as e:
                    print(f"⚠️ Error fetching SerpAPI data for benefit {benefit}: {e}")
                    import traceback
                    traceback.print_exc()
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
        benefit: Optional[str] = None,
        related_queries_list: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """Process SerpAPI response and store in MongoDB"""
        try:
            # Extract timeline data - safely handle different response structures
            if not trends_data or not isinstance(trends_data, dict):
                return None
            
            interest_over_time = trends_data.get("interest_over_time", {})
            if not interest_over_time or not isinstance(interest_over_time, dict):
                return None
            
            timeline_data = interest_over_time.get("timeline_data", [])
            if not timeline_data or not isinstance(timeline_data, list):
                return None
            
            # Process values
            values = []
            dates = []
            for point in timeline_data:
                if not isinstance(point, dict):
                    continue
                    
                point_values = point.get("values")
                if point_values and isinstance(point_values, list) and len(point_values) > 0:
                    first_value = point_values[0]
                    if isinstance(first_value, dict):
                        val = first_value.get("extracted_value", 0)
                        if val is not None:
                            try:
                                val = int(val) if isinstance(val, (int, float, str)) else 0
                                values.append(val)
                                dates.append(point.get("date", ""))
                            except (ValueError, TypeError):
                                continue
            
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
            
            # Safely handle related_data (might be None or empty dict)
            if related_data and isinstance(related_data, dict):
                related_queries = related_data.get("related_queries", {})
                if isinstance(related_queries, dict):
                    rising_list = related_queries.get("rising", [])
                    if isinstance(rising_list, list):
                        for item in rising_list[:10]:
                            if isinstance(item, dict):
                                related_queries_rising.append({
                                    "query": item.get("query", ""),
                                    "growth": item.get("value", ""),
                                    "extracted_value": item.get("extracted_value", 0)
                                })
                    
                    top_list = related_queries.get("top", [])
                    if isinstance(top_list, list):
                        for item in top_list[:10]:
                            if isinstance(item, dict):
                                related_queries_top.append({
                                    "query": item.get("query", ""),
                                    "volume": item.get("value", ""),
                                    "extracted_value": item.get("extracted_value", 0)
                                })
            
            # Process regional data
            regional_interest = []
            if regional_data and isinstance(regional_data, dict):
                interest_by_region = regional_data.get("interest_by_region", [])
                if isinstance(interest_by_region, list):
                    for region in interest_by_region[:20]:
                        if isinstance(region, dict):
                            regional_interest.append({
                                "location": region.get("location", ""),
                                "value": region.get("value", ""),
                                "extracted_value": region.get("extracted_value", 0) or region.get("value", 0)
                            })
            
            # Build document with all related queries
            doc = {
                "query_text": query_text,
                "query_level": "ingredient" if ingredient else "benefit",
                "category": category,
                "ingredient_tag": normalize_ingredient_name(ingredient) if ingredient else None,
                "product_format": normalize_product_type(product_type) if product_type else None,
                "benefit_tag": normalize_benefit(benefit) if benefit else None,
                "brand_tag": None,
                "comparison_group": None,
                "related_queries_list": related_queries_list or [],  # Store related queries found
                "query_variations": [],  # Will be populated by caller if needed
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
            
            # Store in MongoDB (upsert to avoid duplicates)
            # Check if document already exists
            existing = await market_trends_storage_col.find_one({
                "query_text": query_text,
                "query_level": doc["query_level"],
                "category": category
            })
            
            if existing:
                # Update existing document with new data
                await market_trends_storage_col.update_one(
                    {"_id": existing["_id"]},
                    {"$set": {
                        **doc,
                        "fetched_at": datetime.utcnow(),
                        "fetch_source": "serpapi_fallback"
                    }}
                )
                print(f"✅ Updated existing market trends document for: {query_text}")
            else:
                # Insert new document
                await market_trends_storage_col.insert_one(doc)
                print(f"✅ Stored new market trends data in MongoDB for: {query_text}")
            
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
    

