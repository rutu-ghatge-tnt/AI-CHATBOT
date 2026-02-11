"""
Scheduled Market Trends Fetcher
================================

This script runs at fixed intervals to fetch market trend data for a list of topics/ingredients
and stores it in the database. The stored data is then used in the make wish flow instead of
making real-time API calls.

For now, the script skips actual API calls since data is not available yet.
Once the document is provided, the script can be updated to fetch real data.
"""

import asyncio
import os
import sys
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from app.ai_ingredient_intelligence.db.collections import market_trends_storage_col
from app.ai_ingredient_intelligence.logic.trend_analyzer import TrendAnalyzer


# List of topics/ingredients to fetch trends for
# This can be configured via environment variable or config file
DEFAULT_TOPICS = [
    "Niacinamide",
    "Retinol",
    "Hyaluronic Acid",
    "Vitamin C",
    "Salicylic Acid",
    "Alpha Arbutin",
    "Tranexamic Acid",
    "Azelaic Acid",
    "Glycolic Acid",
    "Lactic Acid",
    "Bakuchiol",
    "Centella Asiatica",
    "Ceramides",
    "Peptides",
    "Squalane",
    "Niacinamide serum",
    "Retinol serum",
    "Vitamin C serum",
    "Hyaluronic Acid serum",
    "Salicylic Acid serum"
]


async def fetch_and_store_trend_data(
    topic: str,
    analyzer: TrendAnalyzer,
    skip_api_calls: bool = True
) -> Dict[str, Any]:
    """
    Fetch trend data for a topic and store it in the database.
    
    Args:
        topic: The topic/ingredient to fetch trends for
        analyzer: TrendAnalyzer instance
        skip_api_calls: If True, skip actual API calls (for now)
        
    Returns:
        Dictionary with status and data
    """
    # Normalize topic name for consistent storage
    topic_normalized = topic.lower().strip()
    
    print(f"📊 Processing topic: {topic}")
    
    if skip_api_calls:
        print(f"   ⏭️  Skipping API calls (data not available yet)")
        return {
            "topic": topic,
            "status": "skipped",
            "reason": "API calls disabled - waiting for data document"
        }
    
    # Fetch trend analysis
    trend_data = {}
    try:
        # Analyze ingredient trend
        analyze_data = await analyzer.analyze_ingredient_trend(
            topic,
            time_range="today 12-m"
        )
        
        if analyze_data and "error" not in analyze_data:
            trend_data["analyze"] = analyze_data
            print(f"   ✅ Fetched trend analysis")
        else:
            print(f"   ⚠️  Error in trend analysis: {analyze_data.get('error', 'Unknown error')}")
        
        # Fetch consumer intent
        try:
            consumer_intent_data = await analyzer.analyze_consumer_intent(topic)
            if consumer_intent_data and "error" not in consumer_intent_data:
                trend_data["consumer_intent"] = consumer_intent_data
                print(f"   ✅ Fetched consumer intent")
        except Exception as e:
            print(f"   ⚠️  Error fetching consumer intent: {str(e)}")
        
        # Fetch competitive landscape
        try:
            competitive_data = await analyzer.analyze_competitive_landscape(f"{topic} serum")
            if competitive_data and "error" not in competitive_data:
                trend_data["competitive"] = competitive_data
                print(f"   ✅ Fetched competitive landscape")
        except Exception as e:
            print(f"   ⚠️  Error fetching competitive landscape: {str(e)}")
        
        # Fetch regional demand
        try:
            regional_data = await analyzer.analyze_regional_demand(topic, "today 12-m")
            if regional_data and "error" not in regional_data:
                trend_data["regional"] = regional_data
                print(f"   ✅ Fetched regional demand")
        except Exception as e:
            print(f"   ⚠️  Error fetching regional demand: {str(e)}")
        
    except Exception as e:
        print(f"   ❌ Error fetching trend data: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "topic": topic,
            "status": "error",
            "error": str(e)
        }
    
    # Store in database
    if trend_data:
        try:
            # Check if data already exists for this topic
            existing = await market_trends_storage_col.find_one({
                "topic_normalized": topic_normalized
            })
            
            document = {
                "topic": topic,  # Original topic name
                "topic_normalized": topic_normalized,
                "trend_data": trend_data,
                "fetched_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "data_version": 1
            }
            
            if existing:
                # Update existing document
                document["data_version"] = existing.get("data_version", 0) + 1
                await market_trends_storage_col.update_one(
                    {"topic_normalized": topic_normalized},
                    {"$set": document}
                )
                print(f"   💾 Updated stored data (version {document['data_version']})")
            else:
                # Insert new document
                await market_trends_storage_col.insert_one(document)
                print(f"   💾 Stored new data")
            
            return {
                "topic": topic,
                "status": "success",
                "data_keys": list(trend_data.keys()),
                "version": document["data_version"]
            }
        except Exception as e:
            print(f"   ❌ Error storing data: {str(e)}")
            return {
                "topic": topic,
                "status": "storage_error",
                "error": str(e)
            }
    else:
        print(f"   ⚠️  No data to store")
        return {
            "topic": topic,
            "status": "no_data"
        }


async def run_scheduled_fetch(
    topics: Optional[List[str]] = None,
    skip_api_calls: bool = True,
    interval_seconds: Optional[int] = None
):
    """
    Run scheduled fetch for market trends.
    
    Args:
        topics: List of topics to fetch. If None, uses DEFAULT_TOPICS
        skip_api_calls: If True, skip actual API calls (for now)
        interval_seconds: If provided, run continuously at this interval
    """
    if topics is None:
        topics = DEFAULT_TOPICS
    
    print(f"\n{'='*60}")
    print(f"🔄 Starting Market Trends Scheduled Fetch")
    print(f"{'='*60}")
    print(f"📋 Topics to process: {len(topics)}")
    print(f"⏭️  API calls: {'DISABLED' if skip_api_calls else 'ENABLED'}")
    print(f"⏰ Started at: {datetime.now().isoformat()}")
    print(f"{'='*60}\n")
    
    analyzer = TrendAnalyzer()
    results = []
    
    for i, topic in enumerate(topics, 1):
        print(f"\n[{i}/{len(topics)}] Processing: {topic}")
        result = await fetch_and_store_trend_data(topic, analyzer, skip_api_calls)
        results.append(result)
        
        # Small delay between topics to avoid rate limiting
        if not skip_api_calls and i < len(topics):
            await asyncio.sleep(2)
    
    # Summary
    print(f"\n{'='*60}")
    print(f"📊 Summary")
    print(f"{'='*60}")
    status_counts = {}
    for result in results:
        status = result.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    
    for status, count in status_counts.items():
        print(f"   {status}: {count}")
    
    print(f"\n✅ Completed at: {datetime.now().isoformat()}")
    print(f"{'='*60}\n")
    
    return results


async def run_continuous(interval_hours: int = 24, skip_api_calls: bool = True):
    """
    Run the fetch continuously at specified intervals.
    
    Args:
        interval_hours: Hours between each run
        skip_api_calls: If True, skip actual API calls
    """
    interval_seconds = interval_hours * 3600
    
    print(f"🔄 Starting continuous market trends fetcher")
    print(f"   Interval: {interval_hours} hours ({interval_seconds} seconds)")
    print(f"   API calls: {'DISABLED' if skip_api_calls else 'ENABLED'}")
    
    while True:
        try:
            await run_scheduled_fetch(skip_api_calls=skip_api_calls)
            print(f"\n⏰ Next run in {interval_hours} hours...")
            await asyncio.sleep(interval_seconds)
        except KeyboardInterrupt:
            print("\n\n⚠️  Stopped by user")
            break
        except Exception as e:
            print(f"\n❌ Error in scheduled run: {str(e)}")
            import traceback
            traceback.print_exc()
            print(f"\n⏰ Retrying in {interval_hours} hours...")
            await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Fetch market trends and store in database")
    parser.add_argument(
        "--topics",
        nargs="+",
        help="List of topics to fetch (space-separated)"
    )
    parser.add_argument(
        "--enable-api",
        action="store_true",
        help="Enable actual API calls (default: disabled)"
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Run continuously at intervals"
    )
    parser.add_argument(
        "--interval-hours",
        type=int,
        default=24,
        help="Hours between runs (for continuous mode, default: 24)"
    )
    
    args = parser.parse_args()
    
    topics = args.topics if args.topics else None
    skip_api_calls = not args.enable_api
    
    if args.continuous:
        asyncio.run(run_continuous(
            interval_hours=args.interval_hours,
            skip_api_calls=skip_api_calls
        ))
    else:
        asyncio.run(run_scheduled_fetch(
            topics=topics,
            skip_api_calls=skip_api_calls
        ))

