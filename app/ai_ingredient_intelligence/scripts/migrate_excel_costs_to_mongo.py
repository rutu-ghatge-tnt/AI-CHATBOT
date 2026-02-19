"""
Migrate Excel Cost Data to MongoDB
==================================

This script migrates ingredient costs from the Excel file to MongoDB.
Creates a new collection 'ingredient_costs' for fast lookups.

Usage:
    python -m app.ai_ingredient_intelligence.scripts.migrate_excel_costs_to_mongo
"""

import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Dict, List
import asyncio
from pymongo import ASCENDING

# Import MongoDB connection
from app.ai_ingredient_intelligence.db.mongodb import db

# Collection for ingredient costs
ingredient_costs_col = db["ingredient_costs"]

EXCEL_FILE_PATH = Path(__file__).parent.parent.parent.parent / "Branded_Cosmetic_Ingredients_INCI_Mapped_MDB_COMBINED.xlsx"


async def migrate_excel_to_mongo():
    """Migrate Excel cost data to MongoDB."""
    
    print("📊 Loading Excel file...")
    if not EXCEL_FILE_PATH.exists():
        raise FileNotFoundError(f"Excel file not found: {EXCEL_FILE_PATH}")
    
    df = pd.read_excel(EXCEL_FILE_PATH)
    print(f"✅ Loaded {len(df)} rows from Excel")
    
    # Normalize column names
    df.columns = df.columns.str.strip()
    
    # Validate required columns
    required_cols = ['INCI Name', 'Avg Cost']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")
    
    # Clean data
    df = df.dropna(subset=['INCI Name', 'Avg Cost'])
    df['INCI Name'] = df['INCI Name'].astype(str).str.strip()
    df['Avg Cost'] = pd.to_numeric(df['Avg Cost'], errors='coerce')
    df = df.dropna(subset=['Avg Cost'])
    
    print(f"✅ Cleaned data: {len(df)} valid rows")
    
    # Create indexes
    print("📇 Creating indexes...")
    await ingredient_costs_col.create_index([("inci_name_normalized", ASCENDING)], unique=False)
    await ingredient_costs_col.create_index([("avg_cost", ASCENDING)])
    await ingredient_costs_col.create_index([("branded_ingredient", ASCENDING)])
    print("✅ Indexes created")
    
    # Prepare documents
    documents = []
    skipped = 0
    
    for idx, row in df.iterrows():
        inci_name = str(row['INCI Name']).strip()
        avg_cost = float(row['Avg Cost'])
        
        if not inci_name or pd.isna(avg_cost):
            skipped += 1
            continue
        
        # Normalize INCI name for searching
        inci_normalized = inci_name.lower().strip()
        
        doc = {
            "inci_name": inci_name,
            "inci_name_normalized": inci_normalized,
            "avg_cost": avg_cost,
            "branded_ingredient": str(row.get('Branded Ingredient', '')).strip() if pd.notna(row.get('Branded Ingredient')) else '',
            "primary_supplier": str(row.get('Primary Supplier', '')).strip() if pd.notna(row.get('Primary Supplier')) else '',
            "source": "excel_migration",
            "migrated_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        documents.append(doc)
    
    if skipped > 0:
        print(f"⚠️ Skipped {skipped} invalid rows")
    
    # Insert in batches
    batch_size = 500
    total_inserted = 0
    total_updated = 0
    
    print(f"\n💾 Inserting/updating {len(documents)} documents...")
    
    for i in range(0, len(documents), batch_size):
        batch = documents[i:i + batch_size]
        
        for doc in batch:
            # Use upsert to update if exists, insert if not
            result = await ingredient_costs_col.update_one(
                {
                    "inci_name_normalized": doc["inci_name_normalized"],
                    "branded_ingredient": doc["branded_ingredient"]
                },
                {
                    "$set": {
                        "inci_name": doc["inci_name"],
                        "avg_cost": doc["avg_cost"],
                        "primary_supplier": doc["primary_supplier"],
                        "updated_at": datetime.utcnow()
                    },
                    "$setOnInsert": {
                        "source": doc["source"],
                        "migrated_at": doc["migrated_at"]
                    }
                },
                upsert=True
            )
            
            # If matched_count is 0, it was inserted (upserted)
            # If matched_count > 0, it was updated
            if result.matched_count == 0:
                total_inserted += 1
            else:
                total_updated += 1
        
        print(f"   Processed {min(i + batch_size, len(documents))}/{len(documents)} documents...")
    
    print(f"\n✅ Migration complete!")
    print(f"   - Inserted: {total_inserted}")
    print(f"   - Updated: {total_updated}")
    print(f"   - Total in collection: {await ingredient_costs_col.count_documents({})}")
    
    # Show sample
    sample = await ingredient_costs_col.find_one({})
    if sample:
        print(f"\n📋 Sample document:")
        print(f"   INCI: {sample.get('inci_name')}")
        print(f"   Cost: ₹{sample.get('avg_cost')}/kg")
        print(f"   Branded: {sample.get('branded_ingredient')}")


async def verify_migration():
    """Verify the migration by checking sample lookups."""
    print("\n🔍 Verifying migration...")
    
    test_ingredients = ["Niacinamide", "Glycerin", "Hyaluronic Acid", "Retinol"]
    
    for inci in test_ingredients:
        inci_normalized = inci.lower().strip()
        doc = await ingredient_costs_col.find_one(
            {"inci_name_normalized": {"$regex": inci_normalized, "$options": "i"}}
        )
        
        if doc:
            print(f"   ✅ {inci}: ₹{doc.get('avg_cost')}/kg")
        else:
            print(f"   ❌ {inci}: Not found")


if __name__ == "__main__":
    import sys
    
    async def main():
        try:
            await migrate_excel_to_mongo()
            await verify_migration()
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    
    asyncio.run(main())

