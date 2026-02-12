"""
Clear Market Trends Data
========================

Utility script to clear market trends data from MongoDB.
Use this before running a fresh batch fetch.
"""

import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Set UTF-8 encoding for Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# Load environment
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path)

from motor.motor_asyncio import AsyncIOMotorClient

# Direct MongoDB connection to avoid import chain issues
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "skin_bb")

client = AsyncIOMotorClient(MONGO_URI)
db = client[DB_NAME]
market_trends_storage_col = db["market_trends_storage"]


async def clear_market_trends_data(clear_all: bool = False, clear_batch_only: bool = True):
    """
    Clear market trends data from MongoDB.
    
    Args:
        clear_all: If True, clears all data. If False, only clears batch data.
        clear_batch_only: If True, only clears data with fetch_source='batch'
    """
    print(f"\n{'='*80}")
    print(f"🗑️  Clear Market Trends Data")
    print(f"{'='*80}")
    print(f"⏰ Started at: {datetime.now().isoformat()}")
    
    if clear_all:
        print(f"⚠️  Mode: CLEAR ALL DATA")
        query = {}
    elif clear_batch_only:
        print(f"📋 Mode: Clear batch data only (fetch_source='batch')")
        query = {"fetch_source": "batch"}
    else:
        print(f"📋 Mode: Clear all data")
        query = {}
    
    # Count documents to be deleted
    count = await market_trends_storage_col.count_documents(query)
    print(f"📊 Documents to delete: {count}")
    
    if count == 0:
        print(f"✅ No data to clear")
        print(f"{'='*80}\n")
        return
    
    # Confirm deletion
    print(f"\n⚠️  WARNING: This will delete {count} documents!")
    print(f"Press Ctrl+C to cancel, or wait 5 seconds to proceed...")
    
    try:
        await asyncio.sleep(5)
    except KeyboardInterrupt:
        print(f"\n❌ Cancelled by user")
        print(f"{'='*80}\n")
        return
    
    # Delete documents
    try:
        result = await market_trends_storage_col.delete_many(query)
        deleted_count = result.deleted_count
        
        print(f"\n✅ Successfully deleted {deleted_count} documents")
        print(f"⏰ Completed at: {datetime.now().isoformat()}")
        print(f"{'='*80}\n")
        
    except Exception as e:
        print(f"\n❌ Error deleting data: {str(e)}")
        import traceback
        traceback.print_exc()
        print(f"{'='*80}\n")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Clear market trends data")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Clear ALL data (not just batch data)"
    )
    parser.add_argument(
        "--batch-only",
        action="store_true",
        default=True,
        help="Clear only batch data (default)"
    )
    
    args = parser.parse_args()
    
    clear_all = args.all
    clear_batch_only = not args.all and args.batch_only
    
    asyncio.run(clear_market_trends_data(clear_all=clear_all, clear_batch_only=clear_batch_only))

