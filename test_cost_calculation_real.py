"""
Real test for cost calculation with MongoDB and markup
Tests actual working code for ingredient cost fetching and formula cost calculation
"""

import asyncio
import sys
import os
from pathlib import Path

# Fix encoding issues
os.environ['PYTHONIOENCODING'] = 'utf-8'
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Test ingredients with their percentages
TEST_INGREDIENTS = [
    # Phase A - Water Phase (70-75°C)
    {"name": "Aqua", "inci": "Aqua", "percentage": 88.30, "function": "Solvent", "is_hero": False},
    {"name": "Glycerin", "inci": "Glycerin", "percentage": 5.00, "function": "Humectant", "is_hero": False},
    {"name": "Sodium Lauryl Sulfate", "inci": "Sodium Lauryl Sulfate", "percentage": 3.00, "function": "Surfactant", "is_hero": False},
    # Phase B - Oil Phase (70-75°C)
    {"name": "Cetyl Alcohol", "inci": "Cetyl Alcohol", "percentage": 2.00, "function": "Emollient/Thickener", "is_hero": False},
    # Phase C - Cool Down Phase (Below 40°C)
    {"name": "Phenoxyethanol", "inci": "Phenoxyethanol", "percentage": 0.80, "function": "Preservative", "is_hero": False},
    {"name": "Citric Acid", "inci": "Citric Acid", "percentage": 0.10, "function": "pH Adjuster", "is_hero": False},
    {"name": "Sodium Hydroxide", "inci": "Sodium Hydroxide", "percentage": 0.80, "function": "pH Adjuster", "is_hero": False},
]


async def test_cost_calculation():
    """Test cost calculation with MongoDB lookup and markup"""
    print("=" * 100)
    print("COST CALCULATION TEST - MongoDB with 35% Markup")
    print("=" * 100)
    print()
    
    try:
        from app.ai_ingredient_intelligence.utils.inci_cost_lookup_mongo import (
            lookup_cost_by_inci,
            lookup_multiple_costs
        )
        from app.ai_ingredient_intelligence.db.collections import db
        
        # Check MongoDB connection
        ingredient_costs_col = db["ingredient_costs"]
        count = await ingredient_costs_col.count_documents({})
        print(f"[OK] MongoDB Connection: OK")
        print(f"[INFO] Total ingredients in database: {count}")
        print()
        
        if count == 0:
            print("[WARNING] ingredient_costs collection is empty!")
            print("   Run migration script: python -m app.ai_ingredient_intelligence.scripts.migrate_excel_costs_to_mongo")
            print()
        
    except Exception as e:
        print(f"[ERROR] Error importing modules: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("Testing Individual Ingredient Cost Lookups:")
    print("-" * 100)
    print()
    
    results = []
    mongo_count = 0
    fallback_count = 0
    
    for ing in TEST_INGREDIENTS:
        inci = ing["inci"]
        percentage = ing["percentage"]
        
        print(f"Ingredient: {ing['name']} ({inci})")
        print(f"  Percentage: {percentage}%")
        print(f"  Function: {ing['function']}")
        print(f"  Hero: {ing['is_hero']}")
        
        try:
            cost_data = await lookup_cost_by_inci(inci, use_fallback=True)
            
            if cost_data:
                cost_per_kg = cost_data.get('avg_cost', 0)
                base_cost = cost_data.get('base_cost', cost_per_kg)
                markup_percent = cost_data.get('markup_percent', 0)
                is_fallback = cost_data.get('is_fallback', False)
                source = cost_data.get('primary_supplier', 'Unknown')
                
                # Calculate cost per 100g
                cost_per_100g = (percentage / 100) * (cost_per_kg / 10)
                
                if is_fallback:
                    fallback_count += 1
                    print(f"  Source: FALLBACK (confidence: {cost_data.get('confidence', 'unknown')})")
                    print(f"  Cost: Rs {cost_per_kg:.2f}/kg")
                else:
                    mongo_count += 1
                    print(f"  Source: MONGODB")
                    print(f"  Supplier: {source}")
                    if base_cost != cost_per_kg:
                        print(f"  Base Cost: Rs {base_cost:.2f}/kg")
                        print(f"  With {markup_percent}% Markup: Rs {cost_per_kg:.2f}/kg")
                    else:
                        print(f"  Cost: Rs {cost_per_kg:.2f}/kg")
                
                print(f"  Cost per 100g: Rs {cost_per_100g:.4f}")
                
                results.append({
                    'ingredient': ing['name'],
                    'inci': inci,
                    'percentage': percentage,
                    'cost_per_kg': cost_per_kg,
                    'base_cost': base_cost,
                    'markup_percent': markup_percent if not is_fallback else 0,
                    'cost_per_100g': cost_per_100g,
                    'is_fallback': is_fallback,
                    'source': 'MongoDB' if not is_fallback else 'Fallback'
                })
            else:
                print(f"  [ERROR] No cost data found")
                results.append({
                    'ingredient': ing['name'],
                    'inci': inci,
                    'percentage': percentage,
                    'cost_per_kg': 0,
                    'base_cost': 0,
                    'markup_percent': 0,
                    'cost_per_100g': 0,
                    'is_fallback': False,
                    'source': 'Not found'
                })
        except Exception as e:
            print(f"  [ERROR] Error: {e}")
            import traceback
            traceback.print_exc()
        
        print()
    
    # Calculate total cost
    print("=" * 100)
    print("COST CALCULATION SUMMARY")
    print("=" * 100)
    print()
    
    total_cost_per_100g = 0
    total_base_cost_per_100g = 0
    total_markup_per_100g = 0
    
    print(f"{'Ingredient':<40} {'%':<8} {'Base/kg':<12} {'Markup':<8} {'Final/kg':<12} {'Cost/100g':<12} {'Source':<15}")
    print("-" * 120)
    
    for result in results:
        ingredient = result['ingredient']
        percentage = result['percentage']
        base_cost = result['base_cost']
        markup_percent = result['markup_percent']
        cost_per_kg = result['cost_per_kg']
        cost_per_100g = result['cost_per_100g']
        source = result['source']
        
        total_cost_per_100g += cost_per_100g
        
        if not result['is_fallback'] and base_cost > 0:
            base_per_100g = (percentage / 100) * (base_cost / 10)
            markup_per_100g = cost_per_100g - base_per_100g
            total_base_cost_per_100g += base_per_100g
            total_markup_per_100g += markup_per_100g
            print(f"{ingredient:<40} {percentage:<8.2f} Rs {base_cost:<11.2f} {markup_percent}%{'':<4} Rs {cost_per_kg:<11.2f} Rs {cost_per_100g:<11.4f} {source:<15}")
        else:
            print(f"{ingredient:<40} {percentage:<8.2f} {'-':<12} {'-':<8} Rs {cost_per_kg:<11.2f} Rs {cost_per_100g:<11.4f} {source:<15}")
    
    print("-" * 120)
    print(f"{'TOTAL COST PER 100g':<40} {'':<8} {'':<12} {'':<8} {'':<12} Rs {total_cost_per_100g:<11.4f}")
    if total_base_cost_per_100g > 0:
        print(f"{'  - Base Cost (before markup)':<40} {'':<8} {'':<12} {'':<8} {'':<12} Rs {total_base_cost_per_100g:<11.4f}")
        print(f"{'  - Markup (35%)':<40} {'':<8} {'':<12} {'':<8} {'':<12} Rs {total_markup_per_100g:<11.4f}")
    print()
    print(f"Total Formula Cost: Rs {total_cost_per_100g:.4f} per 100g")
    print(f"Total Formula Cost: Rs {total_cost_per_100g * 10:.2f} per kg")
    print()
    print("Summary:")
    print(f"  [OK] From MongoDB (with 35% markup): {mongo_count} ingredients")
    print(f"  [WARNING] From Fallback: {fallback_count} ingredients")
    print()
    print("=" * 100)


if __name__ == "__main__":
    try:
        asyncio.run(test_cost_calculation())
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"\nError running test: {e}")
        import traceback
        traceback.print_exc()

