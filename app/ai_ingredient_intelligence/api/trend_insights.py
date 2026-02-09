"""
Trend Insights API Endpoints
============================

API endpoints for real-time market intelligence using SerpAPI.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, List
from datetime import datetime

from app.ai_ingredient_intelligence.auth import verify_jwt_token
from app.ai_ingredient_intelligence.logic.trend_analyzer import TrendAnalyzer
from app.ai_ingredient_intelligence.logic.trend_synthesis import synthesize_trend_insights
from app.ai_ingredient_intelligence.logic.trend_monitor import TrendMonitor
from app.ai_ingredient_intelligence.models.trend_schemas import (
    TrendAnalysisRequest,
    TrendAnalysisResponse,
    ConsumerIntentRequest,
    ConsumerIntentResponse,
    CompetitiveAnalysisRequest,
    CompetitiveAnalysisResponse,
    RegionalAnalysisRequest,
    RegionalAnalysisResponse,
    CompareIngredientsRequest,
    CompareIngredientsResponse,
    TrendSynthesisRequest,
    TrendSynthesisResponse
)

router = APIRouter(prefix="/trends", tags=["Trend Insights"])

# Initialize analyzer and monitor (lazy initialization to avoid errors if SERPAPI_KEY not set)
analyzer = None
monitor = None

def get_analyzer():
    """Lazy initialization of analyzer"""
    global analyzer
    if analyzer is None:
        analyzer = TrendAnalyzer()
    return analyzer

def get_monitor():
    """Lazy initialization of monitor"""
    global monitor
    if monitor is None:
        monitor = TrendMonitor()
    return monitor


@router.post("/analyze", response_model=TrendAnalysisResponse)
async def analyze_trend(
    request: TrendAnalysisRequest,
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Analyze trend for a single ingredient
    
    Returns trend classification, growth rates, and related queries
    """
    try:
        result = await get_analyzer().analyze_ingredient_trend(
            request.ingredient,
            request.time_range,
            request.compare_with
        )
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/consumer-intent", response_model=ConsumerIntentResponse)
async def analyze_consumer_intent(
    request: ConsumerIntentRequest,
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Analyze consumer intent from People Also Ask questions
    
    Categorizes questions by intent type (efficacy, safety, usage, purchase, comparison)
    """
    try:
        result = await get_analyzer().analyze_consumer_intent(
            request.ingredient,
            request.concerns
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/competitive", response_model=CompetitiveAnalysisResponse)
async def analyze_competitive(
    request: CompetitiveAnalysisRequest,
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Analyze competitive landscape from Google Shopping data
    
    Returns price distribution, brand analysis, and market overview
    """
    try:
        result = await get_analyzer().analyze_competitive_landscape(
            request.category,
            request.price_min,
            request.price_max
        )
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/regional", response_model=RegionalAnalysisResponse)
async def analyze_regional(
    request: RegionalAnalysisRequest,
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Analyze regional demand across Indian states
    
    Categorizes states by demand level (high, moderate, low)
    """
    try:
        result = await get_analyzer().analyze_regional_demand(
            request.ingredient,
            request.time_range
        )
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/compare", response_model=CompareIngredientsResponse)
async def compare_ingredients(
    request: CompareIngredientsRequest,
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Compare multiple ingredients (up to 5)
    
    Returns relative interest levels for each ingredient
    """
    try:
        if len(request.ingredients) > 5:
            raise HTTPException(status_code=400, detail="Maximum 5 ingredients allowed for comparison")
        
        result = await get_analyzer().compare_ingredients(
            request.ingredients,
            request.time_range
        )
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/synthesis", response_model=TrendSynthesisResponse)
async def synthesize_trends(
    request: TrendSynthesisRequest,
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Comprehensive trend synthesis combining all data sources
    
    Returns complete analysis with AI-powered insights and recommendations
    """
    try:
        # Gather all data sources
        analyzer_instance = get_analyzer()
        trend_data = await analyzer_instance.analyze_ingredient_trend(
            request.ingredient,
            request.time_range
        )
        
        consumer_intent_data = None
        competitive_data = None
        regional_data = None
        
        if request.include_consumer_intent:
            consumer_intent_data = await analyzer_instance.analyze_consumer_intent(request.ingredient)
        
        if request.include_competitive:
            competitive_data = await analyzer_instance.analyze_competitive_landscape(f"{request.ingredient} serum")
        
        if request.include_regional:
            regional_data = await analyzer_instance.analyze_regional_demand(
                request.ingredient,
                request.time_range
            )
        
        # Send to Claude for synthesis
        synthesis_result = await synthesize_trend_insights(
            request.ingredient,
            trend_data if "error" not in trend_data else {},
            consumer_intent_data,
            competitive_data if "error" not in competitive_data else None,
            regional_data if "error" not in regional_data else None
        )
        
        return {
            "ingredient": request.ingredient,
            "trend_analysis": trend_data if "error" not in trend_data else None,
            "consumer_intent": consumer_intent_data,
            "competitive_landscape": competitive_data if "error" not in competitive_data else None,
            "regional_demand": regional_data if "error" not in regional_data else None,
            "synthesis": synthesis_result.get("synthesis"),
            "error": synthesis_result.get("error")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/monitor/run")
async def run_monitoring(
    ingredients: Optional[List[str]] = None,
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Run trend monitoring for tracked ingredients
    
    Manually trigger monitoring (also runs on schedule)
    """
    try:
        result = await get_monitor().monitor_tracked_ingredients(ingredients)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/alerts")
async def get_alerts(
    limit: int = Query(50, ge=1, le=200),
    severity: Optional[str] = Query(None, regex="^(high|medium|low)$"),
    acknowledged: Optional[bool] = Query(None),
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Get recent trend alerts
    
    Returns alerts for explosive growth, breakout queries, and declining trends
    """
    try:
        alerts = await get_monitor().get_recent_alerts(limit=limit, severity=severity, acknowledged=acknowledged)
        return {
            "alerts": alerts,
            "count": len(alerts)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    current_user: dict = Depends(verify_jwt_token)
):
    """Mark an alert as acknowledged"""
    try:
        success = await get_monitor().acknowledge_alert(alert_id)
        if not success:
            raise HTTPException(status_code=404, detail="Alert not found")
        return {"success": True, "alert_id": alert_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Get dashboard summary data
    
    Returns overview of trends, alerts, and key metrics
    """
    try:
        from datetime import datetime, timedelta
        
        monitor_instance = get_monitor()
        # Get recent alerts
        recent_alerts = await monitor_instance.get_recent_alerts(limit=10, acknowledged=False)
        
        # Get trend history for tracked ingredients
        tracked_ingredients = [
            "niacinamide", "vitamin c", "retinol", "tranexamic acid", "ceramides"
        ]
        
        ingredient_summaries = []
        for ingredient in tracked_ingredients[:5]:  # Limit to 5 for performance
            history = await monitor_instance.get_ingredient_history(ingredient, days=7)
            if history:
                latest = history[-1]
                ingredient_summaries.append({
                    "ingredient": ingredient,
                    "current_interest": latest.get("current_interest", 0),
                    "growth_6mo": latest.get("growth_6mo", 0),
                    "trajectory": latest.get("trajectory", ""),
                    "last_updated": latest.get("timestamp")
                })
        
        return {
            "summary": {
                "total_alerts": len(recent_alerts),
                "high_severity_alerts": len([a for a in recent_alerts if a.get("severity") == "high"]),
                "tracked_ingredients": len(tracked_ingredients),
                "last_updated": datetime.utcnow().isoformat()
            },
            "recent_alerts": recent_alerts[:5],
            "ingredient_summaries": ingredient_summaries
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/dashboard/ingredient/{ingredient}")
async def get_ingredient_dashboard(
    ingredient: str,
    days: int = Query(30, ge=1, le=365),
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Get dashboard data for a specific ingredient
    
    Returns trend history, alerts, and current status
    """
    try:
        monitor_instance = get_monitor()
        analyzer_instance = get_analyzer()
        # Get trend history
        history = await monitor_instance.get_ingredient_history(ingredient, days=days)
        
        # Get recent alerts for this ingredient
        all_alerts = await monitor_instance.get_recent_alerts(limit=100)
        ingredient_alerts = [a for a in all_alerts if a.get("ingredient") == ingredient]
        
        # Get current trend analysis
        current_analysis = await analyzer_instance.analyze_ingredient_trend(ingredient)
        
        return {
            "ingredient": ingredient,
            "history": history,
            "alerts": ingredient_alerts,
            "current_analysis": current_analysis if "error" not in current_analysis else None,
            "summary": {
                "data_points": len(history),
                "total_alerts": len(ingredient_alerts),
                "unacknowledged_alerts": len([a for a in ingredient_alerts if not a.get("acknowledged")])
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/dashboard/trending")
async def get_trending_ingredients(
    limit: int = Query(10, ge=1, le=50),
    min_growth: float = Query(20.0, description="Minimum 6-month growth rate"),
    current_user: dict = Depends(verify_jwt_token)
):
    """
    Get trending ingredients (high growth)
    
    Returns ingredients with growth above threshold
    """
    try:
        from app.ai_ingredient_intelligence.logic.trend_monitor import DEFAULT_TRACKED_INGREDIENTS
        
        monitor_instance = get_monitor()
        trending = []
        for ingredient in DEFAULT_TRACKED_INGREDIENTS[:limit * 2]:  # Check more than needed
            history = await monitor_instance.get_ingredient_history(ingredient, days=7)
            if history:
                latest = history[-1]
                growth = latest.get("growth_6mo", 0)
                if growth >= min_growth:
                    trending.append({
                        "ingredient": ingredient,
                        "growth_6mo": growth,
                        "current_interest": latest.get("current_interest", 0),
                        "trajectory": latest.get("trajectory", ""),
                        "last_updated": latest.get("timestamp")
                    })
        
        # Sort by growth and return top N
        trending.sort(key=lambda x: x["growth_6mo"], reverse=True)
        return {
            "trending_ingredients": trending[:limit],
            "threshold": min_growth,
            "count": len(trending[:limit])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/health")
async def health_check():
    """Health check endpoint for trend insights service"""
    try:
        # Check if SerpAPI key is configured
        import os
        has_key = os.getenv("SERPAPI_KEY") is not None
        
        return {
            "status": "healthy" if has_key else "configured",
            "serpapi_configured": has_key,
            "message": "Trend Insights API is operational" if has_key else "SERPAPI_KEY not configured"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

