"""
Trend Monitoring System
=======================

Scheduled monitoring of key ingredients for trend changes and alerts.
"""

import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from app.ai_ingredient_intelligence.logic.trend_analyzer import TrendAnalyzer
from app.ai_ingredient_intelligence.db.collections import trend_alerts_col, trend_history_col

# Default tracked ingredients
DEFAULT_TRACKED_INGREDIENTS = [
    "niacinamide",
    "vitamin c",
    "retinol",
    "hyaluronic acid",
    "tranexamic acid",
    "alpha arbutin",
    "salicylic acid",
    "ceramides",
    "peptides",
    "azelaic acid",
    "kojic acid",
    "centella",
    "bakuchiol",
    "snail mucin",
    "glycolic acid"
]


class TrendMonitor:
    """Monitors ingredient trends and generates alerts"""
    
    def __init__(self):
        self.analyzer = TrendAnalyzer()
    
    async def check_ingredient_trend(
        self,
        ingredient: str,
        time_range: str = "today 12-m"
    ) -> Dict[str, Any]:
        """
        Check trend for a single ingredient and generate alerts if needed
        
        Returns:
            Dict with trend data and any alerts generated
        """
        try:
            analysis = await self.analyzer.analyze_ingredient_trend(ingredient, time_range)
            
            if "error" in analysis:
                return {
                    "ingredient": ingredient,
                    "status": "error",
                    "error": analysis["error"],
                    "alerts": []
                }
            
            alerts = []
            
            # Check for explosive growth
            growth_6mo = analysis.get("trend_classification", {}).get("growth_rate_6mo", 0)
            if growth_6mo > 50:
                alerts.append({
                    "type": "EXPLOSIVE_GROWTH",
                    "severity": "high",
                    "message": f"{ingredient} showing explosive growth (+{growth_6mo:.1f}% in 6 months)",
                    "growth_rate": growth_6mo,
                    "timestamp": datetime.utcnow()
                })
            
            # Check for breakout queries
            rising_queries = analysis.get("related_queries", {}).get("rising", [])
            breakout_queries = [q for q in rising_queries if q.get("growth") == "Breakout" or 
                               (isinstance(q.get("extracted_value"), int) and q.get("extracted_value", 0) > 1000)]
            
            if breakout_queries:
                alerts.append({
                    "type": "BREAKOUT_QUERIES",
                    "severity": "medium",
                    "message": f"{ingredient} has {len(breakout_queries)} breakout search queries",
                    "queries": [q.get("query") for q in breakout_queries[:5]],
                    "timestamp": datetime.utcnow()
                })
            
            # Check for declining trend
            if growth_6mo < -20:
                alerts.append({
                    "type": "DECLINING_TREND",
                    "severity": "medium",
                    "message": f"{ingredient} showing declining interest ({growth_6mo:.1f}% in 6 months)",
                    "growth_rate": growth_6mo,
                    "timestamp": datetime.utcnow()
                })
            
            # Store in history
            await self._store_trend_history(ingredient, analysis)
            
            # Store alerts if any
            if alerts:
                await self._store_alerts(ingredient, alerts)
            
            return {
                "ingredient": ingredient,
                "status": "success",
                "current_interest": analysis.get("interest_metrics", {}).get("current_interest", 0),
                "growth_6mo": growth_6mo,
                "alerts": alerts
            }
            
        except Exception as e:
            return {
                "ingredient": ingredient,
                "status": "error",
                "error": str(e),
                "alerts": []
            }
    
    async def monitor_tracked_ingredients(
        self,
        ingredients: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Monitor all tracked ingredients
        
        Args:
            ingredients: List of ingredients to monitor (defaults to DEFAULT_TRACKED_INGREDIENTS)
            
        Returns:
            Summary of monitoring results
        """
        if ingredients is None:
            ingredients = DEFAULT_TRACKED_INGREDIENTS
        
        results = []
        total_alerts = 0
        
        for ingredient in ingredients:
            result = await self.check_ingredient_trend(ingredient)
            results.append(result)
            total_alerts += len(result.get("alerts", []))
        
        return {
            "monitored_at": datetime.utcnow(),
            "ingredients_checked": len(ingredients),
            "total_alerts": total_alerts,
            "results": results
        }
    
    async def _store_trend_history(
        self,
        ingredient: str,
        analysis: Dict[str, Any]
    ):
        """Store trend data in history collection"""
        try:
            history_entry = {
                "ingredient": ingredient,
                "timestamp": datetime.utcnow(),
                "current_interest": analysis.get("interest_metrics", {}).get("current_interest", 0),
                "growth_6mo": analysis.get("trend_classification", {}).get("growth_rate_6mo", 0),
                "trajectory": analysis.get("trend_classification", {}).get("trajectory", ""),
                "peak_interest": analysis.get("interest_metrics", {}).get("peak_interest", 0),
                "average_interest": analysis.get("interest_metrics", {}).get("average_interest", 0)
            }
            
            await trend_history_col.insert_one(history_entry)
        except Exception as e:
            print(f"Error storing trend history for {ingredient}: {e}")
    
    async def _store_alerts(
        self,
        ingredient: str,
        alerts: List[Dict[str, Any]]
    ):
        """Store alerts in alerts collection"""
        try:
            for alert in alerts:
                alert_entry = {
                    "ingredient": ingredient,
                    "alert_type": alert.get("type"),
                    "severity": alert.get("severity"),
                    "message": alert.get("message"),
                    "data": alert,
                    "created_at": datetime.utcnow(),
                    "acknowledged": False
                }
                
                await trend_alerts_col.insert_one(alert_entry)
        except Exception as e:
            print(f"Error storing alerts for {ingredient}: {e}")
    
    async def get_recent_alerts(
        self,
        limit: int = 50,
        severity: Optional[str] = None,
        acknowledged: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """Get recent alerts"""
        try:
            query = {}
            if severity:
                query["severity"] = severity
            if acknowledged is not None:
                query["acknowledged"] = acknowledged
            
            cursor = trend_alerts_col.find(query).sort("created_at", -1).limit(limit)
            alerts = []
            async for doc in cursor:
                alerts.append({
                    "id": str(doc["_id"]),
                    "ingredient": doc.get("ingredient"),
                    "alert_type": doc.get("alert_type"),
                    "severity": doc.get("severity"),
                    "message": doc.get("message"),
                    "data": doc.get("data"),
                    "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
                    "acknowledged": doc.get("acknowledged", False)
                })
            
            return alerts
        except Exception as e:
            print(f"Error getting alerts: {e}")
            return []
    
    async def acknowledge_alert(self, alert_id: str) -> bool:
        """Mark an alert as acknowledged"""
        try:
            from bson import ObjectId
            result = await trend_alerts_col.update_one(
                {"_id": ObjectId(alert_id)},
                {"$set": {"acknowledged": True, "acknowledged_at": datetime.utcnow()}}
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"Error acknowledging alert: {e}")
            return False
    
    async def get_ingredient_history(
        self,
        ingredient: str,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """Get historical trend data for an ingredient"""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            cursor = trend_history_col.find({
                "ingredient": ingredient,
                "timestamp": {"$gte": cutoff_date}
            }).sort("timestamp", 1)
            
            history = []
            async for doc in cursor:
                history.append({
                    "timestamp": doc.get("timestamp").isoformat() if doc.get("timestamp") else None,
                    "current_interest": doc.get("current_interest", 0),
                    "growth_6mo": doc.get("growth_6mo", 0),
                    "trajectory": doc.get("trajectory", ""),
                    "peak_interest": doc.get("peak_interest", 0),
                    "average_interest": doc.get("average_interest", 0)
                })
            
            return history
        except Exception as e:
            print(f"Error getting history for {ingredient}: {e}")
            return []

