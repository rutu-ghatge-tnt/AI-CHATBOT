"""
Scheduled Trend Monitoring Job
==============================

Runs daily trend monitoring for tracked ingredients.
Can be scheduled using APScheduler, Celery, or cron.
"""

import asyncio
from datetime import datetime
from app.ai_ingredient_intelligence.logic.trend_monitor import TrendMonitor


async def run_daily_trend_monitor():
    """
    Daily trend monitoring job
    
    Monitors all tracked ingredients and generates alerts for:
    - Explosive growth (>50% in 6 months)
    - Breakout queries
    - Declining trends
    
    This function should be called by a scheduler (APScheduler, Celery, or cron)
    """
    print(f"[{datetime.now()}] Starting daily trend monitor...")
    
    monitor = TrendMonitor()
    
    try:
        result = await monitor.monitor_tracked_ingredients()
        
        print(f"[{datetime.now()}] Trend monitoring completed:")
        print(f"  - Ingredients checked: {result['ingredients_checked']}")
        print(f"  - Total alerts generated: {result['total_alerts']}")
        
        # Log alerts by type
        alert_types = {}
        for item in result.get("results", []):
            for alert in item.get("alerts", []):
                alert_type = alert.get("type", "unknown")
                alert_types[alert_type] = alert_types.get(alert_type, 0) + 1
        
        if alert_types:
            print(f"  - Alert breakdown: {alert_types}")
        
        return result
        
    except Exception as e:
        print(f"[{datetime.now()}] Error in trend monitoring: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


# For APScheduler integration
def scheduled_trend_monitor():
    """
    Wrapper for APScheduler (synchronous scheduler)
    
    Usage with APScheduler:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(scheduled_trend_monitor, "cron", hour=6, minute=0)  # Daily at 6 AM
        scheduler.start()
    """
    asyncio.run(run_daily_trend_monitor())


# For direct async execution
if __name__ == "__main__":
    # Run directly for testing
    asyncio.run(run_daily_trend_monitor())

