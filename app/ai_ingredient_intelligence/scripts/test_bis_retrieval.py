# app/ai_ingredient_intelligence/scripts/test_bis_retrieval.py
"""
Test script to check if BIS cautions are available for specific ingredients.
Tests the BIS retrieval system for a list of ingredients.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path to allow imports
# Script is at: app/ai_ingredient_intelligence/scripts/test_bis_retrieval.py
# Need to go up 3 levels to reach project root
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from app.ai_ingredient_intelligence.logic.bis_rag import (
    get_bis_cautions_for_ingredients,
    get_bis_retriever,
    check_bis_rag_health
)


async def test_bis_retrieval():
    """Test BIS retrieval for a list of ingredients"""
    
    # List of ingredients to test
    test_ingredients = [
        "Aqua",
        "Cetyl Alcohol",
        "Propylene Glycol",
        "Sodium Lauryl Sulphate",
        "Stearyl Alcohol",
        "Polysorbate 20",
        "Methyl Paraben",
        "Propyl Paraben",
        "Butyl Paraben"
    ]
    
    print("=" * 80)
    print("BIS RETRIEVAL TEST SCRIPT")
    print("=" * 80)
    print()
    
    # First, check BIS RAG system health
    print("🔍 Checking BIS RAG system health...")
    health = check_bis_rag_health()
    print(f"   Status: {health['status']}")
    print(f"   PDF files: {health['pdf_files']}")
    print(f"   Vectorstore exists: {health['vectorstore_exists']}")
    print(f"   Vectorstore initialized: {health['vectorstore_initialized']}")
    print(f"   Retriever created: {health['retriever_created']}")
    print(f"   Test query successful: {health['test_query_successful']}")
    
    if health['errors']:
        print(f"   ⚠️ Errors: {health['errors']}")
    print()
    
    # Check if retriever is available
    print("🔍 Checking if BIS retriever is available...")
    try:
        retriever = get_bis_retriever()
        if retriever is None:
            print("   ❌ BIS retriever is not available. Cannot proceed with test.")
            print("   Please ensure BIS vectorstore is properly initialized.")
            return
        print("   ✅ BIS retriever is available")
        print()
    except Exception as e:
        print(f"   ❌ Error getting BIS retriever: {e}")
        return
    
    # Test retrieval for all ingredients
    print("=" * 80)
    print(f"Testing BIS retrieval for {len(test_ingredients)} ingredients:")
    print("=" * 80)
    print()
    
    for i, ingredient in enumerate(test_ingredients, 1):
        print(f"[{i}/{len(test_ingredients)}] Testing: {ingredient}")
    
    print()
    print("Retrieving BIS cautions...")
    print("-" * 80)
    
    try:
        # Get BIS cautions for all ingredients
        cautions_map = await get_bis_cautions_for_ingredients(test_ingredients)
        
        # Display results
        print()
        print("=" * 80)
        print("RESULTS")
        print("=" * 80)
        print()
        
        # Summary statistics
        ingredients_with_cautions = sum(1 for cautions in cautions_map.values() if cautions)
        ingredients_without_cautions = len(test_ingredients) - ingredients_with_cautions
        
        print(f"📊 Summary:")
        print(f"   Total ingredients tested: {len(test_ingredients)}")
        print(f"   Ingredients with BIS cautions: {ingredients_with_cautions}")
        print(f"   Ingredients without BIS cautions: {ingredients_without_cautions}")
        print()
        
        # Detailed results for each ingredient
        print("-" * 80)
        print("Detailed Results:")
        print("-" * 80)
        print()
        
        for ingredient in test_ingredients:
            cautions = cautions_map.get(ingredient, [])
            
            if cautions:
                print(f"✅ {ingredient}")
                print(f"   Found {len(cautions)} caution(s):")
                for i, caution in enumerate(cautions, 1):
                    # Truncate long cautions for display
                    display_caution = caution[:150] + "..." if len(caution) > 150 else caution
                    print(f"   {i}. {display_caution}")
            else:
                print(f"❌ {ingredient}")
                print(f"   No BIS cautions found")
            
            print()
        
        # Note about Aqua
        if "Aqua" in test_ingredients:
            print("-" * 80)
            print("ℹ️  Note: 'Aqua' (water) is typically filtered out by the BIS retrieval")
            print("   system as water-related ingredients don't have BIS cautions.")
            print("-" * 80)
            print()
        
    except Exception as e:
        print(f"❌ Error during BIS retrieval: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("=" * 80)
    print("Test completed!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_bis_retrieval())

