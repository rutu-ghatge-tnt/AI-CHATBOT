"""
Retry Failed Market Trends Queries
===================================

Reads failed_queries.json and retries fetching those queries.
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from app.ai_ingredient_intelligence.db.collections import market_trends_storage_col
from app.ai_ingredient_intelligence.logic.trend_analyzer import SerpAPIClient
from app.ai_ingredient_intelligence.serpapi_batch_config.serpapi_batch_config import load_config
from app.ai_ingredient_intelligence.scripts.fetch_market_trends_scheduled import (
    BatchTrendFetcher,
    store_trend_data
)
from tqdm import tqdm


async def load_failed_queries(failed_file: Path) -> List[Dict[str, Any]]:
    """Load failed queries from JSON file"""
    if not failed_file.exists():
        print(f"❌ Failed queries file not found: {failed_file}")
        return []
    
    with open(failed_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    failed_queries = data.get("failed_queries", [])
    print(f"📋 Loaded {len(failed_queries)} failed queries from {failed_file}")
    
    return failed_queries


async def retry_failed_queries(
    failed_queries: List[Dict[str, Any]],
    skip_api_calls: bool = False
):
    """Retry fetching failed queries"""
    if not failed_queries:
        print("✅ No failed queries to retry")
        return
    
    print(f"\n{'='*80}")
    print(f"🔄 Retrying Failed Market Trends Queries")
    print(f"{'='*80}")
    print(f"⏰ Started at: {datetime.now().isoformat()}")
    print(f"📊 Total queries to retry: {len(failed_queries)}")
    print(f"⏭️  API calls: {'DISABLED' if skip_api_calls else 'ENABLED'}")
    print(f"{'='*80}\n")
    
    if skip_api_calls:
        print("⏭️  Skipping API calls (dry run mode)")
        return
    
    # Load config
    try:
        config = load_config()
        print("✅ Config loaded successfully\n")
    except Exception as e:
        print(f"❌ Failed to load config: {str(e)}")
        return
    
    # Initialize fetcher
    fetcher = BatchTrendFetcher(config)
    
    # Convert failed queries to query_info format
    query_infos = []
    for failed in failed_queries:
        query_text = failed.get("query_text", "")
        query_level = failed.get("query_level", "ingredient")
        
        # Try to infer category and other fields from query_text
        category = "skincare"  # Default
        if any(word in query_text.lower() for word in ["hair", "shampoo", "conditioner"]):
            category = "haircare"
        
        query_info = {
            "query_text": query_text,
            "query_level": query_level,
            "category": category,
            "ingredient_tag": None,
            "product_format": None,
            "benefit_tag": None,
            "brand_tag": None,
            "comparison_group": None
        }
        query_infos.append(query_info)
    
    # Results tracking
    results = {
        "success": 0,
        "error": 0,
        "failed_queries": []
    }
    
    # Process with progress bar
    delay_between_requests = 1.0 / fetcher.rate_limit_per_second
    start_time = datetime.now()
    
    pbar = tqdm(
        total=len(query_infos),
        desc="Retrying failed queries",
        unit="query",
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]"
    )
    
    for query_info in query_infos:
        query_text = query_info["query_text"]
        pbar.set_description(f"Retrying: {query_text[:40]}...")
        
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
            await asyncio.sleep(delay_between_requests)
        
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
    
    # Summary
    print(f"\n{'='*80}")
    print(f"📊 Retry Summary")
    print(f"{'='*80}")
    print(f"✅ Success: {results['success']}")
    print(f"❌ Errors: {results['error']}")
    print(f"📊 Total: {len(query_infos)}")
    
    # Timing
    print(f"\n⏱️  Timing Information:")
    print(f"   Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Ended: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Total time: {elapsed_time/60:.2f} minutes ({elapsed_time:.0f} seconds)")
    if len(query_infos) > 0:
        avg_time = elapsed_time / len(query_infos)
        print(f"   Average per query: {avg_time:.2f} seconds")
    
    # Still failed queries
    if results["failed_queries"]:
        print(f"\n❌ Still Failed Queries ({len(results['failed_queries'])}):")
        print(f"{'='*80}")
        
        # Group by error type
        error_groups = {}
        for failed in results["failed_queries"]:
            error = failed.get("error", "Unknown error")
            if error not in error_groups:
                error_groups[error] = []
            error_groups[error].append(failed)
        
        for error, queries in error_groups.items():
            print(f"\n   Error: {error[:80]}")
            print(f"   Count: {len(queries)}")
            print(f"   Queries:")
            for q in queries[:10]:
                print(f"      - {q['query_text']}")
            if len(queries) > 10:
                print(f"      ... and {len(queries) - 10} more")
        
        # Save still-failed queries
        still_failed_file = project_root / "still_failed_queries.json"
        with open(still_failed_file, 'w', encoding='utf-8') as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "total_failed": len(results["failed_queries"]),
                "failed_queries": results["failed_queries"]
            }, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Still-failed queries saved to: {still_failed_file}")
    else:
        print(f"\n✅ All queries succeeded!")
    
    print(f"\n⏰ Completed at: {datetime.now().isoformat()}")
    print(f"{'='*80}\n")


async def retry_failed_queries_from_file(failed_file: Path, skip_api_calls: bool = False):
    """Main entry point - loads file and retries"""
    failed_queries = await load_failed_queries(failed_file)
    await retry_failed_queries(failed_queries, skip_api_calls)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Retry failed market trends queries")
    parser.add_argument(
        "--file",
        type=str,
        default="failed_queries.json",
        help="Path to failed_queries.json file (default: failed_queries.json)"
    )
    parser.add_argument(
        "--enable-api",
        action="store_true",
        help="Enable actual API calls (default: disabled for safety)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode - don't fetch data"
    )
    
    args = parser.parse_args()
    
    failed_file = project_root / args.file
    skip_api_calls = not args.enable_api or args.dry_run
    
    asyncio.run(retry_failed_queries_from_file(failed_file, skip_api_calls))

